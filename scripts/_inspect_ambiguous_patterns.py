"""扫所有 web 笔记，逐个找 ambiguous 错字的上下文 + 视频元数据，
辅助判定每个 hit 是真错字还是合法用法，决定 disambiguation 规则。
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "web" / "public" / "notes"
sys.path.insert(0, str(ROOT / "src"))
from pipeline import _detect_domains, _load_meta_safe

# 每个 wrong 的候选 right + 描述
AMBIG = {
    "中段": ("中断", "在计组/OS域是误识，其他域合法（文章中段）"),
    "电源": ("电路", "在计组特定子上下文是误识，否则是合法元件"),
    "电源选通": ("电路选通", "更具体的子串"),
    "任劳": ("任务", "孤立罕用，任劳任怨是固定词"),
    "烟台": ("延迟", "可能合法（城市/人名），网络/计组域才是误识"),
}


def main():
    for wrong, (right, desc) in AMBIG.items():
        print(f"\n{'='*70}")
        print(f"  '{wrong}' → '{right}'  ({desc})")
        print('='*70)
        for d in sorted(os.listdir(NOTES)):
            nd = NOTES / d
            if not nd.is_dir(): continue
            sp = nd / "summary.json"
            if not sp.exists(): continue
            try:
                summary = json.loads(sp.read_text(encoding="utf-8"))
            except Exception:
                continue
            full = "\n".join(c.get("text","") or "" for c in summary)
            n = full.count(wrong)
            if not n: continue
            meta = _load_meta_safe(nd / "meta.json")
            title = (meta or {}).get("title","(no meta)")[:60]
            domains = _detect_domains(meta) if meta else []
            print(f"\n  [{d}]  domains={domains}")
            print(f"    title: {title}")
            # context for each occurrence
            seen = 0
            for m in re.finditer(re.escape(wrong), full):
                if seen >= 5: break
                s_, e_ = max(0, m.start()-20), min(len(full), m.end()+20)
                ctx = full[s_:e_].replace("\n", " ")
                print(f"      ...{ctx}...")
                seen += 1
            if n > seen:
                print(f"      (... {n-seen} more)")


if __name__ == "__main__":
    main()
