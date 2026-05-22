"""下载视频并抽取 16kHz 单声道音频。"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

RAW_DIR = Path("data/raw")
AUDIO_DIR = Path("data/audio")
COOKIES_DIR = Path("data/.cookies")


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


def _detect_host(url: str) -> str:
    """从 URL 推断站点 key。"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return "youtube"
    if "bilibili.com" in host or host.endswith("b23.tv"):
        return "bilibili"
    if "youtube.com" in host or host == "youtu.be":
        return "youtube"
    return "youtube"


class _SilentLogger(logging.Logger):
    """喂给 yt_dlp.cookies 让 DPAPI 失败等 noise 不刷屏。"""
    def __init__(self):
        super().__init__("silent-cookies", logging.CRITICAL + 1)
    def debug(self, *a, **kw): pass
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass


_SILENT = _SilentLogger()


def _has_bilibili_session(browser: str) -> bool:
    """Browser cookie jar 是否含 bilibili.com 的 SESSDATA（登录态最关键字段）。
    Edge/Chrome 在 Windows 较新版上因 DPAPI 锁定常失败，Firefox 不受影响。"""
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
        jar = extract_cookies_from_browser(browser, logger=_SILENT)
    except Exception:
        return False
    for c in jar:
        dom = (c.domain or "").lstrip(".")
        if dom.endswith("bilibili.com") and c.name == "SESSDATA" and c.value:
            return True
    return False


# host_key → (cache_attr, cookies_file_glob_patterns, login_probe_fn)
# glob patterns 兼容 'Get cookies.txt LOCALLY' 扩展默认导出名（www.bilibili.com_cookies.txt 等）
_HOST_PROBES = {
    "bilibili": ("_bili_cache",
                 ["bilibili.txt", "*bilibili*.txt"],
                 _has_bilibili_session),
}


def _resolve_cookies_for(host_key: str) -> Optional[Tuple[str, str]]:
    """返回 ('file', path) 或 ('browser', name) 或 None。

    优先级：
      1) data/.cookies/<host>.txt （用户浏览器扩展导出的 Netscape 格式）
      2) 各浏览器探测 — 用 host 特定 login probe 检查 SESSDATA / 等价 sentinel
      3) None → caller 走无 cookie 路径（公开内容能下，但 B 站画质卡 480p）

    Windows Chrome/Edge 自 v127 起 cookie 数据库被 DPAPI app-bound 加密，
    yt-dlp 现版本读不到（issue #10927）。Firefox 不受影响，是 Win 上唯一稳的浏览器路。
    """
    if host_key not in _HOST_PROBES:
        return None  # 未注册的 host（YouTube 走旧 _resolve_browser_cookies）
    cache_attr, file_patterns, probe_fn = _HOST_PROBES[host_key]
    cached = getattr(_resolve_cookies_for, cache_attr, "_unset")
    if cached != "_unset":
        return cached  # type: ignore[return-value]

    # 1) cookies 文件 — 按 pattern 顺序找第一个存在且含 SESSDATA 的
    candidates: list[Path] = []
    for pat in file_patterns:
        if any(ch in pat for ch in "*?["):
            candidates.extend(sorted(COOKIES_DIR.glob(pat)))
        else:
            p = COOKIES_DIR / pat
            if p.exists():
                candidates.append(p)
    seen: set[Path] = set()
    for fp in candidates:
        if fp in seen:
            continue
        seen.add(fp)
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
            if "SESSDATA" in content:
                print(f"      [cookies] {host_key}: 使用 {fp}", flush=True)
                result = ("file", str(fp))
                setattr(_resolve_cookies_for, cache_attr, result)
                return result
        except Exception as e:
            print(f"      [cookies] {host_key}: 读 {fp} 失败 ({e})，跳过", flush=True)

    # 2) 浏览器探测
    for b in _BROWSER_CANDIDATES:
        if probe_fn(b):
            print(f"      [cookies] {host_key}: 使用浏览器 {b}", flush=True)
            result = ("browser", b)
            setattr(_resolve_cookies_for, cache_attr, result)
            return result

    # 3) 没有可用 cookie — actionable warning
    if host_key == "bilibili":
        print(
            "      [cookies] bilibili: ⚠ 没找到登录态，画质上限 480p。\n"
            "        修复路径（任选其一）：\n"
            "        1) Firefox 登录 b 站后重跑（Windows 下 Edge/Chrome 因 DPAPI 锁\n"
            "           定，yt-dlp 读不到）；\n"
            "        2) 浏览器扩展 'Get cookies.txt LOCALLY' 在 bilibili.com 页面导\n"
            f"           出，保存为 {fp}；\n"
            "        3) 接受 480p（NoteGen ASR/VL 用 480p 完全够，仅原档观看会差）",
            flush=True,
        )
    setattr(_resolve_cookies_for, cache_attr, None)
    return None


def _resolve_browser_cookies() -> Optional[str]:
    """YouTube 专用旧探测路径（保留向后兼容）。
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


def _yt_dlp_cookie_opts(url: str) -> dict:
    """根据 URL host 返回 yt-dlp options dict 的 cookie 部分。"""
    host_key = _detect_host(url)
    if host_key in _HOST_PROBES:
        src = _resolve_cookies_for(host_key)
        if src:
            kind, val = src
            return {"cookiefile": val} if kind == "file" else {"cookiesfrombrowser": (val,)}
        return {}
    # YouTube fallback
    browser = _resolve_browser_cookies()
    return {"cookiesfrombrowser": (browser,)} if browser else {}


def _cli_cookie_args(url: str) -> list[str]:
    """根据 URL host 返回 yt-dlp CLI args 的 cookie 参数。"""
    host_key = _detect_host(url)
    if host_key in _HOST_PROBES:
        src = _resolve_cookies_for(host_key)
        if src:
            kind, val = src
            return ["--cookies", val] if kind == "file" else ["--cookies-from-browser", val]
        return []
    browser = _resolve_browser_cookies()
    return ["--cookies-from-browser", browser] if browser else []


def fetch_metadata(url: str) -> dict:
    """不下载文件，只取标题 / 描述 / id 等元数据。供 ASR 用作 initial_prompt。"""
    import yt_dlp
    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    opts.update(_yt_dlp_cookie_opts(url))
    with yt_dlp.YoutubeDL(opts) as y:
        return y.extract_info(url, download=False)


_QUALITY_RE = re.compile(r"^(\d{2,4})p$")


def _quality_to_format(quality: str) -> str:
    """画质字符串 → yt-dlp -f 表达式。
    支持 'best' 或 'NNNp'（任意 height，e.g. '1080p', '720p', '480p'）。
    NoteGen 实际只用 ASR 音频 + 关键帧 caption，720p 已足 PPT OCR；
    1080p+ 仅当用户想保留原档观看才有价值。"""
    if quality in ("best", "", None):
        return "bv*+ba/b"
    m = _QUALITY_RE.match(str(quality).lower())
    if m:
        h = int(m.group(1))
        return f"bv*[height<={h}]+ba/b[height<={h}]/b"
    return "bv*+ba/b"


def probe_qualities(url: str) -> dict:
    """探测 URL 实际可下的画质 list + 元信息。供前端在用户确认前展示。

    返回：
      {ok: bool, error?: str, title, uploader, duration,
       heights: [int 降序去重], cookie_status: 'ok' | 'missing'}
    heights 为空 → 公开视频探测失败 / 没有视频流。
    """
    host = _detect_host(url)
    cookie_src = _resolve_cookies_for(host) if host in _HOST_PROBES else None
    cookie_status = "ok" if cookie_src else "missing"
    import yt_dlp
    # noplaylist=True 关键：B 站 anthology（多 P 合集）默认会被 yt-dlp 当 playlist
    # 展开，顶层 info 没有 formats（formats 在 entries[i] 里），导致 heights=[]
    # 误判 "没有可用画质"。强制按单视频提取，与 download_video 的 --no-playlist 对齐
    opts = {"skip_download": True, "quiet": True, "no_warnings": True,
            "noplaylist": True}
    opts.update(_yt_dlp_cookie_opts(url))
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200],
                "title": "", "uploader": "", "duration": 0,
                "heights": [], "cookie_status": cookie_status}
    # 兜底：极个别 extractor 即使 noplaylist=True 仍返回 playlist（旧版 yt-dlp /
    # 某些 host），取第一个 entry 作为单视频信息
    if info.get("_type") == "playlist" or (not info.get("formats") and info.get("entries")):
        entries = list(info.get("entries") or [])
        if entries:
            info = entries[0] or info
    formats = info.get("formats") or []
    heights = sorted(
        {int(f["height"]) for f in formats
         if isinstance(f.get("height"), int) and f.get("vcodec") not in (None, "none")},
        reverse=True,
    )
    return {
        "ok": True,
        "title": info.get("title", "") or "",
        "uploader": info.get("uploader", "") or "",
        "duration": int(info.get("duration") or 0),
        "heights": heights,
        "cookie_status": cookie_status,
    }


def download_video(url: str, out_dir: Path | str = RAW_DIR,
                   *, quality: str = "best") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = _quality_to_format(quality)

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "-o", f"{out_dir.as_posix()}/%(id)s_p%(playlist_index|0)s.%(ext)s",
        "--print", "after_move:filepath",
        "--no-simulate",
        "--no-playlist",
    ]
    cmd += _cli_cookie_args(url)
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
