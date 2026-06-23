"""state.json の読み書き。これがツールの「記憶」。
投稿済みネタ・成果データ・改善された戦略をここに保存し、毎回commitして残す。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from .util import DATA_DIR

STATE_PATH = DATA_DIR / "state.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "version": 1,
            "topics_queue": [],
            "posted": [],
            "performance": {"by_topic": {}, "by_keyword": {}, "notes": []},
            "strategy": {"boost_keywords": [], "avoid_keywords": [], "last_updated": None},
        }
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_post(state: dict, post: dict) -> None:
    post["posted_at"] = now_iso()
    state.setdefault("posted", []).append(post)
