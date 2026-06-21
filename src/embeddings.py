"""bge-m3 向量层：一鱼两吃——
  1. pipeline 末尾给全部 chunk 算 dense 向量落盘（{stem}.embeddings.npz），
     publish 时随产物进 note 目录，QA hybrid 检索用；
  2. summarize.chunk_by_semantic 的句向量来源（--chunker semantic）。

依赖 sentence-transformers（torch 已在 GPU 栈里）。模型解析顺序：
models/bge-m3 本地副本 → HF hub "BAAI/bge-m3"（建议先下到本地：
HF_ENDPOINT=https://hf-mirror.com huggingface-cli download BAAI/bge-m3 --local-dir models/bge-m3）。

显存策略：pipeline 侧 encode_texts 先试 cuda，OOM/异常回落 CPU（几十个
chunk CPU 也就几十秒）；worker 侧 encode_query 固定 CPU + 模型常驻（单条
问题 <1s，不与 Qwen 抢 VRAM）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
_LOCAL_MODEL = ROOT / "models" / "bge-m3"
_HUB_ID = "BAAI/bge-m3"

_ENCODERS: dict[str, object] = {}   # device -> SentenceTransformer


def model_source() -> str:
    return str(_LOCAL_MODEL) if _LOCAL_MODEL.is_dir() else os.environ.get(
        "NOTEGEN_EMBED_MODEL", _HUB_ID)


def _get_encoder(device: str):
    enc = _ENCODERS.get(device)
    if enc is None:
        from sentence_transformers import SentenceTransformer
        enc = SentenceTransformer(model_source(), device=device)
        _ENCODERS[device] = enc
    return enc


def unload() -> None:
    """释放编码器（pipeline 在加载大模型前让位 VRAM 用）。"""
    _ENCODERS.clear()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def encode_texts(texts: list[str], device: Optional[str] = None,
                 batch_size: int = 16):
    """编码一批文本 → np.ndarray (n, dim)，L2 归一化。cuda 失败自动回落 cpu。
    自动选设备时按剩余 VRAM 决定：< 3GB（Qwen 常驻时的典型状态）直接走 CPU，
    不去试 cuda 再 OOM 回落——几十个 chunk CPU 编码也就几十秒。"""
    if device is None:
        device = "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                free_gb = torch.cuda.mem_get_info()[0] / 1024**3
                if free_gb >= 3.0:
                    device = "cuda"
                else:
                    print(f"      [embed] VRAM 剩余 {free_gb:.1f}GB < 3GB，"
                          f"直接用 CPU 编码", flush=True)
        except Exception:
            pass
    try:
        enc = _get_encoder(device)
        return enc.encode(texts, batch_size=batch_size,
                          normalize_embeddings=True, show_progress_bar=False)
    except Exception:
        if device == "cuda":
            _ENCODERS.pop("cuda", None)
            print("      [embed] cuda 编码失败，回落 CPU", flush=True)
            return encode_texts(texts, device="cpu", batch_size=batch_size)
        raise


def encode_query(text: str):
    """单条查询编码（worker QA 用）：固定 CPU、模型常驻。返回 list[float]。"""
    enc = _get_encoder("cpu")
    v = enc.encode([text], normalize_embeddings=True, show_progress_bar=False)
    return [float(x) for x in v[0]]


def chunk_text_for_embedding(chunk: dict) -> str:
    """chunk → 编码文本：headline + 正文前 512 字（bge-m3 支持长文，但 QA
    检索目标是话题级匹配，截断减少无关尾部稀释）。"""
    head = (chunk.get("headline") or "").strip()
    body = (chunk.get("text") or "").replace("\n", " ").strip()[:512]
    return f"{head}\n{body}".strip()


def write_chunk_embeddings(chunks: list[dict], out_path: Path,
                           device: Optional[str] = None) -> int:
    """给全部 chunk 编码并存 npz（key='vectors'，顺序 == chunk 顺序）。返回条数。"""
    import numpy as np
    texts = [chunk_text_for_embedding(c) for c in chunks]
    vecs = encode_texts(texts, device=device)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, vectors=np.asarray(vecs, dtype=np.float32))
    return len(texts)


def load_chunk_embeddings(path: Path) -> Optional[list[list[float]]]:
    """读 npz → list[list[float]]；文件缺失/损坏返回 None（上层回落 BM25）。"""
    try:
        import numpy as np
        data = np.load(str(path))
        return [[float(x) for x in row] for row in data["vectors"]]
    except Exception:
        return None
