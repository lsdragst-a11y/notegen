"""Feasibility dryrun: 学习「ASR 同音字纠错」是否值得做 + 该怎么做。

两阶段：

Phase 1 (instant, ~10s)：静态分析
  1.1 扫 _GLOBAL_CORRECTIONS / _DOMAIN_HOTWORDS 字典结构，分类（繁→简、同音字、域错字）
  1.2 扫 summary.json corpus，统计已知错字模式的 leakage
       — 这告诉我们：现有 qwen_asr_fix + 静态字典 漏了多少
  1.3 对每个 leakage，输出周围 ±20 字 context（silver gold 雏形）

Phase 2 (~5-10 min, GPU)：silver gold 采样
  2.1 选 N 个已 cache 的 summary.json
  2.2 对每个 chunk 跑 qwen_asr_fix，捕获 fix 字典持久化
  2.3 分类汇总：
       - 已在 _GLOBAL_CORRECTIONS 里（重复，无需训）
       - 同 wrong 在不同 chunk 映射到不同 right（context-dependent → 需 ML）
       - 1:1 lookup（dict 扩展即可）

跑法：
  .venv/Scripts/python.exe scripts/_dryrun_asr_correction.py --phase 1
  .venv/Scripts/python.exe scripts/_dryrun_asr_correction.py --phase 2 --n-videos 5
  .venv/Scripts/python.exe scripts/_dryrun_asr_correction.py            # 两个都跑

判定标准：
  - leakage / video > 5：值得做（错字现存不少）
  - 1:1 ratio > 0.8：dict 扩展够了，不必训
  - 1:1 ratio < 0.5：很多 context-dependent，ML 有价值
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUTPUTS = ROOT / "data" / "outputs"
CACHE_DIR = ROOT / "data"

# 从 J5/J6/J7 系列 memory 收集的已知 ASR 同音字 patterns（域内常见误识别）
# 不含繁→简（那个 _GLOBAL_CORRECTIONS 已覆盖）；不含纯 punctuation。
# 注意：有些"错字"在合法语境下也合法（如"中段"本意=中间段落，要 context 判 false positive）
KNOWN_ERRORS = {
    # 王道计组系列（J6/J7 高频）
    "中段": "中断",     # 操作系统/计组上下文常 fire；vlog/talk 上下文 "中段=middle section" 合法
    "中斩": "中断",
    "中斜": "中断",
    "中斷": "中断",     # 繁体残留
    "中斧": "中断",
    "屁屁": "PP",       # 王道 P/V 操作场景
    "屏屏": "屏蔽",
    "地坝": "地址",
    "任劳": "任务",
    "程庇": "程序",
    "介绅": "介绍",
    "服务程": "服务程序",
    # 计网域
    "双脚线": "双绞线",
    # 烟台/电源 series (J5)
    "烟台": "延迟",
    "电源": "电路",
}


def _categorize_dict_entry(wrong: str, right: str) -> str:
    """繁→简 / 同音字 / 域错字 三分类。"""
    # 繁体 → 简体：wrong 含繁体特征字（基于 Unicode 范围粗判，不严格）
    trad_chars = set("會經過國機電腦邊們時間題為對單應當議協網絡個導報層線輸內優當隨擇異總點價結論觀識")
    if any(c in trad_chars for c in wrong):
        return "trad_to_simp"
    # 同长度的字符替换 = 同音字最可能
    if len(wrong) == len(right):
        return "homophone"
    # 否则是域错字 / phrase fix
    return "domain"


def phase1_dict_analysis():
    """分析现有 _GLOBAL_CORRECTIONS / _DOMAIN_HOTWORDS 结构。"""
    print("=== Phase 1.1: 字典结构分析 ===")
    src = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")

    # 抠 _GLOBAL_CORRECTIONS dict
    m = re.search(r"_GLOBAL_CORRECTIONS:\s*dict\[str,\s*str\]\s*=\s*\{(.+?)\n\}",
                  src, re.DOTALL)
    if not m:
        print("  [warn] failed to parse _GLOBAL_CORRECTIONS")
        return None
    body = m.group(1)
    global_pairs = re.findall(r'"([^"]+)":\s*"([^"]+)"', body)
    print(f"  _GLOBAL_CORRECTIONS: {len(global_pairs)} 条")
    cats = Counter(_categorize_dict_entry(w, r) for w, r in global_pairs)
    for c, n in cats.most_common():
        print(f"    {c}: {n} ({n/len(global_pairs):.0%})")
    samples = {c: [] for c in cats}
    for w, r in global_pairs:
        c = _categorize_dict_entry(w, r)
        if len(samples[c]) < 3:
            samples[c].append((w, r))
    for c, exs in samples.items():
        print(f"    [{c}] e.g. {exs}")

    # _DOMAIN_HOTWORDS
    m2 = re.search(r"_DOMAIN_HOTWORDS:\s*dict\[str,\s*list\[str\]\]\s*=\s*\{(.+?)\n\}",
                   src, re.DOTALL)
    if m2:
        n_domains = len(re.findall(r'^\s*"[^"]+":', m2.group(1), re.MULTILINE))
        terms = re.findall(r'"[^"]+",|"[^"]+"\]', m2.group(1))
        print(f"  _DOMAIN_HOTWORDS: {n_domains} domains, ~{len(terms)} terms")
    return {"global_pairs": global_pairs, "categories": dict(cats)}


def phase1_leakage_scan():
    """扫 summary.json corpus 看已知错字 leakage。"""
    print("\n=== Phase 1.2: 已知错字 leakage 扫描 ===")
    summary_files = sorted(glob.glob(str(OUTPUTS / "*.summary.json")))
    print(f"  扫 {len(summary_files)} 个 summary.json")

    # per-pattern 统计：哪些视频有 leakage
    pattern_hits = defaultdict(lambda: {"count": 0, "videos": set(), "contexts": []})
    n_videos_checked = 0
    n_videos_with_leakage = 0

    for f in summary_files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list) or not d:
            continue
        n_videos_checked += 1
        vid = Path(f).stem
        full = "\n".join(c.get("text", "") or "" for c in d)
        has_leak = False
        for wrong, right in KNOWN_ERRORS.items():
            # 找所有出现位置
            for m in re.finditer(re.escape(wrong), full):
                # 排除：right 本身已存在的合法上下文（如 "中段" 用作 middle section 而非 "中断"）
                # 简单启发：if 同 chunk 里还出现了 right，可能是 ASR fix 已经救了部分但有 leakage
                # 这里不做误报过滤，留给人工/上下文 viewer 判
                start = max(0, m.start() - 20)
                end = min(len(full), m.end() + 20)
                ctx = full[start:end].replace("\n", " ")
                pattern_hits[wrong]["count"] += 1
                pattern_hits[wrong]["videos"].add(vid)
                if len(pattern_hits[wrong]["contexts"]) < 3:
                    pattern_hits[wrong]["contexts"].append(ctx)
                has_leak = True
        if has_leak:
            n_videos_with_leakage += 1

    print(f"  跑通视频: {n_videos_checked}, 有 leakage 的: {n_videos_with_leakage} "
          f"({n_videos_with_leakage/max(n_videos_checked,1):.0%})")
    print()
    print("  按 pattern leakage rank:")
    sorted_pats = sorted(pattern_hits.items(),
                          key=lambda kv: -kv[1]["count"])
    for wrong, info in sorted_pats:
        right = KNOWN_ERRORS[wrong]
        print(f"  '{wrong}'→'{right}': {info['count']} 次 in "
              f"{len(info['videos'])} 个视频")
        for ctx in info["contexts"][:2]:
            print(f"      ...{ctx}...")
    return {
        "n_videos_checked": n_videos_checked,
        "n_videos_with_leakage": n_videos_with_leakage,
        "pattern_hits": {w: {"count": v["count"], "n_videos": len(v["videos"])}
                          for w, v in pattern_hits.items()},
    }


def phase2_silver_gold(n_videos: int = 5):
    """对采样视频跑 qwen_asr_fix 捕获 corrections。"""
    print(f"\n=== Phase 2: 在 {n_videos} 视频上跑 qwen_asr_fix 收集 silver gold ===")
    # 挑跑过 llm_chapters 的视频（确保 chunks 有 headline + keywords）
    candidates = []
    for f in sorted(glob.glob(str(OUTPUTS / "*.summary.json")),
                    key=lambda p: -Path(p).stat().st_mtime):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list) or len(d) < 3:
            continue
        # 必须有 headline + keywords（qwen_asr_fix 喂这些）
        if not d[0].get("headline") or not d[0].get("keywords"):
            continue
        candidates.append(f)
        if len(candidates) >= n_videos:
            break
    print(f"  采样 {len(candidates)} 个视频")
    if not candidates:
        print("  [warn] 找不到合格的 summary.json")
        return None

    from segment_llm import qwen_asr_fix

    all_fixes_per_video: dict[str, dict[str, str]] = {}
    for i, f in enumerate(candidates, 1):
        vid = Path(f).stem
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        print(f"\n  [{i}/{len(candidates)}] {vid} ({len(d)} chunks)")
        fixes = qwen_asr_fix(d)
        all_fixes_per_video[vid] = fixes
        if fixes:
            print(f"    捕获 {len(fixes)} 条 fix:")
            for w, r in list(fixes.items())[:5]:
                print(f"      '{w}' → '{r}'")
        else:
            print(f"    无 fix（chunks 已干净 or LLM 没找到）")

    # 持久化
    out = CACHE_DIR / "_dryrun_asr_silver_gold.json"
    out.write_text(json.dumps(all_fixes_per_video, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\n  [cache] 写入 {out}")
    return all_fixes_per_video


def phase2_analyze(all_fixes_per_video: dict, dict_analysis: dict | None):
    """分类汇总：1:1 lookup vs context-dependent vs 已在静态字典里。"""
    print("\n=== Phase 2 分析：silver gold 分类 ===")
    if not all_fixes_per_video:
        print("  [warn] 无 silver gold 数据")
        return

    # wrong → 所有 right（across videos）
    wrong_to_rights: dict[str, set[str]] = defaultdict(set)
    wrong_to_videos: dict[str, set[str]] = defaultdict(set)
    for vid, fixes in all_fixes_per_video.items():
        for w, r in fixes.items():
            wrong_to_rights[w].add(r)
            wrong_to_videos[w].add(vid)

    n_unique_wrong = len(wrong_to_rights)
    n_1to1 = sum(1 for rs in wrong_to_rights.values() if len(rs) == 1)
    n_context_dep = n_unique_wrong - n_1to1
    print(f"  unique wrong patterns: {n_unique_wrong}")
    print(f"    1:1 (context-free): {n_1to1} ({n_1to1/max(n_unique_wrong,1):.0%})")
    print(f"    1:N (context-dependent): {n_context_dep}")
    if n_context_dep:
        print(f"    1:N samples:")
        for w, rs in wrong_to_rights.items():
            if len(rs) > 1:
                print(f"      '{w}' → {rs}")

    # 是否已在 _GLOBAL_CORRECTIONS
    if dict_analysis:
        existing = {w for w, _ in dict_analysis["global_pairs"]}
        in_existing = sum(1 for w in wrong_to_rights if w in existing)
        net_new = n_unique_wrong - in_existing
        print(f"\n  已在 _GLOBAL_CORRECTIONS 里: {in_existing}")
        print(f"  净新增（可直接扩 dict）: {net_new}")
        if net_new:
            print(f"  净新增 sample:")
            for w, rs in wrong_to_rights.items():
                if w not in existing:
                    print(f"      '{w}' → {list(rs)[0]} (in {len(wrong_to_videos[w])} videos)")
                    if list(wrong_to_rights.keys()).index(w) > 9:
                        break

    # 决策
    print(f"\n=== 决策 ===")
    if n_unique_wrong == 0:
        print(f"  [no-go] 0 corrections，corpus 已干净，无需训")
        return
    ratio_1to1 = n_1to1 / n_unique_wrong
    if ratio_1to1 > 0.85:
        print(f"  [extend-dict] 1:1 比例 {ratio_1to1:.0%}，建议：")
        print(f"    扩 _GLOBAL_CORRECTIONS 字典，加上述 silver gold 净新增项")
        print(f"    不必训 ML 模型——上下文判断价值低")
    elif ratio_1to1 > 0.5:
        print(f"  [hybrid] 1:1 比例 {ratio_1to1:.0%}，建议：")
        print(f"    一半扩 dict + 一半上下文检测：")
        print(f"    - dict 覆盖 1:1 部分（轻量）")
        print(f"    - 用 BERT-base char-level seq-tag 或 char-LM scoring 处理 1:N 部分")
    else:
        print(f"  [train-ML] 1:1 比例 {ratio_1to1:.0%}，建议：")
        print(f"    多数 corrections 是 context-dependent，dict 扩展不够；")
        print(f"    考虑 MacBERT char-level fine-tune，预期 6-12h 训练，2-3 周工程")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, default=0, help="只跑某 phase（0=都跑）")
    ap.add_argument("--n-videos", type=int, default=5,
                     help="Phase 2 采样视频数")
    args = ap.parse_args()

    dict_analysis = None
    if args.phase in (0, 1):
        dict_analysis = phase1_dict_analysis()
        leakage = phase1_leakage_scan()

    if args.phase in (0, 2):
        all_fixes = phase2_silver_gold(args.n_videos)
        if all_fixes:
            phase2_analyze(all_fixes, dict_analysis)


if __name__ == "__main__":
    main()
