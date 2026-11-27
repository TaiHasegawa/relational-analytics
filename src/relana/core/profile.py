"""入力の構造だけを返す（原則5: 生データをコンテキストに入れない）。

エージェントがアダプタを書くために必要なのは「どんな形か」であって
「中身が何か」ではない。実データ値は既定で出さない。
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

MASK = "<値は表示しません>"


def profile_path(path: Path, max_files: int = 20) -> dict[str, Any]:
    if path.is_dir():
        files = sorted(
            p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".csv", ".json", ".jsonl", ".tsv"}
        )
        return {
            "kind": "directory",
            "path": str(path),
            "file_count": len(files),
            "files": [profile_file(p) for p in files[:max_files]],
            "note": "実データの値は表示していません。構造のみです。",
        }
    return {"kind": "file", **profile_file(path), "note": "実データの値は表示していません。構造のみです。"}


def profile_file(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "format": path.suffix.lstrip(".").lower(),
    }
    try:
        if path.suffix.lower() in {".csv", ".tsv"}:
            info.update(_profile_csv(path))
        elif path.suffix.lower() == ".jsonl":
            info.update(_profile_jsonl(path))
        elif path.suffix.lower() == ".json":
            info.update(_profile_json(path))
    except Exception as e:  # noqa: BLE001
        info["error"] = f"読み取れませんでした: {type(e).__name__}"
    return info


def _profile_csv(path: Path) -> dict[str, Any]:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        cols = reader.fieldnames or []
        counts = {c: Counter() for c in cols}
        rows = 0
        for row in reader:
            rows += 1
            for c in cols:
                v = (row.get(c) or "").strip()
                counts[c][v] += 1
            if rows >= 50000:
                break
    return {
        "rows_scanned": rows,
        "columns": [
            {
                "name": c,
                "distinct": len([k for k in counts[c] if k]),
                "blank_rate": round(counts[c].get("", 0) / rows, 3) if rows else None,
                "inferred_type": _infer_type(counts[c]),
                "looks_like": _looks_like(c, counts[c]),
            }
            for c in cols
        ],
    }


def _profile_jsonl(path: Path) -> dict[str, Any]:
    keys = Counter()
    rows = 0
    sample: dict[str, Any] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            if isinstance(obj, dict):
                keys.update(obj.keys())
                if not sample:
                    sample = _shape(obj)
            if rows >= 20000:
                break
    return {"rows_scanned": rows, "keys": dict(keys.most_common()), "shape": sample}


def _profile_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return {
            "rows_scanned": len(obj),
            "shape": _shape(obj[0]) if obj and isinstance(obj[0], dict) else type(obj[0]).__name__,
        }
    return {"shape": _shape(obj)}


def _shape(obj: Any, depth: int = 0) -> Any:
    """値を伏せて型と構造だけを返す。"""
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        return {k: _shape(v, depth + 1) for k, v in list(obj.items())[:40]}
    if isinstance(obj, list):
        return [_shape(obj[0], depth + 1), f"...（{len(obj)}件）"] if obj else []
    return type(obj).__name__


def _infer_type(counter: Counter) -> str:
    vals = [v for v in counter if v][:200]
    if not vals:
        return "empty"
    if all(_is_int(v) for v in vals):
        return "integer"
    if all(_is_float(v) for v in vals):
        return "number"
    if all(_is_dt(v) for v in vals):
        return "datetime"
    if all(v.lower() in {"true", "false"} for v in vals):
        return "boolean"
    return "string"


def _looks_like(name: str, counter: Counter) -> str | None:
    """列名と形から、共通スキーマのどの列に対応しそうかを示す。"""
    low = name.lower()
    hints = {
        "ts": ["time", "date", "start", "when"],
        "actor_id": ["organizer", "from", "host", "sender", "owner"],
        "target_ids": ["attendee", "participant", "guest", "to", "invitee"],
        "event_id": ["id", "uid"],
        "duration_min": ["duration", "minutes", "length"],
        "email": ["mail"],
        "dept": ["dept", "department", "division", "org", "部門", "部署"],
    }
    for target, needles in hints.items():
        if any(nd in low for nd in needles):
            return target
    vals = [v for v in counter if v][:50]
    if vals and all("@" in v for v in vals):
        return "email"
    return None


def _is_int(v: str) -> bool:
    try:
        int(v)
        return True
    except ValueError:
        return False


def _is_float(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _is_dt(v: str) -> bool:
    from datetime import datetime

    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False
