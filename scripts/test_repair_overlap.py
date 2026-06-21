"""Offline pure-function test for the cross-chapter overlap repair fix.
No GPU / no model load. Verifies _repair_overlap + the repair chain ordering
resolves the p79 boundary-repeat-overlap + oversize signature instead of
falling back to TextTiling. Run: .venv/Scripts/python.exe scripts/_test_repair_overlap.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import segment_llm as S

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

CAP = S.CAP_TEACHING  # 5
N = 17
# 17 dummy chunks, no keywords (forces _repair_oversize even-ish split, fine for validity)
CHUNKS = [{"text": f"c{i}", "keywords": []} for i in range(N)]

def run_chain(parsed, with_overlap_fix):
    """Replicate the production repair chain ordering (segment_llm.py ~L1469)."""
    if with_overlap_fix:
        parsed, _ = S._repair_overlap(parsed, N)
    repaired = S._repair_missing_chunks(parsed, N)
    if repaired is None:
        return None, "missing-returned-None"
    repaired = S._promote_oversized(repaired, max_chunks_per_top=CAP)
    repaired = S._repair_oversize(repaired, CHUNKS, max_chunks_per_top=CAP)
    min_required = 3
    if len(repaired.get("chapters") or []) < min_required:
        repaired = S._repair_too_few_chapters(repaired, CHUNKS,
                                              min_required=min_required,
                                              max_chunks_per_top=CAP)
    err = S._diagnose_outline(repaired, N, category="teaching")
    return repaired, err

# ---- (a) p79-like: boundary-repeat overlap + a 7-chunk oversize chapter ----
def p79_like():
    return {"chapters": [
        {"title": "A", "chunks": [0, 1]},
        {"title": "B", "chunks": [1, 2, 3]},
        {"title": "C", "chunks": [3, 4, 5]},
        {"title": "D", "chunks": [5, 6, 7]},
        {"title": "E", "chunks": [7, 8, 9, 10]},
        {"title": "F", "chunks": [10, 11, 12, 13, 14, 15, 16]},  # 7 -> oversize
    ]}

# OLD chain (no overlap fix) must still FAIL with a duplicate/overlap error.
old_out, old_err = run_chain(p79_like(), with_overlap_fix=False)
check(old_err is not None and ("多个顶层" in old_err or "重叠" in old_err or "重复覆盖" in old_err),
      f"(a) OLD chain still fails on overlap -> got: {old_err!r}")

# NEW chain (with overlap fix) must PASS validation.
new_out, new_err = run_chain(p79_like(), with_overlap_fix=True)
check(new_err is None, f"(a) NEW chain passes diagnose -> err={new_err!r}")
if new_err is None:
    chs = new_out["chapters"]
    allc = [c for ch in chs for c in ch["chunks"]]
    check(sorted(allc) == list(range(N)), "(a) covers 0..16 exactly")
    check(len(allc) == len(set(allc)), "(a) no cross-chapter duplicates")
    check(all(c["chunks"] == list(range(min(c["chunks"]), max(c["chunks"]) + 1))
              for c in chs), "(a) every chapter is a contiguous range")
    check(all(len(c["chunks"]) <= CAP for c in chs), f"(a) no chapter > {CAP} chunks")
    check(len(chs) >= 3, "(a) >= 3 top chapters")
    print("    (a) NEW partition:", [(c["title"], c["chunks"]) for c in chs])

# ---- (b) chapter fully emptied by de-overlap must be dropped ----
b_in = {"chapters": [
    {"title": "A", "chunks": [5, 6]},
    {"title": "B", "chunks": [6]},          # fully absorbed by A
    {"title": "C", "chunks": [7, 8]},
]}
b_out, b_changed = S._repair_overlap(b_in, N)
titles = [c["title"] for c in b_out["chapters"]]
check(b_changed and "B" not in titles and titles == ["A", "C"],
      f"(b) emptied chapter dropped -> titles={titles}")

# ---- (c) chunk in 3 chapters -> kept only in earliest ----
c_in = {"chapters": [
    {"title": "A", "chunks": [0, 1]},
    {"title": "B", "chunks": [1, 2]},
    {"title": "C", "chunks": [1, 2, 3]},
]}
c_out, c_changed = S._repair_overlap(c_in, N)
sets = [ch["chunks"] for ch in c_out["chapters"]]
flat = [x for s in sets for x in s]
check(c_changed and flat == [0, 1, 2, 3] and len(flat) == len(set(flat)),
      f"(c) triple overlap resolved keep-earliest -> {sets}")

# ---- (d) no overlap -> unchanged, identity preserved ----
d_in = {"chapters": [
    {"title": "A", "chunks": [0, 1]},
    {"title": "B", "chunks": [2, 3]},
]}
d_out, d_changed = S._repair_overlap(d_in, N)
check(d_changed is False and d_out is d_in, "(d) no-overlap passthrough (unchanged)")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
