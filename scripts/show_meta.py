"""打 B 站视频 metadata 看是否合适加入 benchmark（UTF-8 输出）。"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from download import fetch_metadata  # noqa: E402


def main():
    for url in sys.argv[1:]:
        try:
            m = fetch_metadata(url)
        except Exception as e:
            print(f"[FAIL] {url}: {e}")
            continue
        dur = m.get("duration", 0)
        print(f"\n=== {m.get('id', '?')} ===")
        print(f"  title    : {m.get('title')}")
        print(f"  uploader : {m.get('uploader')}")
        print(f"  duration : {dur}s ≈ {dur // 60}min {dur % 60}s")
        desc = (m.get("description") or "").strip()
        print(f"  desc[:300]: {desc[:300]}")


if __name__ == "__main__":
    main()
