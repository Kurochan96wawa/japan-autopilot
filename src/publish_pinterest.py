"""Pinterest API v5 で Pin を作成する。
- 画像URL方式（site側の画像URL）でPinを作るのが安定。
- ボードIDは初回に取得/作成してキャッシュ。
公式: https://developers.pinterest.com/docs/api/v5/
"""
from __future__ import annotations
import os
import requests
from .util import log, load_settings

API = "https://api.pinterest.com/v5"


def _headers():
    token = os.environ["PINTEREST_ACCESS_TOKEN"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def list_boards() -> dict:
    r = requests.get(f"{API}/boards", headers=_headers(), timeout=60)
    r.raise_for_status()
    return {b["name"]: b["id"] for b in r.json().get("items", [])}


def ensure_board(name: str, cache: dict) -> str:
    if name in cache:
        return cache[name]
    boards = list_boards()
    if name in boards:
        cache[name] = boards[name]
        return boards[name]
    # 無ければ作成
    r = requests.post(f"{API}/boards", headers=_headers(),
                      json={"name": name, "privacy": "PUBLIC"}, timeout=60)
    r.raise_for_status()
    bid = r.json()["id"]
    cache[name] = bid
    log.info("ボード作成: %s", name)
    return bid


def pick_board(content: dict, settings: dict, cache: dict) -> str:
    boards = settings["pinterest"]["default_boards"]
    hint = (content.get("board_hint") or "").lower()
    chosen = next((b for b in boards if any(w in hint for w in b.lower().split())), boards[0])
    return ensure_board(chosen, cache)


def create_pin(content: dict, image_url: str, link_url: str, board_id: str,
               extra_tags: str = "") -> dict:
    desc = content["pin_description"]
    # アフィリ誘導Pinには開示ハッシュタグを付与（Pinterest 2026ルール & FTC）
    if extra_tags and extra_tags not in desc:
        desc = f"{desc} {extra_tags}"
    payload = {
        "board_id": board_id,
        "title": content["pin_title"][:100],
        "description": desc[:500],
        "link": link_url,
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    r = requests.post(f"{API}/pins", headers=_headers(), json=payload, timeout=90)
    if r.status_code >= 400:
        log.error("Pin作成失敗 %s: %s", r.status_code, r.text)
        r.raise_for_status()
    pin = r.json()
    log.info("Pin作成成功: id=%s", pin.get("id"))
    return pin


def get_pin_analytics(pin_id: str, start: str, end: str) -> dict:
    try:
        r = requests.get(
            f"{API}/pins/{pin_id}/analytics", headers=_headers(),
            params={"start_date": start, "end_date": end,
                    "metric_types": "IMPRESSION,PIN_CLICK,OUTBOUND_CLICK,SAVE"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("Pin分析取得失敗 %s: %s", pin_id, e)
        return {}
