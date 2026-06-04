"""对照 with/without OCR：读两个 chapters.json，diff 章标题/abstract/recap。
用法: .venv/Scripts/python.exe scripts/compare_ocr_ablation.py <base_chapters.json> <ocr_chapters.json>"""
import sys, json


def load(p):
    d = json.loads(open(p, encoding="utf-8").read())
    return d.get("chapters") or d


base = load(sys.argv[1])
ocr = load(sys.argv[2])
for i, (b, o) in enumerate(zip(base, ocr)):
    bt, ot = b.get("title", ""), o.get("title", "")
    if bt != ot:
        print(f"[ch{i+1} 标题] base: {bt}\n           ocr : {ot}")
    ba, oa = (b.get("abstract") or "")[:120], (o.get("abstract") or "")[:120]
    if ba != oa:
        print(f"[ch{i+1} abstract] base: {ba}\n               ocr : {oa}")
    br, orc = (b.get("recap") or "")[:120], (o.get("recap") or "")[:120]
    if br != orc:
        print(f"[ch{i+1} recap] base: {br}\n            ocr : {orc}")
