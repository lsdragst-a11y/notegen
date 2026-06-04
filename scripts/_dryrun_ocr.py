"""单视频跑 OCR pass，打印每 chunk 的 ocr_text，人工核质量。
用法: .venv/Scripts/python.exe scripts/_dryrun_ocr.py <summary.json 路径> <视频路径>
summary.json 里要有带 start/end/keyframe 的 chunks。"""
import sys, json
sys.path.insert(0, "src")
import ocr_vl

chunks = json.loads(open(sys.argv[1], encoding="utf-8").read())
if isinstance(chunks, dict):
    chunks = chunks.get("chunks") or chunks.get("summary") or []
texts = ocr_vl.ocr_chunks(chunks, sys.argv[2], frames_per_chunk=3)
for i, (c, t) in enumerate(zip(chunks, texts)):
    print(f"\n=== chunk {i+1} [{c.get('start')}-{c.get('end')}] hl={c.get('headline','')[:30]}")
    print(t or "(无屏上文字)")
