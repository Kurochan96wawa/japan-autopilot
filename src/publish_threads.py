"""Threads (Meta公式 Graph API) で投稿する。
2段階: (1)メディアコンテナ作成 → (2)publish。
重要: 投稿間隔は5分以上必須（settingsで余裕を持って制御）。
公式: https://developers.facebook.com/docs/threads
"""
from __future__ import annotations
import os
import time
import requests
from .util import log

API = "https://graph.threads.net/v1.0"


def _creds():
    return os.environ["THREADS_USER_ID"], os.environ["THREADS_ACCESS_TOKEN"]


def post_text(text: str, link: str | None = None) -> dict:
    user_id, token = _creds()
    body = text if not link else f"{text}\n{link}"
    # 1) コンテナ作成
    r = requests.post(
        f"{API}/{user_id}/threads",
        data={"media_type": "TEXT", "text": body[:500], "access_token": token},
        timeout=60,
    )
    if r.status_code >= 400:
        log.error("Threadsコンテナ失敗 %s: %s", r.status_code, r.text)
        r.raise_for_status()
    creation_id = r.json()["id"]
    # Metaは作成直後のpublishを推奨しないので少し待つ
    time.sleep(5)
    # 2) publish
    r2 = requests.post(
        f"{API}/{user_id}/threads_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60,
    )
    if r2.status_code >= 400:
        log.error("Threads publish失敗 %s: %s", r2.status_code, r2.text)
        r2.raise_for_status()
    out = r2.json()
    log.info("Threads投稿成功: id=%s", out.get("id"))
    return out
