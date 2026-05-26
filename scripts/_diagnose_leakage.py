"""诊断 ASR 错字 leakage 的根因：
A. 字典漏（错字形式不在现有 _DOMAIN_CORRECTIONS 里）
B. 域 detect 失败（视频 meta 没触发对应 domain）
C. 老产物未回填（产物早于字典补丁）

对每个 leakage 视频，输出：
  - 视频 stem + meta.title
  - meta-based detected domains
  - 错字 raw context（chunk text 片段，看是否裸 "中段" 形式 vs "中段X" 变体）
  - chapters.json mtime vs git log of pipeline.py
"""
from __future__ import annotations
import json, glob, re, sys, os
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

OUTPUTS = ROOT / "data" / "outputs"
RAW = ROOT / "data" / "raw"

from pipeline import (_DOMAIN_CORRECTIONS, _DOMAIN_KEYWORDS,
                       _GLOBAL_CORRECTIONS, _detect_domains, _load_meta_safe)


# 拿 dryrun 时找到的 leakage patterns
LEAKAGE_PATTERNS = [
    "中段", "中斷", "服务程", "双脚线", "程庇", "地坝",
    "中斧", "中斩", "中斜", "屁屁", "屏屏",
    "任劳", "电源", "烟台", "介绅",
]


def find_video_meta(stem: str) -> dict | None:
    """从 stem 反向找 raw/{bv}.meta.json"""
    bv = stem.split(".")[0]  # e.g. BV1BE411D7ii_p68_p0
    p = RAW / f"{bv}.meta.json"
    return _load_meta_safe(p)


def check_dict_coverage(wrong: str, domain_keys: list[str]) -> dict:
    """检查这个 wrong pattern 是否在字典里被覆盖（裸 + 已知变体）。"""
    result = {
        "in_global": wrong in _GLOBAL_CORRECTIONS,
        "in_domains": [],
        "variants_in_domain": defaultdict(list),
    }
    for d in domain_keys:
        dc = _DOMAIN_CORRECTIONS.get(d, {})
        if wrong in dc:
            result["in_domains"].append(d)
        # 找变体（带 wrong 作 substring 的字典 key）
        for k, v in dc.items():
            if wrong in k and k != wrong:
                result["variants_in_domain"][d].append((k, v))
    return result


def main():
    print("=" * 70)
    print("ASR Leakage 根因诊断")
    print("=" * 70)

    # 收集所有有 leakage 的视频
    print("\n【步骤 1】扫所有 summary.json，按视频聚合 leakage")
    video_leaks = defaultdict(lambda: {"patterns": Counter(), "contexts": []})

    for f in sorted(glob.glob(str(OUTPUTS / "*.summary.json"))):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list) or not d:
            continue
        full = "\n".join(c.get("text", "") or "" for c in d)
        for p in LEAKAGE_PATTERNS:
            cnt = full.count(p)
            if cnt == 0:
                continue
            stem = Path(f).stem
            video_leaks[stem]["patterns"][p] += cnt
            if len(video_leaks[stem]["contexts"]) < 5:
                # 找 ±15 字 context，看周围出现什么
                for m in re.finditer(re.escape(p), full):
                    if len(video_leaks[stem]["contexts"]) >= 5:
                        break
                    s_, e_ = max(0, m.start()-15), min(len(full), m.end()+15)
                    ctx = full[s_:e_].replace("\n", " ")
                    video_leaks[stem]["contexts"].append((p, ctx))

    print(f"  {len(video_leaks)} 个视频有 leakage")

    # 每个视频独立诊断
    print("\n【步骤 2】每视频根因分析")
    bucket_A = []  # 字典漏
    bucket_B = []  # 域 detect 失败
    bucket_C = []  # 老产物未回填
    for stem, info in sorted(video_leaks.items(),
                              key=lambda kv: -sum(kv[1]["patterns"].values())):
        meta = find_video_meta(stem)
        title = (meta or {}).get("title", "(no meta)")[:50]
        detected = _detect_domains(meta) if meta else []
        # 计算 leakage 总数
        total = sum(info["patterns"].values())
        # 看 leakage patterns 是否都已被字典覆盖
        all_covered = True
        coverage_msgs = []
        for p in info["patterns"]:
            cov = check_dict_coverage(p, detected)
            if not cov["in_global"] and not cov["in_domains"]:
                # 裸 pattern 没字典覆盖
                # 检查是不是变体形式（如 "中段处理"）已覆盖但裸 "中段" 没
                has_variant_cov = False
                for d in detected:
                    dc = _DOMAIN_CORRECTIONS.get(d, {})
                    for k in dc:
                        if p in k and k != p:
                            # 字典有变体 e.g. "中段处理"，看 leakage context 是不是有更长形式
                            has_variant_cov = True
                            break
                    if has_variant_cov:
                        break
                if has_variant_cov:
                    coverage_msgs.append(f"{p}=变体已覆盖但裸 pattern 漏")
                else:
                    coverage_msgs.append(f"{p}=字典未覆盖")
                all_covered = False
        # 判 bucket
        if not detected:
            bucket = "B"  # 域 detect 失败（无任何 domain）
        elif not all_covered:
            bucket = "A"  # 字典漏
        else:
            bucket = "C"  # 字典覆盖了但产物没修，老产物
        line = (f"  [{bucket}] {stem[:55]}\n"
                f"        title: {title}\n"
                f"        patterns: {dict(info['patterns'])}\n"
                f"        detected_domains: {detected}\n"
                f"        coverage: {coverage_msgs if coverage_msgs else 'all covered'}")
        if bucket == "A":
            bucket_A.append((stem, total, info))
        elif bucket == "B":
            bucket_B.append((stem, total, info))
        else:
            bucket_C.append((stem, total, info))
        print(line)

    print(f"\n=== 根因汇总 ===")
    print(f"  Bucket A (字典漏): {len(bucket_A)} 视频, {sum(b[1] for b in bucket_A)} leakage")
    print(f"  Bucket B (域 detect 失败): {len(bucket_B)} 视频, {sum(b[1] for b in bucket_B)} leakage")
    print(f"  Bucket C (老产物未回填): {len(bucket_C)} 视频, {sum(b[1] for b in bucket_C)} leakage")


if __name__ == "__main__":
    main()
