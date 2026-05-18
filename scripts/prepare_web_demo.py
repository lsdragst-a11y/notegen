"""把 5 个 demo 视频的产出拷贝到 web/public 供前端 fetch。

Backend stem (BV 号) 含 dots / 较长，前端用 short_id 替代作 URL。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (short_id, backend_stem, video_filename, display_title_fallback, domain)
DEMOS = [
    ("python", "BV1Sz4y1U77N_p0", "BV1Sz4y1U77N_p0.mp4",
     "20 分钟学完 Python 基础", "编程教学"),
    ("os", "BV1YE411D7nH_p37_p0", "BV1YE411D7nH_p37_p0.mp4",
     "操作系统：哲学家进餐问题", "考研专业课"),
    ("claudecode", "BV1SddcBFESs_p0", "BV1SddcBFESs_p0.mp4",
     "10 分钟学会 Claude Code", "工具教程"),
    ("network", "BV19E411D78Q_p38.f30280", "BV19E411D78Q_p38.f100023.mp4",
     "计算机网络：以太网与 MAC 帧", "考研专业课"),
    ("linear-algebra", "BV1Vi5Q66EYo_p0", "BV1Vi5Q66EYo_p0.mp4",
     "考研数一线性代数指南", "考研专业课"),
]


def main():
    web_pub = ROOT / "web" / "public"
    (web_pub / "videos").mkdir(parents=True, exist_ok=True)
    notes_root = web_pub / "notes"
    notes_root.mkdir(parents=True, exist_ok=True)

    catalog = []
    for short_id, stem, video, title, domain in DEMOS:
        out = notes_root / short_id
        out.mkdir(parents=True, exist_ok=True)

        # summary.json + chapters.json
        for kind in ("summary", "chapters"):
            src = ROOT / "data" / "outputs" / f"{stem}.large-v3.neural.texttile.{kind}.json"
            if src.exists():
                shutil.copy(src, out / f"{kind}.json")

        # meta.json (raw/<video_stem>.meta.json, video_stem 是去掉 .f30280 这种后缀的纯 BV 号)
        meta_stem = stem.split(".")[0]
        meta_src = ROOT / "data" / "raw" / f"{meta_stem}.meta.json"
        meta_data = None
        if meta_src.exists():
            shutil.copy(meta_src, out / "meta.json")
            try:
                meta_data = json.loads(meta_src.read_text(encoding="utf-8"))
            except Exception:
                pass

        # keyframes 目录
        kf_src = ROOT / "data" / "outputs" / f"{stem}.large-v3.neural.texttile.keyframes"
        if kf_src.exists():
            kf_dst = out / "keyframes"
            if kf_dst.exists():
                shutil.rmtree(kf_dst)
            shutil.copytree(kf_src, kf_dst)

        # video
        vid_src = ROOT / "data" / "raw" / video
        vid_size_mb = None
        if vid_src.exists():
            vid_dst = web_pub / "videos" / f"{short_id}.mp4"
            shutil.copy(vid_src, vid_dst)
            vid_size_mb = vid_dst.stat().st_size / 1024 / 1024

        # 拼 catalog 项
        try:
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            chapters = json.loads((out / "chapters.json").read_text(encoding="utf-8"))
            n_chunks = len(summary)
            n_chapters = len(chapters.get("chapters", []))
            duration_sec = summary[-1].get("end", 0) if summary else 0
        except Exception:
            n_chunks = n_chapters = 0
            duration_sec = 0

        catalog.append({
            "id": short_id,
            "title": (meta_data or {}).get("title", title),
            "domain": domain,
            "duration_sec": int(duration_sec),
            "chunks": n_chunks,
            "chapters": n_chapters,
            "uploader": (meta_data or {}).get("uploader", ""),
            "webpage_url": (meta_data or {}).get("webpage_url", ""),
            "video_size_mb": round(vid_size_mb, 1) if vid_size_mb else None,
        })
        print(f"  {short_id}: chunks={n_chunks} chapters={n_chapters} "
              f"dur={int(duration_sec)}s video={vid_size_mb and f'{vid_size_mb:.1f}MB'}")

    # 写一个总 catalog 文件供 landing 页 fetch
    (notes_root / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] catalog -> {notes_root / 'catalog.json'}")


if __name__ == "__main__":
    main()
