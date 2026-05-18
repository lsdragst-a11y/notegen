"""Quick automated smoke tests for NoteGen (no GPU-heavy pipeline)."""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

FAILURES: list[str] = []
WARNINGS: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"  WARN {msg}")


def test_imports() -> None:
    print("\n=== module imports ===")
    mods = [
        "download", "asr", "summarize", "summarize_neural",
        "segment", "keyframe", "slide", "pipeline",
    ]
    for m in mods:
        try:
            importlib.import_module(m)
            ok(m)
        except Exception as e:
            fail(f"import {m}: {e}")


def test_server_md_stem_regex() -> None:
    """_publish_to_web expects audio stem (before .large-v3), not full output stem."""
    print("\n=== server.py md_path regex ===")
    line = r"\n[OK] 完成! 笔记: data\outputs\BV1SddcBFESs_p0.large-v3.neural.texttile.md"
    pat = re.compile(r"data[\\/]outputs[\\/]([^\\/]+)\.large-v3")
    m = pat.search(line)
    if not m:
        fail("regex did not match pipeline [OK] line")
        return
    audio_stem = m.group(1)
    publish_src = ROOT / "data" / "outputs" / f"{audio_stem}.large-v3.neural.texttile.summary.json"
    ok(f"captured audio_stem = {audio_stem!r}")
    if audio_stem != "BV1SddcBFESs_p0":
        fail(f"unexpected audio stem: {audio_stem!r}")
    elif not publish_src.exists():
        fail(f"_publish_to_web source missing: {publish_src}")
    else:
        ok("_publish_to_web path resolves to existing summary.json")


def test_cached_outputs_schema() -> None:
    print("\n=== cached output JSON schema ===")
    out = ROOT / "data" / "outputs"
    samples = list(out.glob("*.large-v3.neural.texttile.summary.json"))[:5]
    if not samples:
        warn("no neural.texttile summary files to validate")
        return
    for p in samples:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list) or not data:
                fail(f"{p.name}: not a non-empty list")
                continue
            c0 = data[0]
            for key in ("start", "end", "text"):
                if key not in c0:
                    fail(f"{p.name}: chunk missing {key}")
                    break
            else:
                ok(p.name)
        except Exception as e:
            fail(f"{p.name}: {e}")


def test_regen_md() -> None:
    print("\n=== regen_md (to_markdown) ===")
    stem = "BV1G85V6cE1g_p0.large-v3.neural.texttile"
    p = ROOT / "data" / "outputs" / f"{stem}.summary.json"
    if not p.exists():
        warn(f"skip regen: {p} missing")
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from regen_md import regen  # type: ignore
        out = regen(stem, learning_mode=True)
        if not out.exists() or out.stat().st_size < 100:
            fail(f"regen produced empty md: {out}")
        else:
            ok(f"regen -> {out.name} ({out.stat().st_size} bytes)")
    except Exception as e:
        fail(f"regen_md: {e}")


def test_segment_on_cache() -> None:
    print("\n=== segment detect_boundaries (text-only) ===")
    asr_p = ROOT / "data" / "outputs" / "BV1G85V6cE1g_p0.large-v3.asr.json"
    if not asr_p.exists():
        warn("skip segment: no BV1G85V6cE1g ASR cache")
        return
    from asr import dedupe_consecutive_segments
    from summarize import chunk_by_texttile, keywords_for
    from segment import detect_boundaries

    asr = json.loads(asr_p.read_text(encoding="utf-8"))
    segs = dedupe_consecutive_segments(asr)[0]["segments"]
    chunks = chunk_by_texttile(segs, target_chunk_chars=800)
    for c in chunks:
        c["keywords"] = keywords_for(c["text"])
    bounds = detect_boundaries(chunks)
    if not isinstance(bounds, list):
        fail(f"bounds not list: {type(bounds)}")
    elif any(b < 0 or b >= len(chunks) for b in bounds):
        fail(f"invalid boundary indices: {bounds} for n_chunks={len(chunks)}")
    else:
        ok(f"n_chunks={len(chunks)} auto_K={len(bounds)+1} bounds={bounds}")


def main() -> int:
    print("NoteGen smoke_test")
    test_imports()
    test_server_md_stem_regex()
    test_cached_outputs_schema()
    test_regen_md()
    test_segment_on_cache()
    print("\n=== summary ===")
    print(f"failures: {len(FAILURES)}")
    print(f"warnings: {len(WARNINGS)}")
    for f in FAILURES:
        print(f"  - {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
