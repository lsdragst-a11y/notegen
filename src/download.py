"""下载视频并抽取 16kHz 单声道音频。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

RAW_DIR = Path("data/raw")
AUDIO_DIR = Path("data/audio")


def _find_ffmpeg() -> str:
    """优先 PATH，回退到 winget 默认安装位置。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin/ffmpeg.exe",
        Path("C:/ProgramData/chocolatey/bin/ffmpeg.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError("找不到 ffmpeg，请装 ffmpeg 并加到 PATH")


# YouTube 自 2024 年起对无 cookie 请求严反爬（"Sign in to confirm you're not a bot"）。
# 从用户浏览器借 cookie 是最稳的绕过方案。按 Windows 默认顺序试 edge → chrome → firefox。
# 用户未登录任何浏览器时全失败，会返回 None 让 caller 走无 cookie 路径（小视频可能通过）。
_BROWSER_CANDIDATES = ("edge", "chrome", "firefox", "brave", "opera")


def _resolve_browser_cookies() -> Optional[str]:
    """探测哪个浏览器有可读 YouTube cookies + 实际登录态。第一次调用时缓存结果。
    探测 URL 用 YouTube 自家"我的频道"——未登录态会被重定向，未登录的 Firefox
    在公开视频测试上能"通过"但实际下载失败（被反爬挡）。"""
    if hasattr(_resolve_browser_cookies, "_cache"):
        return _resolve_browser_cookies._cache  # type: ignore[attr-defined]
    import yt_dlp
    probe_url = "https://www.youtube.com/feed/library"  # 登录态才能访问
    for b in _BROWSER_CANDIDATES:
        try:
            opts = {"skip_download": True, "quiet": True, "no_warnings": True,
                    "cookiesfrombrowser": (b,)}
            with yt_dlp.YoutubeDL(opts) as y:
                y.extract_info(probe_url, download=False)
            print(f"      [cookies] using browser: {b}", flush=True)
            _resolve_browser_cookies._cache = b  # type: ignore[attr-defined]
            return b
        except Exception:
            continue
    print("      [cookies] no usable browser cookies found, "
          "trying no-cookie path", flush=True)
    _resolve_browser_cookies._cache = None  # type: ignore[attr-defined]
    return None


def fetch_metadata(url: str) -> dict:
    """不下载文件，只取标题 / 描述 / id 等元数据。供 ASR 用作 initial_prompt。"""
    import yt_dlp
    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    browser = _resolve_browser_cookies()
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    with yt_dlp.YoutubeDL(opts) as y:
        return y.extract_info(url, download=False)


def download_video(url: str, out_dir: Path | str = RAW_DIR) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    browser = _resolve_browser_cookies()
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", f"{out_dir.as_posix()}/%(id)s_p%(playlist_index|0)s.%(ext)s",
        "--print", "after_move:filepath",
        "--no-simulate",
        "--no-playlist",
    ]
    if browser:
        cmd += ["--cookies-from-browser", browser]
    cmd.append(url)
    result = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    paths = [p for p in paths if Path(p).exists()]
    if not paths:
        raise RuntimeError(f"yt-dlp 未输出文件路径\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    # --no-playlist 已加，正常单视频应只返回 1 个 path。多个 path 通常意味着 URL
    # 走了 playlist 分支（曾因 ?p= 缺失把 39 集英语播客全下载，最后取 paths[-1]
    # 拿到 p39 内容、跟用户意图错位）。fail fast 暴露问题而非默默取末位。
    if len(paths) > 1:
        raise RuntimeError(
            f"yt-dlp 输出多个 file path ({len(paths)} 个)，可能触发了 playlist 模式。"
            f"检查 URL 是否带 ?p=N 指定单集。\npaths:\n  " + "\n  ".join(paths)
        )
    return Path(paths[0])


def extract_audio(video_path: Path | str, out_dir: Path | str = AUDIO_DIR,
                  force: bool = False) -> Path:
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{video_path.stem}.wav"

    if audio_path.exists() and not force and \
            audio_path.stat().st_mtime >= video_path.stat().st_mtime:
        return audio_path

    ffmpeg = _find_ffmpeg()
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(audio_path),
        ],
        check=True,
    )
    return audio_path


if __name__ == "__main__":
    import sys
    video = download_video(sys.argv[1])
    audio = extract_audio(video)
    print(f"video: {video}\naudio: {audio}")
