"""service_common 私有发布 + 字段抽取。用临时 DATA_OUTPUTS/DATA_RAW/USER_NOTES_DIR
造假产物，验证私有目录落位 + video.mp4 + extract_note_fields。不碰 GPU/网络。
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_publish_private.py"""
import sys, os, json, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import service_common as SC  # noqa: E402
from object_store import resolve_ref  # noqa: E402

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# 把 SC 的目录常量重定向到临时区
base = Path(tempfile.mkdtemp())
SC.DATA_OUTPUTS = base / "outputs"; SC.DATA_OUTPUTS.mkdir()
SC.DATA_RAW = base / "raw"; SC.DATA_RAW.mkdir()
SC.USER_NOTES_DIR = base / "user_notes"
SC.NOTES_DIR = base / "web" / "notes"
SC.VIDEOS_DIR = base / "web" / "videos"

stem = "BVtest_p0"
pref = f"{stem}.large-v3.neural.texttile"
(SC.DATA_OUTPUTS / f"{pref}.summary.json").write_text(
    json.dumps([{"start": 0, "end": 42}]), encoding="utf-8")
(SC.DATA_OUTPUTS / f"{pref}.chapters.json").write_text(
    json.dumps({"chapters": [{"title": "C1"}, {"title": "C2"}]}), encoding="utf-8")
(SC.DATA_OUTPUTS / f"{pref}.keyframes").mkdir()
(SC.DATA_OUTPUTS / f"{pref}.keyframes" / "k0.jpg").write_bytes(b"img")
meta_stem = stem.split(".")[0]
(SC.DATA_RAW / f"{meta_stem}.meta.json").write_text(
    json.dumps({"title": "Python 入门", "uploader": "老师", "webpage_url": "http://u"}),
    encoding="utf-8")
(SC.DATA_RAW / f"{meta_stem}.mp4").write_bytes(b"video-bytes")

note_id, storage_path, fields = SC.publish_private(stem, "u1")
nd = resolve_ref(storage_path)
check(note_id == f"u1_{stem}", f"note_id 加 user 维度 == u1_{stem} -> {note_id}")
check(storage_path.startswith("local:"), f"storage_path 变为 object ref -> {storage_path}")
check(str(nd).replace("\\", "/").endswith(f"user_notes/u1/{stem}"),
      f"私有目录在 user_notes/u1 下 -> {nd}")
# 两个用户同 stem -> 不同 note_id（防全局主键覆盖归属）
nid_u2, _, _ = SC.publish_private(stem, "u2")
check(note_id != nid_u2 and nid_u2 == f"u2_{stem}",
      f"不同用户同视频 note_id 不同 -> {note_id} vs {nid_u2}")
check((nd / "summary.json").exists() and (nd / "chapters.json").exists(),
      "summary/chapters 落位")
check((nd / "meta.json").exists(), "meta.json 落位")
check((nd / "keyframes" / "k0.jpg").exists(), "keyframes 落位")
check((nd / "video.mp4").read_bytes() == b"video-bytes", "视频随目录放为 video.mp4")
check(not (SC.VIDEOS_DIR / f"{stem}.mp4").exists(), "私有视频不进公开 videos 目录")
check(fields["title"] == "Python 入门" and fields["domain"] == "编程教学",
      f"字段抽取 title/domain -> {fields.get('title')}/{fields.get('domain')}")
check(fields["duration_sec"] == 42 and fields["chunks"] == 1 and fields["chapters"] == 2,
      f"字段 dur/chunks/chapters -> {fields}")
check(fields["uploader"] == "老师" and fields["webpage_url"] == "http://u",
      "字段 uploader/webpage_url")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ==="); sys.exit(1)
print("=== ALL CHECKS PASSED ===")
