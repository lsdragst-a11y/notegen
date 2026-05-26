"""扫 web/public/notes/ 用扩好的字典回填 ASR 错字 leakage。

跟 _postfix_asr_titles.py / _postfix_qmask.py 是同类工具：
对已发布产物做就地修补，不重跑 ASR/LLM。

字典来源：
  _GLOBAL_CORRECTIONS     — 所有视频都 apply（繁→简 + unambiguous 同音字）
  _DOMAIN_CORRECTIONS[D]  — 视频 meta 命中 domain D 时 apply

修补范围（每视频）：
  web/public/notes/{id}/summary.json   chunk.text / headline / summary / keywords[]
  web/public/notes/{id}/chapters.json  chapter.title / abstract / recap / quiz.questions[].q+options+explanation
                                       + 双语字段 title_zh/abstract_zh（_en 字段也扫但应该都是英文，
                                       不会被中文 patterns 误伤）

跑法：
  .venv/Scripts/python.exe scripts/_postfix_corpus_corrections.py            # 跑全部 web 笔记
  .venv/Scripts/python.exe scripts/_postfix_corpus_corrections.py --dry      # 只 print 不写盘
  .venv/Scripts/python.exe scripts/_postfix_corpus_corrections.py --only BV1xxx  # 单视频
"""
from __future__ import annotations
import argparse, json, sys, os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

NOTES = ROOT / "web" / "public" / "notes"

from pipeline import (_GLOBAL_CORRECTIONS, _DOMAIN_CORRECTIONS,
                       _detect_domains, _load_meta_safe)


def build_corrections(meta: dict | None) -> dict[str, str]:
    """合并 global + 命中 domain 的字典。长 key 排前避免短 key 先吃。"""
    merged: dict[str, str] = dict(_GLOBAL_CORRECTIONS)
    if meta:
        for d in _detect_domains(meta):
            merged.update(_DOMAIN_CORRECTIONS.get(d, {}))
    # 按 key 长度降序排，让 "中段处理" 先于 "中段" 替换（避免双重替换冲突）
    return dict(sorted(merged.items(), key=lambda kv: -len(kv[0])))


def apply_to_json(obj, corrections: dict[str, str], counter: dict[str, int]):
    """递归 apply 到任意 JSON value，原地替换。"""
    if isinstance(obj, str):
        s = obj
        for wrong, right in corrections.items():
            if wrong == right:  # 占位 entry (e.g. "缓冲":"缓冲" 防短词先吃长词)
                continue
            if wrong in s:
                n = s.count(wrong)
                if n:
                    counter[wrong] += n
                    s = s.replace(wrong, right)
        return s
    if isinstance(obj, list):
        return [apply_to_json(x, corrections, counter) for x in obj]
    if isinstance(obj, dict):
        return {k: apply_to_json(v, corrections, counter) for k, v in obj.items()}
    return obj


def process_one(note_dir: Path, dry: bool = False) -> dict[str, int]:
    summary_p = note_dir / "summary.json"
    chapters_p = note_dir / "chapters.json"
    meta_p = note_dir / "meta.json"
    if not (summary_p.exists() and chapters_p.exists()):
        return {}

    meta = _load_meta_safe(meta_p)
    corrections = build_corrections(meta)
    domains = _detect_domains(meta) if meta else []

    counter: dict[str, int] = defaultdict(int)
    # summary
    summary = json.loads(summary_p.read_text(encoding="utf-8"))
    new_summary = apply_to_json(summary, corrections, counter)
    summary_changed = (new_summary != summary)
    # chapters
    chapters_doc = json.loads(chapters_p.read_text(encoding="utf-8"))
    new_chapters = apply_to_json(chapters_doc, corrections, counter)
    chapters_changed = (new_chapters != chapters_doc)

    if not (summary_changed or chapters_changed):
        return {}

    if not dry:
        if summary_changed:
            summary_p.write_text(
                json.dumps(new_summary, ensure_ascii=False, indent=2),
                encoding="utf-8")
        if chapters_changed:
            chapters_p.write_text(
                json.dumps(new_chapters, ensure_ascii=False, indent=2),
                encoding="utf-8")
    return dict(counter)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只 print 不写盘")
    ap.add_argument("--only", nargs="*", default=None,
                     help="只处理指定 note id（用 web/public/notes 下目录名）")
    args = ap.parse_args()

    if args.only:
        targets = [NOTES / nid for nid in args.only]
    else:
        targets = sorted([d for d in NOTES.iterdir() if d.is_dir()])

    print(f"扫 {len(targets)} 个笔记目录…")
    total_videos_changed = 0
    grand_counter: dict[str, int] = defaultdict(int)
    for note_dir in targets:
        try:
            cnt = process_one(note_dir, dry=args.dry)
        except Exception as e:
            print(f"  [error] {note_dir.name}: {e}")
            continue
        if cnt:
            total_videos_changed += 1
            total = sum(cnt.values())
            top3 = sorted(cnt.items(), key=lambda kv: -kv[1])[:3]
            mark = "[dry]" if args.dry else "[ok]"
            print(f"  {mark} {note_dir.name}: {total} 处替换 "
                  f"top3={[(w, n) for w, n in top3]}")
            for w, n in cnt.items():
                grand_counter[w] += n

    print(f"\n=== 汇总 ===")
    print(f"  改动视频数: {total_videos_changed}/{len(targets)}")
    print(f"  总替换次数: {sum(grand_counter.values())}")
    if grand_counter:
        print(f"  pattern 分布:")
        for w, n in sorted(grand_counter.items(), key=lambda kv: -kv[1]):
            print(f"    '{w}' → '{find_right(w)}': {n}")


def find_right(wrong: str) -> str:
    """从 dicts 反查 right（仅 print 用）。"""
    if wrong in _GLOBAL_CORRECTIONS:
        return _GLOBAL_CORRECTIONS[wrong]
    for d, dc in _DOMAIN_CORRECTIONS.items():
        if wrong in dc:
            return dc[wrong]
    return "?"


if __name__ == "__main__":
    main()
