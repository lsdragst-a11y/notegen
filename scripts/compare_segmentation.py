"""把多模态章节切分的 ablation 数据按段落对齐打印出来。"""
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OUTPUTS = Path("data/outputs")

for stem in ("BV1SddcBFESs_p0", "BV19E411D78Q_p38.f30280"):
    name = f"{stem}.large-v3.neural"
    ch_path = OUTPUTS / f"{name}.chapters.json"
    sum_path = OUTPUTS / f"{name}.summary.json"
    if not ch_path.exists():
        continue
    print(f"\n========== {name} ==========")
    d = json.load(open(ch_path, encoding="utf-8"))
    a = d["ablation"]
    seg = json.load(open(sum_path, encoding="utf-8"))

    header = f"{'pos':>6} {'text':>5} {'visu':>5} {'fused':>5} {'depth':>6}  邻接段标题"
    print(header)
    for i in range(len(a["text_dists"])):
        v = a["visual_dists"][i]
        v_str = f"{v:.2f}" if v is not None else " -- "
        t = a["text_dists"][i]
        f = a["fused_dists"][i]
        s = a["depth_scores"][i]
        h1 = seg[i]["headline"][:18]
        h2 = seg[i + 1]["headline"][:18]
        print(f"{i+1:>2}->{i+2:<3} {t:>5.2f} {v_str:>5} {f:>5.2f} {s:>+6.3f}  {h1:18} | {h2}")

    print(f"  纯文本边界: 段{[b + 1 for b in a['text_only_boundaries']]}")
    print(f"  多模态边界: 段{[b + 1 for b in a['multimodal_boundaries']]}  (alpha={a['alpha']})")
