"""Stress test: 强制 LLM 反复输出"倔强单顶层"，验证 auto_subs 兜底是否触发。

不调真 Qwen — monkey-patch segment_llm.load_model 返回 (FakeModel, FakeTok)，
让 decode() 按 call counter 吐预设字符串。

跑法:
  cd E:\\claudeproject\\notegen
  .venv\\Scripts\\python.exe scripts\\stress_test_auto_subs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import segment_llm as sl  # noqa: E402


class _FakeInputs(dict):
    def to(self, device):
        return self


class FakeTok:
    eos_token_id = 0
    decode_calls = 0
    next_decode_returns: list[str] = []

    def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=True):
        return "<fake_prompt>"

    def __call__(self, text, return_tensors="pt"):
        return _FakeInputs(input_ids=torch.tensor([[1, 2, 3, 4, 5]]))

    def decode(self, ids, skip_special_tokens=True):
        idx = self.decode_calls
        FakeTok.decode_calls += 1
        if idx < len(self.next_decode_returns):
            return self.next_decode_returns[idx]
        return ""


class FakeModel:
    device = "cpu"

    def generate(self, input_ids=None, **kw):
        gen_tail = torch.tensor([[100, 101, 102, 103]])
        return torch.cat([input_ids, gen_tail], dim=1)

    def eval(self):
        return self


def make_chunks(n: int) -> list[dict]:
    out = []
    for i in range(n):
        out.append({
            "start": float(i * 60),
            "end": float((i + 1) * 60),
            "headline": f"第{i+1}段主题",
            "text": f"段{i+1}的样本文本内容，仅供 stress test。",
            "keywords": [f"kw{i}a", f"kw{i}b", f"kw{i}c"],
        })
    return out


def run_case(name: str, n: int, decode_returns: list[str], expect_auto_subs: bool,
             expect_top_count: int | None = None,
             expect_children_count: int | None = None):
    """跑一个 case，对照预期断言。"""
    sl._MODEL = None
    sl._TOKENIZER = None
    fake_tok = FakeTok()
    fake_tok.next_decode_returns = list(decode_returns)
    FakeTok.decode_calls = 0
    fake_model = FakeModel()

    def fake_load(model_id=sl._DEFAULT_MODEL):
        return fake_model, fake_tok

    sl.load_model = fake_load

    chunks = make_chunks(n)
    print(f"\n{'='*60}")
    print(f"CASE: {name} (n={n}, expect_auto_subs={expect_auto_subs})")
    print(f"{'='*60}")
    out = sl.segment_hierarchical(
        chunks,
        headlines=[c["headline"] for c in chunks],
        category="teaching",
        lang="zh",
        max_retries=2,  # 0/1/2 = 3 attempts
    )

    meta = out.get("_meta") if isinstance(out, dict) else None
    chapters = out.get("chapters") if isinstance(out, dict) else None
    print(f"\n--- RESULT for {name} ---")
    print(f"meta: {json.dumps(meta, ensure_ascii=False)}")
    if chapters:
        for ci, ch in enumerate(chapters):
            kids = ch.get("children") or []
            print(f"  ch{ci+1}: title='{ch.get('title')}' chunks={ch.get('chunks')} "
                  f"children={len(kids)}")
            for sub in kids:
                print(f"      - '{sub.get('title')}' chunks={sub.get('chunks')}")

    # Assertions
    fails: list[str] = []
    repair_used = (meta or {}).get("repair_used") or []
    pass_via = (meta or {}).get("pass_via")
    if expect_auto_subs:
        if "auto_subs_for_single_top" not in repair_used:
            fails.append(f"expected auto_subs_for_single_top in repair_used, got {repair_used}")
        if pass_via != "repair":
            fails.append(f"expected pass_via='repair', got {pass_via!r}")
        if not chapters:
            fails.append("expected non-empty chapters")
        elif expect_top_count is not None and len(chapters) != expect_top_count:
            fails.append(f"expected {expect_top_count} top, got {len(chapters)}")
        elif chapters and expect_children_count is not None:
            kids = chapters[0].get("children") or []
            if len(kids) != expect_children_count:
                fails.append(f"expected {expect_children_count} children, got {len(kids)}")
            else:
                # 每个 child 用对应 chunk.headline
                for i, sub in enumerate(kids):
                    if sub.get("chunks") != [i]:
                        fails.append(f"child {i} chunks {sub.get('chunks')} != [{i}]")
                    expect_title = f"第{i+1}段主题"
                    if sub.get("title") != expect_title:
                        fails.append(f"child {i} title {sub.get('title')!r} != {expect_title!r}")
    else:
        if "auto_subs_for_single_top" in repair_used:
            fails.append(f"unexpected auto_subs triggered: {repair_used}")
        if chapters:
            fails.append(f"expected empty chapters when auto_subs not applicable, got {len(chapters)}")

    if fails:
        print(f"\n[FAIL] {name}:")
        for f in fails:
            print(f"  - {f}")
        return False
    print(f"\n[PASS] {name}")
    return True


def main():
    # 倔强单顶层 JSON：3 次 attempt 都吐这个，强迫走 repair → auto_subs
    stubborn_n4 = json.dumps({"chapters": [
        {"title": "全片", "chunks": [0, 1, 2, 3]},
    ]}, ensure_ascii=False)
    stubborn_n3 = json.dumps({"chapters": [
        {"title": "全片", "chunks": [0, 1, 2]},
    ]}, ensure_ascii=False)
    # n=4 双顶层 chunks=[0,1] + [2,3] 无 children — 应只命中 "至少 3 个顶层" reject
    # 不进 auto_subs 兜底（len(chs)!=1）
    stubborn_2tops = json.dumps({"chapters": [
        {"title": "前半", "chunks": [0, 1]},
        {"title": "后半", "chunks": [2, 3]},
    ]}, ensure_ascii=False)
    # refine_chapter_titles 调用第 4 次 decode，给故意 parse-fail garbage，
    # 让 refine 返回 None → 不覆盖兜底的 chunk.headline 兜底
    refine_garbage = "I cannot follow the format."

    results = []
    results.append(run_case(
        "A: 倔强单顶层 n=4 → auto_subs 触发",
        n=4,
        decode_returns=[stubborn_n4, stubborn_n4, stubborn_n4, refine_garbage],
        expect_auto_subs=True,
        expect_top_count=1,
        expect_children_count=4,
    ))
    results.append(run_case(
        "B: 倔强单顶层 n=3 → auto_subs 触发",
        n=3,
        decode_returns=[stubborn_n3, stubborn_n3, stubborn_n3, refine_garbage],
        expect_auto_subs=True,
        expect_top_count=1,
        expect_children_count=3,
    ))
    results.append(run_case(
        "C: 双顶层 n=4 无 children → 兜底不触发",
        n=4,
        decode_returns=[stubborn_2tops, stubborn_2tops, stubborn_2tops, refine_garbage],
        expect_auto_subs=False,
    ))

    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r)
    print(f"TOTAL: {passed}/{len(results)} passed")
    print(f"{'='*60}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
