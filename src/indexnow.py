# -*- coding: utf-8 -*-
"""IndexNow で Bing/Yandex/Naver/Seznam 等に新規・更新URLを即時通知し、
インデックスを早める。※Google は IndexNow 非対応 → sitemap.xml(既存)で対応。

キーは公開情報（https://littletabi.com/<KEY>.txt で所有確認される）なので
ハードコードで問題ない。env INDEXNOW_KEY があればそちらを優先。"""
from __future__ import annotations
import os

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

# 公開キー（docs/<KEY>.txt として配信され所有確認に使う）
DEFAULT_KEY = "be64c0067fb61155d2b8064244f08721"
KEY = os.environ.get("INDEXNOW_KEY", DEFAULT_KEY)
HOST = "littletabi.com"


def write_key_file(docs_dir: str = "docs") -> None:
    """キー確認用ファイルを docs/ に出力（rebuild時に毎回呼んでOK）。"""
    if not KEY:
        return
    try:
        os.makedirs(docs_dir, exist_ok=True)
        with open(os.path.join(docs_dir, KEY + ".txt"), "w", encoding="utf-8") as f:
            f.write(KEY)
    except Exception as e:  # pragma: no cover
        print("IndexNow key file write failed:", e)


def ping(urls) -> None:
    """新規/更新URLを IndexNow に通知。失敗は握りつぶす（運用を止めない）。"""
    if not requests or not KEY or not urls:
        return
    urls = [u for u in dict.fromkeys(urls) if u]  # 重複除去
    if not urls:
        return
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": f"https://{HOST}/{KEY}.txt",
        "urlList": urls[:10000],
    }
    try:
        r = requests.post("https://api.indexnow.org/indexnow",
                          json=payload, timeout=20)
        print(f"IndexNow: {r.status_code} ({len(urls)} urls)")
    except Exception as e:
        print("IndexNow ping failed:", e)
