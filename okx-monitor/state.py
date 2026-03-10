from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def push_history(state: dict, inst_id: str, snapshot: dict, limit: int = 50) -> dict:
    item = state.setdefault(inst_id, {})
    history = item.setdefault("history", [])
    history.append(snapshot)
    if len(history) > limit:
        del history[:-limit]
    item.update(snapshot)
    return state
