"""Feasibility dryrun: 学习「翻页 vs 换章」视觉判别器是否值得做。

做的事：
1. 扫 data/outputs/*.chapters.json，找开了 keyframes 且产物完整的视频
2. 用 Chinese-CLIP 把每个 keyframe JPG encode 成 768d 特征
3. 对相邻 (kf_i, kf_{i+1}) 算：cos_sim、L2、是否章边界
4. 报告：
   - 数据规模 (n_videos, n_pairs, pos/neg balance)
   - cos_sim 在正/负样本的分布（mean/median/std/p25/p75）
   - 单特征 logistic baseline F1（仅 cos_sim → boundary）
   - 简单 MLP（feat_diff 768d → 2 层 → 1）baseline F1

如果 single-feature F1 已 > 0.7，说明信号强；MLP > 0.75 就可以正式训练。
F1 < 0.6 说明 CLIP feature 区分度不够，要换 VLM 或加文本特征。

跑法：
  .venv/Scripts/python.exe scripts/_dryrun_visual_boundary.py
  .venv/Scripts/python.exe scripts/_dryrun_visual_boundary.py --no-mlp  # 跳过 MLP，只看分布
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
from PIL import Image
import torch

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

OUTPUTS = ROOT / "data" / "outputs"
CACHE = ROOT / "data" / "_dryrun_visual_features.npz"


def find_videos_with_keyframes() -> list[tuple[str, str]]:
    """返回 [(chapters_json_path, keyframes_dir_path), ...]，跑过 keyframes 且配对的视频。"""
    out: list[tuple[str, str]] = []
    for chap_p in glob.glob(str(OUTPUTS / "*.chapters.json")):
        try:
            d = json.loads(Path(chap_p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        ab = d.get("ablation") or {}
        if not ab.get("keyframes"):
            continue
        if not d.get("chapters"):
            continue
        # 找对应的 .keyframes 目录（同 stem 前缀，可能有 .mm / .mm.vl 后缀差异）
        stem = Path(chap_p).name.replace(".chapters.json", "")
        # 同 stem 直接 + .keyframes
        candidates = [
            OUTPUTS / f"{stem}.keyframes",
            OUTPUTS / f"{stem.replace('.vl', '')}.keyframes",
            OUTPUTS / f"{stem.replace('.mm.vl', '.mm')}.keyframes",
        ]
        kf_dir = next((p for p in candidates if p.is_dir()), None)
        if kf_dir is None:
            # glob 兜底
            base = stem.split(".")[0]
            kf_dirs = [p for p in OUTPUTS.glob(f"{base}*.keyframes") if p.is_dir()]
            if kf_dirs:
                kf_dir = kf_dirs[0]
        if kf_dir is None:
            continue
        out.append((chap_p, str(kf_dir)))
    return out


def list_keyframes(kf_dir: str) -> list[tuple[int, str]]:
    """返回 [(chunk_idx_0based, jpg_path), ...] 按 chunk_idx 排序。文件名形如 keyframe_01_0027s.jpg。"""
    pairs: list[tuple[int, str]] = []
    for f in sorted(os.listdir(kf_dir)):
        if not f.endswith(".jpg"):
            continue
        m = re.match(r"keyframe_(\d+)_", f)
        if not m:
            continue
        # 文件名 1-indexed，转 0-indexed
        idx = int(m.group(1)) - 1
        pairs.append((idx, os.path.join(kf_dir, f)))
    # 同一 chunk 可能多张 keyframe，去重保留第一个
    seen: set[int] = set()
    uniq: list[tuple[int, str]] = []
    for idx, p in pairs:
        if idx in seen:
            continue
        seen.add(idx)
        uniq.append((idx, p))
    uniq.sort(key=lambda x: x[0])
    return uniq


def load_clip():
    """加载 Chinese-CLIP，跟 keyframe.py 同源（避免 OFA-Sys text_model BertPooler 兼容问题，
    只用 image 端）。"""
    from transformers import ChineseCLIPModel, ChineseCLIPProcessor
    model_dir = ROOT / "models" / "chinese-clip-vit-base-patch16"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"  [clip] loading from {model_dir} (device={device}, dtype={dtype}) ...")
    model = ChineseCLIPModel.from_pretrained(str(model_dir), torch_dtype=dtype).to(device).eval()
    processor = ChineseCLIPProcessor.from_pretrained(str(model_dir))
    return model, processor, device


def encode_keyframes(model, processor, device,
                     jpg_paths: list[str]) -> np.ndarray:
    """批量 encode keyframe JPG 列表，返回 (N, 768) L2-normalized 特征。"""
    feats: list[torch.Tensor] = []
    batch_size = 16
    with torch.no_grad():
        for s in range(0, len(jpg_paths), batch_size):
            batch_paths = jpg_paths[s:s + batch_size]
            imgs = [Image.open(p).convert("RGB") for p in batch_paths]
            inputs = processor(images=imgs, return_tensors="pt").to(device)
            f = model.get_image_features(**inputs)
            f = f / f.norm(dim=-1, keepdim=True)
            feats.append(f.float().cpu())
    return torch.cat(feats, dim=0).numpy()


def build_dataset(force_recompute: bool = False) -> dict:
    """返回 {video_id: {feats, chunk_idxs, boundary_chunk_idxs}}。"""
    if CACHE.exists() and not force_recompute:
        print(f"  [cache] loading {CACHE}")
        data = np.load(CACHE, allow_pickle=True)
        return dict(data["data"].item())

    videos = find_videos_with_keyframes()
    print(f"  扫到 {len(videos)} 个开了 keyframes 的视频")
    if not videos:
        raise SystemExit("no videos with keyframes found")

    model, processor, device = load_clip()
    dataset: dict = {}
    for i, (chap_p, kf_dir) in enumerate(videos, 1):
        d = json.loads(Path(chap_p).read_text(encoding="utf-8"))
        chapters = d.get("chapters", [])
        # boundary_chunk_idxs = 每章起点（除第 0 章），表示 chunk[idx-1] 与 chunk[idx] 之间是边界
        boundary_chunk_idxs = sorted(set(
            ch["indices"][0] for ch in chapters[1:]
            if ch.get("indices") and ch["indices"][0] > 0))
        kfs = list_keyframes(kf_dir)
        if len(kfs) < 2:
            continue
        # 防御：如果 chunk 数 vs keyframe 数不对齐就跳过
        max_chunk_idx = kfs[-1][0]
        if not all(b <= max_chunk_idx for b in boundary_chunk_idxs):
            print(f"    [skip] {Path(chap_p).stem}: boundary 越界 (max_kf_idx={max_chunk_idx}, bds={boundary_chunk_idxs})")
            continue
        # encode
        jpg_paths = [p for _, p in kfs]
        feats = encode_keyframes(model, processor, device, jpg_paths)
        # 用 chunk_idx 标识
        chunk_idxs = np.array([idx for idx, _ in kfs], dtype=np.int32)
        dataset[Path(chap_p).stem] = {
            "feats": feats,
            "chunk_idxs": chunk_idxs,
            "boundary_chunk_idxs": np.array(boundary_chunk_idxs, dtype=np.int32),
        }
        print(f"  [{i}/{len(videos)}] {Path(chap_p).stem}  n_kf={len(kfs)}  n_boundaries={len(boundary_chunk_idxs)}")
    # 缓存
    np.savez_compressed(CACHE, data=np.array(dataset, dtype=object))
    print(f"  [cache] wrote {CACHE}")
    return dataset


def make_pairs(dataset: dict):
    """从数据集拼相邻 pair：返回 X_sim (N,), X_l2 (N,), X_diff (N, 768), y (N,)"""
    sims: list[float] = []
    l2s: list[float] = []
    diffs: list[np.ndarray] = []
    ys: list[int] = []
    video_ids: list[str] = []
    for vid, d in dataset.items():
        feats = d["feats"]
        chunk_idxs = d["chunk_idxs"]
        boundary_set = set(int(b) for b in d["boundary_chunk_idxs"])
        for i in range(len(chunk_idxs) - 1):
            f_i = feats[i]
            f_j = feats[i + 1]
            sims.append(float(np.dot(f_i, f_j)))  # 已 L2-norm，dot = cos
            l2s.append(float(np.linalg.norm(f_i - f_j)))
            diffs.append((f_j - f_i).astype(np.float32))
            # label: chunk_idxs[i+1] 是某章首段 → 边界
            y = 1 if int(chunk_idxs[i + 1]) in boundary_set else 0
            ys.append(y)
            video_ids.append(vid)
    return (np.array(sims, np.float32), np.array(l2s, np.float32),
            np.stack(diffs), np.array(ys, np.int32), video_ids)


def stat_report(sims, l2s, ys):
    """信号分布对比 + 单特征 logistic baseline。"""
    pos_mask = ys == 1
    print(f"\n=== 数据规模 ===")
    print(f"  total pairs: {len(ys)}")
    print(f"  boundary (+): {pos_mask.sum()} ({pos_mask.mean():.1%})")
    print(f"  page-flip (-): {(~pos_mask).sum()} ({1 - pos_mask.mean():.1%})")

    print(f"\n=== cos_sim 分布（高 = 视觉相似 = 应该是同章翻页）===")
    for name, vals in [("boundary (+)", sims[pos_mask]),
                        ("page-flip (-)", sims[~pos_mask])]:
        if len(vals) == 0:
            print(f"  {name}: <empty>")
            continue
        print(f"  {name}: mean={vals.mean():.3f}  median={np.median(vals):.3f}  "
              f"std={vals.std():.3f}  p25={np.percentile(vals,25):.3f}  "
              f"p75={np.percentile(vals,75):.3f}")
    gap = sims[~pos_mask].mean() - sims[pos_mask].mean()
    print(f"  Δmean(neg-pos) = {gap:.3f}  "
          f"（>0.05 信号清晰，0.02-0.05 弱信号，<0.02 几乎无）")

    # AUROC for sim (低 sim → boundary)
    from sklearn.metrics import roc_auc_score, f1_score
    auroc_sim = roc_auc_score(ys, -sims)  # 负方向：低 sim 是边界
    auroc_l2 = roc_auc_score(ys, l2s)
    print(f"\n=== 单特征 AUROC ===")
    print(f"  cos_sim → boundary: AUROC = {auroc_sim:.3f}")
    print(f"  l2_dist → boundary: AUROC = {auroc_l2:.3f}")
    print(f"  （>0.75 强信号，0.65-0.75 中等，<0.65 弱）")

    # 简单 logistic threshold sweep on sim
    best_f1 = 0.0
    best_thr = None
    for thr in np.linspace(sims.min(), sims.max(), 50):
        pred = (sims < thr).astype(int)
        if pred.sum() == 0 or pred.sum() == len(pred):
            continue
        f1 = f1_score(ys, pred)
        if f1 > best_f1:
            best_f1 = f1
            best_thr = float(thr)
    print(f"  best single-threshold F1 (sim<thr=boundary): {best_f1:.3f} @ thr={best_thr:.3f}")
    return {"auroc_sim": float(auroc_sim), "auroc_l2": float(auroc_l2),
            "best_thr_f1": float(best_f1)}


def mlp_cv(X_diff, ys, video_ids, n_folds=5):
    """video-aware 5-fold CV 跑 2 层 MLP on feat_diff (768d)。"""
    try:
        from sklearn.neural_network import MLPClassifier
        from sklearn.metrics import f1_score, roc_auc_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("  sklearn 未安装，跳过 MLP")
        return None
    # video-level split: 同一视频的 pair 不能跨 fold（避免视频泄露）
    unique_vids = sorted(set(video_ids))
    np.random.seed(42)
    perm = np.random.permutation(len(unique_vids))
    folds = np.array_split(perm, n_folds)
    vid_to_idx = {v: i for i, v in enumerate(unique_vids)}
    pair_vid_idx = np.array([vid_to_idx[v] for v in video_ids])

    f1s, aurocs = [], []
    print(f"\n=== MLP video-aware {n_folds}-fold CV (feat_diff 768d → 2 layer MLP) ===")
    for k, test_vid_idxs in enumerate(folds):
        test_mask = np.isin(pair_vid_idx, test_vid_idxs)
        if test_mask.sum() == 0 or (~test_mask).sum() == 0:
            continue
        X_tr, X_te = X_diff[~test_mask], X_diff[test_mask]
        y_tr, y_te = ys[~test_mask], ys[test_mask]
        if y_tr.sum() == 0 or y_te.sum() == 0:
            print(f"  fold {k+1}: 标签不平衡跳过")
            continue
        sc = StandardScaler()
        X_tr_s = sc.fit_transform(X_tr)
        X_te_s = sc.transform(X_te)
        clf = MLPClassifier(hidden_layer_sizes=(128, 32), max_iter=300,
                            early_stopping=True, random_state=42,
                            validation_fraction=0.15)
        clf.fit(X_tr_s, y_tr)
        pred = clf.predict(X_te_s)
        prob = clf.predict_proba(X_te_s)[:, 1]
        f1 = f1_score(y_te, pred)
        auroc = roc_auc_score(y_te, prob) if len(np.unique(y_te)) > 1 else 0.5
        f1s.append(f1)
        aurocs.append(auroc)
        print(f"  fold {k+1}: train={len(y_tr)} test={len(y_te)} "
              f"pos%={y_te.mean():.1%}  F1={f1:.3f}  AUROC={auroc:.3f}")
    if not f1s:
        return None
    print(f"  mean F1 = {np.mean(f1s):.3f}  mean AUROC = {np.mean(aurocs):.3f}")
    return {"mean_f1": float(np.mean(f1s)), "mean_auroc": float(np.mean(aurocs)),
            "fold_f1s": [float(x) for x in f1s]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mlp", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="不用 cache，强制重 encode keyframes")
    args = ap.parse_args()

    print("=== 步骤 1: 拼数据集 ===")
    dataset = build_dataset(force_recompute=args.force)
    print(f"  videos: {len(dataset)}")
    n_pairs = sum(len(d["chunk_idxs"]) - 1 for d in dataset.values())
    print(f"  pair 总数: {n_pairs}")

    print("\n=== 步骤 2: 拼 pair 特征 ===")
    sims, l2s, diffs, ys, vids = make_pairs(dataset)
    print(f"  X_sim={sims.shape}  X_diff={diffs.shape}  y={ys.shape}")

    print("\n=== 步骤 3: 信号统计 ===")
    single_stat = stat_report(sims, l2s, ys)

    if not args.no_mlp:
        print("\n=== 步骤 4: MLP baseline ===")
        mlp_stat = mlp_cv(diffs, ys, vids)
    else:
        mlp_stat = None

    print("\n=== 结论 ===")
    if single_stat["auroc_sim"] >= 0.75:
        print(f"  [OK] 单特征 cos_sim AUROC={single_stat['auroc_sim']:.3f} 信号已经清晰")
    elif single_stat["auroc_sim"] >= 0.65:
        print(f"  [warn] 单特征 cos_sim AUROC={single_stat['auroc_sim']:.3f} 中等信号")
    else:
        print(f"  [no-go] 单特征 cos_sim AUROC={single_stat['auroc_sim']:.3f} 弱信号，CLIP feature 不够区分")

    if mlp_stat:
        if mlp_stat["mean_f1"] >= 0.75:
            print(f"  [OK] MLP F1={mlp_stat['mean_f1']:.3f} 值得正式训")
        elif mlp_stat["mean_f1"] >= 0.65:
            print(f"  [warn] MLP F1={mlp_stat['mean_f1']:.3f} 边缘可行，需扩 corpus 或加文本特征")
        else:
            print(f"  [no-go] MLP F1={mlp_stat['mean_f1']:.3f} 不值得，要换模态/换 feature")


if __name__ == "__main__":
    main()
