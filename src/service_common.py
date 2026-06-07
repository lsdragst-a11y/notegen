"""server.py 与 worker_tasks.py 共用的纯/IO helper：路径常量、画质归一、
chunk 粒度、估时、ffprobe 时长、产物 publish 到 web/public。
（原先散在 server.py，提取以便 worker 进程复用。）"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WEB_PUBLIC = ROOT / "web" / "public"
NOTES_DIR = WEB_PUBLIC / "notes"
VIDEOS_DIR = WEB_PUBLIC / "videos"
DATA_OUTPUTS = ROOT / "data" / "outputs"
DATA_RAW = ROOT / "data" / "raw"

_QUALITY_RE = re.compile(r"^(?:best|\d{2,4}p)$")


def normalize_quality(q: Optional[str]) -> str:
    """白名单：'best' or 'NNNp'；非法 → 'best'。"""
    if not q:
        return "best"
    s = q.strip().lower()
    return s if _QUALITY_RE.match(s) else "best"


def adaptive_chunk_chars(video_duration_sec: float) -> int:
    """按视频时长选 chunker 字符上限。"""
    if video_duration_sec <= 0:
        return 800
    if video_duration_sec < 600:
        return 400
    if video_duration_sec < 1500:
        return 600
    return 800


def estimate_pipeline_seconds(video_duration_sec: float) -> int:
    """经验估时（秒）：下载抽音频固定 ~25s + ASR ~0.45x + 后处理 30 + 0.04x。"""
    return int(25 + video_duration_sec * 0.45 + 30 + video_duration_sec * 0.04)


def probe_duration(video_path: Path) -> float:
    """ffprobe 探本地视频时长（秒）。失败返回 0。"""
    try:
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            ffprobe = str(Path(ffmpeg_bin).with_name("ffprobe.exe"))
        else:
            ffprobe = "ffprobe"
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        return float((r.stdout or "").strip() or 0)
    except Exception:
        return 0.0


def publish_to_web(stem: str) -> str:
    """把 data/outputs/{stem}.* + data/raw/{stem}.mp4 copy 到 web/public，返回 note_id。"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    short_id = stem
    note_dir = NOTES_DIR / short_id
    note_dir.mkdir(parents=True, exist_ok=True)

    def _pick_latest(pattern: str) -> Optional[Path]:
        cands = sorted(DATA_OUTPUTS.glob(pattern), key=lambda p: -p.stat().st_mtime)
        return cands[0] if cands else None

    for kind in ("summary", "chapters"):
        src = _pick_latest(f"{stem}.large-v3.neural.texttile*.{kind}.json")
        if src:
            shutil.copy(src, note_dir / f"{kind}.json")

    meta_stem = stem.split(".")[0]
    meta_src = DATA_RAW / f"{meta_stem}.meta.json"
    if meta_src.exists():
        shutil.copy(meta_src, note_dir / "meta.json")

    kf_candidates = sorted(
        [p for p in DATA_OUTPUTS.glob(f"{stem}.large-v3.neural.texttile*.keyframes") if p.is_dir()],
        key=lambda p: -p.stat().st_mtime,
    )
    kf_src = kf_candidates[0] if kf_candidates else None
    if kf_src:
        kf_dst = note_dir / "keyframes"
        kf_dst.mkdir(parents=True, exist_ok=True)
        for f in kf_src.iterdir():
            if f.is_file():
                try:
                    shutil.copy(f, kf_dst / f.name)
                except PermissionError:
                    pass

    for cand in [DATA_RAW / f"{meta_stem}_p0.mp4",
                 DATA_RAW / f"{meta_stem}.mp4",
                 *DATA_RAW.glob(f"{meta_stem}*.mp4")]:
        if cand.exists():
            shutil.copy(cand, VIDEOS_DIR / f"{short_id}.mp4")
            break
    return short_id
