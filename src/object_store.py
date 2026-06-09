"""Small object-storage adapter used by note file serving.

Current backend is local disk, but callers use storage refs instead of assuming
that a DB field is always a raw filesystem path. New private notes can store
`local:data/user_notes/...`; old absolute/relative paths remain supported.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_PREFIX = "local:"


def storage_ref(path: Path) -> str:
    p = path.resolve()
    try:
        rel = p.relative_to(ROOT)
        return LOCAL_PREFIX + rel.as_posix()
    except ValueError:
        return LOCAL_PREFIX + p.as_posix()


def resolve_ref(ref: str) -> Path:
    raw = (ref or "").strip()
    if raw.startswith(LOCAL_PREFIX):
        val = raw[len(LOCAL_PREFIX):]
        p = Path(val)
        return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    return Path(raw).resolve()


class LocalObjectStore:
    def path_for_ref(self, ref: str) -> Path:
        return resolve_ref(ref)

    def file_path(self, ref: str, object_path: str) -> Path:
        base = self.path_for_ref(ref)
        target = (base / object_path).resolve()
        if not target.is_relative_to(base):
            raise ValueError("object path escapes storage root")
        return target

    def delete_prefix(self, ref: str) -> list[str]:
        base = self.path_for_ref(ref)
        if not base.exists():
            return []
        if base.is_dir():
            shutil.rmtree(base, ignore_errors=True)
        else:
            base.unlink(missing_ok=True)
        return [str(base)]


default_store = LocalObjectStore()
