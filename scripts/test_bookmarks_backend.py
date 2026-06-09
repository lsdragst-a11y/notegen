"""Backend bookmarks/categories API with per-user isolation.
Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/test_bookmarks_backend.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TMP = tempfile.mkdtemp()
os.environ["NOTEGEN_DB_PATH"] = os.path.join(TMP, "t.db")

import db  # noqa: E402
db.set_db_path(os.environ["NOTEGEN_DB_PATH"])

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)


def signup(client, email):
    client.post("/api/auth/register",
                json={"email": email, "password": "pw123456", "display_name": email})
    conn = db.connect()
    tok = conn.execute(
        "SELECT ev.token FROM email_verifications ev JOIN users u ON u.id=ev.user_id "
        "WHERE u.email=?", (email.lower(),)).fetchone()["token"]
    conn.close()
    client.get(f"/api/auth/verify?token={tok}")
    r = client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code == 200, r.text


c1 = TestClient(server.app)
c2 = TestClient(server.app)
signup(c1, "bm1@x.com")
signup(c2, "bm2@x.com")

r = c1.get("/api/bookmarks")
check(r.status_code == 200 and r.json() == {"categories": [], "bookmarks": []},
      f"initial empty state -> {r.status_code} {r.text}")

cat = {"id": "c_test", "name": "重点", "color": "#0a84ff", "createdAt": 1000}
r = c1.put("/api/bookmark-categories", json=cat)
st = r.json()
check(r.status_code == 200 and st["categories"][0]["id"] == "c_test",
      f"create category -> {r.status_code} {st}")

bookmark = {
    "key": "note1:chunk:0",
    "noteId": "note1",
    "noteTitle": "Note 1",
    "kind": "chunk",
    "idx": 0,
    "title": "A key point",
    "title_en": "A key point",
    "time": 12.5,
    "keyframeRel": "kf.jpg",
    "categoryIds": ["c_test"],
    "addedAt": 2000,
}
r = c1.put("/api/bookmarks", json=bookmark)
st = r.json()
check(r.status_code == 200 and st["bookmarks"][0]["categoryIds"] == ["c_test"],
      f"upsert bookmark -> {r.status_code} {st}")

r = c1.patch("/api/bookmark-categories/c_test", json={"name": "复习"})
st = r.json()
check(r.status_code == 200 and st["categories"][0]["name"] == "复习",
      f"rename category -> {r.status_code} {st}")

r = c2.get("/api/bookmarks")
check(r.status_code == 200 and r.json() == {"categories": [], "bookmarks": []},
      f"other user cannot see bookmarks -> {r.status_code} {r.text}")

r = c1.delete("/api/bookmark-categories/c_test")
st = r.json()
check(r.status_code == 200 and st["categories"] == [] and st["bookmarks"][0]["categoryIds"] == [],
      f"delete category keeps bookmark and detaches tag -> {r.status_code} {st}")

r = c1.delete("/api/bookmarks/note1%3Achunk%3A0")
st = r.json()
check(r.status_code == 200 and st["bookmarks"] == [], f"delete bookmark -> {r.status_code} {st}")

print()
if FAILS:
    print(f"=== {len(FAILS)} CHECK(S) FAILED ===")
    sys.exit(1)
print("=== ALL CHECKS PASSED ===")
