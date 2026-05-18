"""一次性脚本：用新的 domain-aware initial_prompt 重跑指定视频的 ASR，
然后 dry-print 帧/针 计数对比。

usage:
    python scripts/rerun_asr_with_hotword.py BV19E411D78Q_p44_p0
"""
from __future__ import annotations
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pipeline import _build_asr_prompt, _detect_domains  # noqa
from asr import transcribe  # noqa

META_DIR = ROOT / "data" / "raw"
AUDIO_DIR = ROOT / "data" / "audio"


def main():
    stem = sys.argv[1]  # e.g. BV19E411D78Q_p44_p0
    meta_path = META_DIR / f"{stem}.meta.json"
    audio_path = AUDIO_DIR / f"{stem}.wav"
    if not meta_path.exists():
        print(f"meta 不存在: {meta_path}")
        sys.exit(1)
    if not audio_path.exists():
        print(f"audio 不存在: {audio_path}")
        sys.exit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    prompt = _build_asr_prompt(meta)
    print(f"domains: {_detect_domains(meta)}")
    print(f"prompt ({len(prompt)} chars): {prompt}")
    print()
    print("跑 ASR (large-v3) ...")
    res = transcribe(audio_path, initial_prompt=prompt)
    zhen = sum(1 for s in res["segments"] if "针" in s["text"])
    zheng = sum(1 for s in res["segments"] if "帧" in s["text"])
    print(f"\n结果对比:")
    print(f"  segments with 针: {zhen}")
    print(f"  segments with 帧: {zheng}")
    print(f"  total segments:  {len(res['segments'])}")


if __name__ == "__main__":
    main()
