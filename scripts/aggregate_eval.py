"""聚合 data/outputs/*.chapters.json + meta.json 为论文附录 B 表（markdown）。

只挑当前 pipeline 默认参数（neural + texttile + cc 800 + llm_chapters）的 case。
旧的 ablation 跑出来的（extractive / cc400 等）跳过。

Run:
  .venv/Scripts/python.exe scripts/aggregate_eval.py
  .venv/Scripts/python.exe scripts/aggregate_eval.py --out paper/appendix_b.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "outputs"
META_DIR = ROOT / "data" / "raw"


def _load_meta(video_stem: str) -> dict | None:
    """video_stem 是 chapters.json 文件名前缀对应的视频 stem。"""
    # chapters.json: BV1xxx_p0.large-v3.neural.texttile.chapters.json
    # 对应 video stem 为 BV1xxx_p0（去掉 .large-v3.neural.texttile）
    p = META_DIR / f"{video_stem}.meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def collect_records(include_legacy: bool = False,
                    include_mm: bool = True) -> list[dict]:
    """扫所有 chapters.json，挑默认参数 case。
    include_legacy=False 时只挑有 seg_meta 字段的新 schema 跑（旧 cache 缺数字段）。
    include_mm=True 时也收 .mm.chapters.json（keyframes 开启路径）+
    .mm.vl.chapters.json（VLM caption 路径）。
    """
    records: list[dict] = []
    patterns = ["*.neural.texttile.chapters.json"]
    if include_mm:
        patterns.append("*.neural.texttile.mm.chapters.json")
        patterns.append("*.neural.texttile.mm.vl.chapters.json")
    paths = []
    for pat in patterns:
        paths.extend(OUT_DIR.glob(pat))
    for p in sorted(set(paths)):
        # 跳过含 .cc 变体（cc!=800 ablation 跑）
        if ".cc" in p.name:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  skip {p.name}: {e}", file=sys.stderr)
            continue
        chapters = data.get("chapters") or []
        if not chapters:
            continue
        ablation = data.get("ablation") or {}
        if not isinstance(ablation, dict):
            ablation = {}
        # 旧 schema 没 seg_meta，过滤掉（除非显式 --include-legacy）
        if not include_legacy and "seg_meta" not in ablation:
            continue
        # video stem = 去掉 .large-v3.neural.texttile[.mm[.vl]].chapters.json
        is_vl = ".mm.vl.chapters.json" in p.name
        is_mm = ".mm.chapters.json" in p.name or is_vl
        stem = p.name.replace(".large-v3.neural.texttile.mm.vl.chapters.json", "")\
                     .replace(".large-v3.neural.texttile.mm.chapters.json", "")\
                     .replace(".large-v3.neural.texttile.chapters.json", "")
        # chapter boundaries 用于多模态 vs 纯文本对比
        boundaries = [c["indices"][0] for c in chapters[1:]]
        meta = _load_meta(stem)
        title = meta.get("title", "") if meta else ""
        # 整理一行
        seg_meta = ablation.get("seg_meta") or {}
        records.append({
            "stem": stem,
            "title": title[:50],
            "lang": ablation.get("lang") or "?",
            "duration_s": ablation.get("duration"),
            "n_chunks": ablation.get("n_chunks") or 0,
            "n_chapters": ablation.get("n_chapters") or len(chapters),
            "max_chunks_ch": ablation.get("max_chunks_per_chapter")
                             or max(len(c.get("indices", [])) for c in chapters),
            "method": seg_meta.get("method") or ("texttile" if seg_meta == {} else "?"),
            "fallback": seg_meta.get("fallback_used", False),
            "llm_attempts": seg_meta.get("llm_attempts", 0),
            "llm_pass_via": seg_meta.get("llm_pass_via") or "-",
            "llm_repair": seg_meta.get("llm_repair_used") or [],
            "llm_fail": seg_meta.get("llm_fail_reasons") or [],
            "wrapup": ablation.get("has_wrapup", False),
            "keyframes": is_mm or bool(ablation.get("keyframes", False)),
            "vl": is_vl or bool(ablation.get("vlm_captions", False)),
            "vl_used": bool(ablation.get("vlm_captions_used", False)),
            "vl_degraded_reason": ablation.get("vlm_degraded_reason"),
            "vl_max_prefix_run": ablation.get("vlm_max_prefix_run"),
            "vl_generic_ratio": ablation.get("vlm_generic_ratio"),
            "vl_rescue": bool(seg_meta.get("vl_rescue_used", False)),
            "boundaries": boundaries,
        })
    return records


def _path_key(r: dict) -> str:
    """记录走哪条路径：'txt' / 'mm' / 'mm.vl'。"""
    if r.get("vl"):
        return "mm.vl"
    if r.get("keyframes"):
        return "mm"
    return "txt"


def render_mm_compare(records: list[dict]) -> str:
    """渲染多模态 ablation 对比表：同 video 的纯文本 vs +keyframes 两路并列。"""
    # 按 stem 聚合（key=path）
    by_stem: dict[str, dict[str, dict]] = {}
    for r in records:
        by_stem.setdefault(r["stem"], {})[_path_key(r)] = r
    paired = [(s, by_stem[s]) for s in by_stem
              if "txt" in by_stem[s] and "mm" in by_stem[s]]
    n_with_vl = sum(1 for _, paths in paired if "mm.vl" in paths)
    lines = ["# 多模态 ablation：纯文本 vs CLIP-sim vs VLM-caption 三栏对比", "",
             f"配对：{len(paired)} 个视频 txt+mm 都跑了；其中 {n_with_vl} 个也跑了 mm.vl（VLM caption）。",
             ""]
    if not paired:
        lines.append("**没有配对数据**——请先 `pipeline ... --keyframes` 跑过相同视频。")
        return "\n".join(lines)
    # 主对比表
    headers = ["#", "视频", "时长", "段数",
               "txt 章/att/通过", "mm 章/att/通过", "mm.vl 章/att/通过",
               "vl 自适应"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    n_vl_actually_used = 0
    n_vl_downgraded = 0
    n_vl_helped = 0  # vl_used 且章数细于 mm
    for i, (stem, pair) in enumerate(paired, 1):
        tr = pair["txt"]; mr = pair["mm"]; vr = pair.get("mm.vl")
        title = tr["title"] or stem

        def _cell(r):
            if r is None:
                return "-"
            pass_via = r["llm_pass_via"]
            if r["fallback"]:
                pass_via = "fb"
            elif pass_via and pass_via.startswith("attempt_"):
                pass_via = pass_via.replace("attempt_", "#")
            elif pass_via == "repair":
                pass_via = "rep"
            return f"{r['n_chapters']}/{r['llm_attempts']}/{pass_via}"

        if vr is not None:
            if vr["vl_used"]:
                n_vl_actually_used += 1
                if vr["n_chapters"] > mr["n_chapters"]:
                    n_vl_helped += 1
                adaptive = f"used (n_chunks={tr['n_chunks']} ≤ 15)"
            else:
                n_vl_downgraded += 1
                reason = vr.get("vl_degraded_reason")
                if reason == "prefix_run_degenerate":
                    pref_run = vr.get("vl_max_prefix_run")
                    adaptive = (f"downgrade→sim (prefix_run={pref_run}/{tr['n_chunks']}"
                                f" 同质化)")
                elif reason == "generic_ratio_high":
                    gr = vr.get("vl_generic_ratio")
                    adaptive = (f"downgrade→sim (generic_ratio="
                                f"{gr:.2f} 通用句式)" if gr is not None
                                else "downgrade→sim (generic_ratio 高)")
                elif reason == "n_chunks_gt_15" or tr['n_chunks'] > 15:
                    adaptive = f"downgrade→sim (n_chunks={tr['n_chunks']} > 15)"
                else:
                    adaptive = "downgrade→sim"
        else:
            adaptive = "(not run)"

        lines.append(
            f"| {i} | {title} | {_format_duration(tr['duration_s'])} | "
            f"{tr['n_chunks']} | {_cell(tr)} | {_cell(mr)} | {_cell(vr)} | "
            f"{adaptive} |"
        )
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    # 按降级原因细分（老版本可能没记 reason，按 n_chunks 兜底推断）
    def _dg_reason(p):
        v = p.get("mm.vl"); t = p.get("txt")
        if not v or v["vl_used"]:
            return None
        r = v.get("vl_degraded_reason")
        if r:
            return r
        return "n_chunks_gt_15" if (t and t["n_chunks"] > 15) else "unknown"
    n_dg_chunks = sum(1 for _, p in paired if _dg_reason(p) == "n_chunks_gt_15")
    n_dg_generic = sum(1 for _, p in paired if _dg_reason(p) == "generic_ratio_high")
    n_dg_prefix = sum(1 for _, p in paired if _dg_reason(p) == "prefix_run_degenerate")
    lines.append(f"- 跑了三路对比的视频：{len([p for p in paired if 'mm.vl' in p[1]])}/{len(paired)}")
    lines.append(f"- VL 自适应实际启用 caption：{n_vl_actually_used}")
    lines.append(f"- VL 自适应降级回 sim cue：{n_vl_downgraded}"
                 f"（外层 n_chunks>15: {n_dg_chunks}，"
                 f"中层 generic_ratio: {n_dg_generic}，"
                 f"内层 prefix_run 同质化: {n_dg_prefix}）")
    lines.append(f"- VL caption 启用且切更细（vs mm）：{n_vl_helped}/{n_vl_actually_used}")
    lines.append("")
    lines.append("**字段说明**: `章/att/通过` = 章数 / LLM attempts / 通过方式 "
                 "(#1/#2/#3/rep=repair/fb=fallback)")
    return "\n".join(lines)


def render_markdown_table(records: list[dict]) -> str:
    """渲染附录 B markdown 表。"""
    lines = ["# 附录 B：评估视频切分路径汇总", "",
             f"共 {len(records)} 个视频 × 默认配置（chunker=texttile, cc=800, "
             "summarizer=neural, --llm-chapters）。",
             ""]
    # 主表
    headers = ["#", "视频", "语言", "时长", "段数", "章数", "max ch", "切分路径",
               "LLM attempts", "通过方式", "repair", "wrap-up"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for i, r in enumerate(records, 1):
        title = r["title"] or r["stem"]
        path = r["method"]
        if r["fallback"]:
            path = "texttile (LLM fallback)"
        elif path == "llm":
            path = "LLM"
        repair_str = "+".join(r["llm_repair"]) or "-"
        pass_via = r["llm_pass_via"]
        # 如果 attempt N 失败但 repair 救了，显示 "repair (after N attempts)"
        if pass_via == "repair":
            pass_via = f"repair (after {r['llm_attempts']} attempts)"
        elif pass_via and pass_via.startswith("attempt_"):
            pass_via = pass_via.replace("attempt_", "attempt #")
        wrapup = "✓" if r["wrapup"] else "-"
        lines.append(
            f"| {i} | {title} | {r['lang']} | {_format_duration(r['duration_s'])} | "
            f"{r['n_chunks']} | {r['n_chapters']} | {r['max_chunks_ch']} | "
            f"{path} | {r['llm_attempts'] or '-'} | {pass_via} | {repair_str} | {wrapup} |"
        )
    lines.append("")
    # 汇总统计
    lines.append("## 汇总统计")
    lines.append("")
    n_llm = sum(1 for r in records if r["method"] == "llm" and not r["fallback"])
    n_fallback = sum(1 for r in records if r["fallback"])
    n_attempt1 = sum(1 for r in records if r["llm_pass_via"] == "attempt_1")
    n_repair = sum(1 for r in records if r["llm_pass_via"] == "repair")
    n_oversize = sum(1 for r in records if "repair_oversize" in (r["llm_repair"] or []))
    n_wrapup = sum(1 for r in records if r["wrapup"])
    n_en = sum(1 for r in records if r["lang"] == "en")
    n_zh = sum(1 for r in records if r["lang"] == "zh")
    lines.append(f"- 总视频数：{len(records)}（中文 {n_zh} / 英文 {n_en}）")
    lines.append(f"- **LLM 切分成功**：{n_llm}/{len(records)} = "
                 f"{n_llm / max(len(records), 1):.0%}")
    lines.append(f"- LLM attempt 1 直接通过：{n_attempt1}/{len(records)} = "
                 f"{n_attempt1 / max(len(records), 1):.0%}")
    lines.append(f"- **程序化 repair 救活**：{n_repair}/{len(records)} = "
                 f"{n_repair / max(len(records), 1):.0%}")
    lines.append(f"- `_repair_oversize` 实际触发：{n_oversize}/{len(records)}")
    lines.append(f"- Fallback 到 TextTiling：{n_fallback}/{len(records)}")
    lines.append(f"- 末尾 wrap-up 章被识别：{n_wrapup}/{len(records)}")
    return "\n".join(lines)


def render_section_6_4(records: list[dict]) -> str:
    """渲染论文 §6.4 表 + 核心数据栏（VL caption 路径，即 .mm.vl.chapters.json）。

    与 render_mm_compare 不同：本表只看 mm.vl 单路径，含 VL 三层 gate 决策列
    （used / 内层 gate / 外层 gate / 救援），以及 LLM 通过路径列（#1/#2/#3/
    repair/fb）；核心数据栏自动统计覆盖率、各 attempt 计数、gate 触发次数。
    扩 corpus 时一键刷表避免手动计数出错。"""
    # 只取 .mm.vl 路径（_path_key == "mm.vl"）
    vl_records = [r for r in records if _path_key(r) == "mm.vl"]
    if not vl_records:
        return "# §6.4 表\n\n**没有 .mm.vl.chapters.json**——先 `pipeline ... --vlm-captions` 跑过视频。"
    n = len(vl_records)

    def _vl_path(r: dict) -> str:
        if r.get("vl_rescue"):
            return "**救援**"
        if r["vl_used"]:
            return "used"
        reason = r.get("vl_degraded_reason")
        if reason == "prefix_run_degenerate":
            return "**内层 gate**"
        if reason == "generic_ratio_high":
            return "**中层 gate**"
        if reason == "n_chunks_gt_15" or r["n_chunks"] > 15:
            return "外层 gate"
        return f"degrade ({reason or '?'})"

    def _llm_status(r: dict) -> str:
        if r["fallback"]:
            return "fb"
        pv = r["llm_pass_via"]
        if pv == "repair":
            return "repair"
        if pv and pv.startswith("attempt_"):
            return "#" + pv.split("_", 1)[1]
        return pv or "-"

    lines = [f"### 6.4 {n} 视频 corpus：多模态架构泛化验证（auto-aggregated）", "",
             f"VL caption + 三层自适应架构在以下 {n} 视频 corpus 上的完整验证。",
             ""]
    lines.append("| 视频 | n | mm.vl 章 | VL 路径 | LLM 状态 | 备注 |")
    lines.append("|---|---|---|---|---|---|")
    for r in vl_records:
        title = r["title"] or r["stem"]
        note_parts = []
        if r["vl_max_prefix_run"] and r["vl_max_prefix_run"] >= 4:
            note_parts.append(f"prefix_run={r['vl_max_prefix_run']}/{r['n_chunks']}")
        if r["fallback"]:
            note_parts.append("唯一 fallback")
        if r["vl_rescue"]:
            note_parts.append("救援触发")
        note = "; ".join(note_parts) or ""
        lines.append(
            f"| {title} | {r['n_chunks']} | {r['n_chapters']} | "
            f"{_vl_path(r)} | {_llm_status(r)} | {note} |"
        )

    # 核心数据
    n_llm_pass = sum(1 for r in vl_records if r["method"] == "llm" and not r["fallback"])
    n_att1 = sum(1 for r in vl_records if r["llm_pass_via"] == "attempt_1")
    n_att23 = sum(1 for r in vl_records
                  if r["llm_pass_via"] in ("attempt_2", "attempt_3"))
    n_repair = sum(1 for r in vl_records if r["llm_pass_via"] == "repair")
    n_rescue = sum(1 for r in vl_records if r["vl_rescue"])
    n_outer = sum(1 for r in vl_records
                  if not r["vl_used"]
                  and (r.get("vl_degraded_reason") == "n_chunks_gt_15"
                       or r["n_chunks"] > 15)
                  and not r["vl_rescue"])
    n_middle = sum(1 for r in vl_records
                   if r.get("vl_degraded_reason") == "generic_ratio_high")
    n_inner = sum(1 for r in vl_records
                  if r.get("vl_degraded_reason") == "prefix_run_degenerate")
    n_fb = sum(1 for r in vl_records if r["fallback"])

    lines.append("")
    lines.append("**核心数据**：")
    lines.append("")
    lines.append("| 维度 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| LLM 切分覆盖率 | **{n_llm_pass}/{n} = {n_llm_pass/n:.0%}** |")
    lines.append(f"| 一次过 (attempt 1) | {n_att1}/{n} |")
    lines.append(f"| Retry-with-feedback (attempt 2-3) | {n_att23}/{n} |")
    lines.append(f"| Programmatic repair | {n_repair}/{n} |")
    lines.append(f"| 救援触发 | {n_rescue}/{n} |")
    lines.append(f"| 外层 gate 降级 | {n_outer}/{n} |")
    lines.append(f"| 中层 gate 降级 | {n_middle}/{n} |")
    lines.append(f"| 内层 gate 降级 | {n_inner}/{n} |")
    lines.append(f"| Fallback TextTiling | {n_fb}/{n} |")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=str, default=None,
                   help="输出 markdown 路径；不指定则 print 到 stdout")
    p.add_argument("--include-legacy", action="store_true",
                   help="包含旧 schema 跑出的 chapters.json（缺 seg_meta 字段）")
    p.add_argument("--mode", choices=("appendix-b", "mm-compare", "section6-4"),
                   default="appendix-b",
                   help="appendix-b: 默认表格；mm-compare: 多模态 ablation 对比；"
                        "section6-4: §6.4 corpus 表 + 核心数据（VL 路径）")
    args = p.parse_args()

    records = collect_records(include_legacy=args.include_legacy)
    if not records:
        print("no chapters.json found under data/outputs/", file=sys.stderr)
        sys.exit(1)

    if args.mode == "mm-compare":
        md = render_mm_compare(records)
    elif args.mode == "section6-4":
        md = render_section_6_4(records)
        records = [r for r in records if _path_key(r) == "mm.vl"]
    else:
        # appendix-b 模式只看 keyframes=False 的（避免 mm 跑混进基本表）
        text_only = [r for r in records if not r["keyframes"]]
        md = render_markdown_table(text_only)
        records = text_only  # 影响下面的 wrote 行数
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out} ({len(records)} records, mode={args.mode})")
    else:
        print(md)


if __name__ == "__main__":
    main()
