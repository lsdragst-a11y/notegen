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
USER_NOTES_DIR = ROOT / "data" / "user_notes"

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


def _guess_domain(title: str) -> str:
    t = (title or "").lower()
    if "python" in t or "代码" in t or "编程" in t:
        return "编程教学"
    if "考研" in t or "操作系统" in t or "计算机网络" in t or "线代" in t or "线性代数" in t:
        return "考研专业课"
    if "vlog" in t or "日常" in t or "外卖" in t or "小镇" in t:
        return "Vlog"
    if "评测" in t or "iphone" in t or "ios" in t:
        return "数码评测"
    return "学习"


def _copy_artifacts(stem: str, note_dir: Path) -> None:
    """把 outputs 的 summary/chapters/keyframes + raw 的 meta.json copy 进 note_dir。"""
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
        [p for p in DATA_OUTPUTS.glob(f"{stem}.large-v3.neural.texttile*.keyframes")
         if p.is_dir()], key=lambda p: -p.stat().st_mtime)
    if kf_candidates:
        kf_dst = note_dir / "keyframes"
        kf_dst.mkdir(parents=True, exist_ok=True)
        for f in kf_candidates[0].iterdir():
            if f.is_file():
                try:
                    shutil.copy(f, kf_dst / f.name)
                except PermissionError:
                    pass


def _find_source_video(stem: str) -> Optional[Path]:
    meta_stem = stem.split(".")[0]
    for cand in [DATA_RAW / f"{meta_stem}_p0.mp4",
                 DATA_RAW / f"{meta_stem}.mp4",
                 *DATA_RAW.glob(f"{meta_stem}*.mp4")]:
        if cand.exists():
            return cand
    return None


def extract_note_fields(note_dir: Path) -> dict:
    """从 note_dir 的 summary/chapters/meta 读出列表展示冗余字段。"""
    import json
    title = note_dir.name
    uploader = webpage_url = ""
    duration_sec = chunks = chapters = 0
    sp = note_dir / "summary.json"
    if sp.exists():
        try:
            summary = json.loads(sp.read_text(encoding="utf-8"))
            chunks = len(summary)
            if summary:
                duration_sec = int(summary[-1].get("end", 0))
        except Exception:
            pass
    cp = note_dir / "chapters.json"
    if cp.exists():
        try:
            chapters = len(json.loads(cp.read_text(encoding="utf-8")).get("chapters", []))
        except Exception:
            pass
    mp = note_dir / "meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            title = meta.get("title") or title
            uploader = meta.get("uploader", "")
            webpage_url = meta.get("webpage_url", "")
        except Exception:
            pass
    return {"title": title, "domain": _guess_domain(title),
            "duration_sec": duration_sec, "chunks": chunks, "chapters": chapters,
            "uploader": uploader, "webpage_url": webpage_url}


def publish_to_web(stem: str) -> str:
    """公开发布：copy 产物到 web/public/{notes,videos}/，返回 note_id。
    （公开展示区/admin 用；新用户生成走 publish_private。）"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    note_dir = NOTES_DIR / stem
    _copy_artifacts(stem, note_dir)
    vid = _find_source_video(stem)
    if vid:
        shutil.copy(vid, VIDEOS_DIR / f"{stem}.mp4")
    return stem


def publish_private(stem: str, user_id: str) -> tuple[str, str, dict]:
    """私有发布：copy 产物 + 视频(video.mp4) 到 data/user_notes/{uid}/{stem}/（公开静态不可达）。
    返回 (note_id, storage_path, 展示字段 dict)。"""
    note_dir = USER_NOTES_DIR / user_id / stem
    _copy_artifacts(stem, note_dir)
    vid = _find_source_video(stem)
    if vid:
        shutil.copy(vid, note_dir / "video.mp4")
    return stem, str(note_dir), extract_note_fields(note_dir)
