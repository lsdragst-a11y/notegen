"""关键帧抽取：用 Chinese-CLIP 给每段笔记匹配最相关的视频截图。

输入：summarize_chunks 输出（带 headline / start / end）。
对每个 chunk 在视频里等间距抽 N 帧，用 CLIP 算每帧与 headline 的 cosine
相似度，选最高那帧保存为 JPEG。

后续多模态章节切分会复用这里的 image features：相邻 chunk 平均图像
embedding 的 cosine 距离可以叠加到 boundary score。
"""
from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import ChineseCLIPModel, ChineseCLIPProcessor


DEFAULT_CLIP_DIR = Path("models/chinese-clip-vit-base-patch16")
_CACHE: dict[str, tuple] = {}


def load_clip(model_dir: Path | str = DEFAULT_CLIP_DIR,
              device: str | None = None, dtype: torch.dtype | None = None):
    key = str(model_dir)
    if key in _CACHE:
        return _CACHE[key]
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = dtype or (torch.float16 if device == "cuda" else torch.float32)
    print(f"      [clip] loading from {model_dir} (device={device}, dtype={dtype}) ...")
    processor = ChineseCLIPProcessor.from_pretrained(str(model_dir))
    # transformers 4.46 在 model.safetensors 缺 __metadata__ 时会 NPE，
    # 模型目录里同时有 pytorch_model.bin，退回 .bin 路径绕过
    model = ChineseCLIPModel.from_pretrained(
        str(model_dir), torch_dtype=dtype, use_safetensors=False,
    ).to(device)
    model.eval()
    _CACHE[key] = (model, processor, device, dtype)
    return _CACHE[key]


def sample_frames(video_path: Path | str, start: float, end: float,
                  n: int = 8) -> list[tuple[float, Image.Image]]:
    """在 [start, end] 内等间距抽 n 帧（跳过首尾边界以避开转场黑帧）。"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"opencv 打不开视频: {video_path}")
    if end <= start:
        cap.release()
        return []
    times = np.linspace(start, end, n + 2)[1:-1]
    frames: list[tuple[float, Image.Image]] = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append((float(t), Image.fromarray(rgb)))
    cap.release()
    return frames


def sample_frames_for_ranges(video_path: Path | str,
                             ranges: list[tuple[float, float]],
                             n: int = 8) -> list[list[tuple[float, Image.Image]]]:
    """对多个 [start, end] 区间各抽 n 帧，全程复用同一个 VideoCapture。
    替代"每段 open 一次 cap"，IO 与 demuxer init 都只做一次。返回每段一个 list。"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"opencv 打不开视频: {video_path}")
    out: list[list[tuple[float, Image.Image]]] = []
    try:
        for start, end in ranges:
            if end <= start:
                out.append([])
                continue
            times = np.linspace(start, end, n + 2)[1:-1]
            frames: list[tuple[float, Image.Image]] = []
            for t in times:
                cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
                ok, frame = cap.read()
                if not ok:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append((float(t), Image.fromarray(rgb)))
            out.append(frames)
    finally:
        cap.release()
    return out


def encode_frames_and_text(frames: list[tuple[float, Image.Image]], text: str,
                           model_data=None):
    """一次 CLIP forward 得到帧的 L2-normalized image features 和文本 features。
    返回 (img_feats, txt_feats, times, images)，img_feats 形状 [N, D]。"""
    model, processor, device, dtype = model_data or load_clip()
    times = [f[0] for f in frames]
    images = [f[1] for f in frames]
    img_inputs = processor(images=images, return_tensors="pt").to(device)
    txt_inputs = processor(text=[text], return_tensors="pt",
                           padding=True, truncation=True, max_length=52).to(device)
    with torch.no_grad():
        img_feats = model.get_image_features(**img_inputs)
        txt_feats = model.get_text_features(**txt_inputs)
        img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)
        txt_feats = txt_feats / txt_feats.norm(dim=-1, keepdim=True)
    return img_feats, txt_feats, times, images


def pick_keyframe(frames: list[tuple[float, Image.Image]], text: str,
                  model_data=None) -> tuple[float, Image.Image, float] | None:
    if not frames:
        return None
    img_feats, txt_feats, times, images = encode_frames_and_text(frames, text, model_data)
    sims = (img_feats @ txt_feats.T).squeeze(-1)
    best = int(sims.argmax().item())
    return times[best], images[best], float(sims[best].item())


def extract_keyframes(video_path: Path | str, chunks: Sequence[dict],
                      out_dir: Path | str,
                      samples_per_chunk: int = 8,
                      img_batch_size: int = 32
                      ) -> tuple[list[dict], list[np.ndarray | None]]:
    """对每个 chunk 选一张关键帧存盘，同时返回该 chunk 的平均图像 embedding
    （供多模态章节切分用 — 复用了同一次 CLIP forward，零额外推理开销）。
    返回 (enriched_chunks, chunk_visual_features)。

    实现路径（2026-05-15 优化前是 N 段各跑 1 次 CLIP forward + 各 open 一次 cap）：
    1) 一次 VideoCapture 顺序抽完所有段的帧（IO + demuxer 只 init 一次）
    2) 所有帧拼成一个 batch，分 img_batch_size 子批跑 CLIP image forward
    3) 所有 chunk headline 拼成 batch 跑一次 CLIP text forward
    4) 按 chunk 切回 image features，算 sim 选 best 帧、保存、算平均视觉 embedding

    img_batch_size=32 是显存与 forward 调用次数的折中：32 × 3×224×224 fp16
    ≈ 9.6MB 输入，CLIP-base 全部激活 < 1GB，对 4GB+ GPU 安全。
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model, processor, device, dtype = load_clip()

    chunk_list = list(chunks)
    n_chunks = len(chunk_list)

    # 1) 一次开 cap 抽完所有段
    ranges = [(c["start"], c["end"]) for c in chunk_list]
    all_frames = sample_frames_for_ranges(video_path, ranges, n=samples_per_chunk)

    # 2) 收集所有有效帧，标记 chunk_idx 便于后面切回
    flat_images: list[Image.Image] = []
    owner: list[int] = []  # 每帧属于哪个 chunk
    times_per_chunk: list[list[float]] = []
    images_per_chunk: list[list[Image.Image]] = []
    for ci, frames in enumerate(all_frames):
        ts_list = [t for t, _ in frames]
        im_list = [im for _, im in frames]
        times_per_chunk.append(ts_list)
        images_per_chunk.append(im_list)
        for im in im_list:
            flat_images.append(im)
            owner.append(ci)

    # 3) batch image forward
    if flat_images:
        feat_chunks: list[torch.Tensor] = []
        with torch.no_grad():
            for s in range(0, len(flat_images), img_batch_size):
                batch = flat_images[s:s + img_batch_size]
                img_inputs = processor(images=batch, return_tensors="pt").to(device)
                feats = model.get_image_features(**img_inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                feat_chunks.append(feats)
        all_img_feats = torch.cat(feat_chunks, dim=0) if feat_chunks else None
    else:
        all_img_feats = None

    # 4) text forward — 绕过 model.get_text_features。原因：OFA-Sys 的 chinese-clip
    # 训练时 text_model 不带 BertPooler（state_dict 里没 pooler.dense.weight），但
    # transformers 4.57 的 get_text_features 强引用 text_outputs.pooler_output 喂给
    # text_projection，结果是 text_projection(None) TypeError。绕过：直接调用
    # text_model 拿 last_hidden_state，取 CLS token (idx 0) 喂 text_projection。
    # 这是 OFA-Sys 原始训练时的用法，与历史 transformers 行为一致。
    texts = [c.get("headline") or c.get("text", "")[:80] for c in chunk_list]
    txt_chunks: list[torch.Tensor] = []
    with torch.no_grad():
        for t in texts:
            ti = processor(text=[t], return_tensors="pt",
                           padding=True, truncation=True, max_length=52).to(device)
            out = model.text_model(input_ids=ti["input_ids"],
                                   attention_mask=ti.get("attention_mask"),
                                   token_type_ids=ti.get("token_type_ids"))
            cls = out.last_hidden_state[:, 0, :]  # [1, 768]
            f = model.text_projection(cls)
            f = f / f.norm(dim=-1, keepdim=True)
            txt_chunks.append(f)
    all_txt_feats = torch.cat(txt_chunks, dim=0)

    # 5) 切回每个 chunk 算 sim、选 best、写盘
    enriched: list[dict] = []
    visual_feats: list[np.ndarray | None] = []
    # 预计算每个 chunk 在 flat_images 里的起止
    bounds: list[tuple[int, int]] = []
    cursor = 0
    for ci in range(n_chunks):
        n = len(images_per_chunk[ci])
        bounds.append((cursor, cursor + n))
        cursor += n

    for i, c in enumerate(chunk_list, 1):
        ci = i - 1
        new = dict(c)
        ts_list = times_per_chunk[ci]
        im_list = images_per_chunk[ci]
        if not im_list or all_img_feats is None:
            print(f"      [clip] {i}/{n_chunks} 抽帧失败 (start={c['start']:.1f}s)")
            new["keyframe"] = None
            visual_feats.append(None)
            enriched.append(new)
            continue
        lo, hi = bounds[ci]
        img_feats = all_img_feats[lo:hi]
        txt = all_txt_feats[ci:ci + 1]
        sims = (img_feats @ txt.T).squeeze(-1)
        best = int(sims.argmax().item())
        ts, img, score = ts_list[best], im_list[best], float(sims[best].item())
        mean = img_feats.mean(dim=0)
        mean = mean / mean.norm()
        visual_feats.append(mean.detach().float().cpu().numpy())

        fname = f"keyframe_{i:02d}_{int(ts):04d}s.jpg"
        path = out_dir / fname
        img.save(path, "JPEG", quality=85)
        new["keyframe"] = {"path": str(path), "rel": fname,
                           "time": ts, "score": score}
        print(f"      [clip] {i}/{n_chunks} -> {fname} "
              f"(t={ts:.1f}s, sim={score:.3f})")
        enriched.append(new)
    return enriched, visual_feats
