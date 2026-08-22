"""Instagram (Meta Graph API) 補助投稿。
Pinに使った縦長画像をそのままフィード投稿に流用する＝視覚情報の使い回しで効率化。
2段階: (1)メディアコンテナ作成(image_url) → (2)publish。
公式: https://developers.facebook.com/docs/instagram-platform/content-publishing

注意:
 - テキストのみ投稿は不可（必ず画像/動画が要る）。本ツールはPin画像を使うので問題なし。
 - 1日25投稿まで。Businessアカウント + 連携が必要。
 - キャプションにアフィリ生リンクは貼らない（IGはリンク無効＆規約的に微妙）。
   プロフィールのlink-in-bio(=Hubサイト)へ誘導する文面にする。
"""
from __future__ import annotations
import os
import time
import requests
from .util import log

GRAPH = "https://graph.facebook.com/v21.0"


def _creds():
    return os.environ["INSTAGRAM_USER_ID"], os.environ["INSTAGRAM_ACCESS_TOKEN"]


def post_image(image_url: str, caption: str) -> dict:
    user_id, token = _creds()
    # 1) コンテナ作成
    r = requests.post(
        f"{GRAPH}/{user_id}/media",
        data={"image_url": image_url, "caption": caption[:2200], "access_token": token},
        timeout=90,
    )
    if r.status_code >= 400:
        log.error("IGコンテナ失敗 %s: %s", r.status_code, r.text)
        r.raise_for_status()
    creation_id = r.json()["id"]
    time.sleep(5)
    # 2) publish
    r2 = requests.post(
        f"{GRAPH}/{user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=90,
    )
    if r2.status_code >= 400:
        log.error("IG publish失敗 %s: %s", r2.status_code, r2.text)
        r2.raise_for_status()
    out = r2.json()
    log.info("Instagram投稿成功: id=%s", out.get("id"))
    return out
