"""施策F: メール配信（ESP）への昇格スキャフォールド。

現状: web3forms で購読者の「取得」のみ（leadmagnet.py）。自動配信・出発前シーケンスには ESP が要る。
このモジュールは Kit(ConvertKit) / Beehiiv 等の ESP に購読者を登録する薄いクライアント。

★Kei作業（ブロッカー・私が代行不可）★
  1. ESPアカウントを作成（Kit または Beehiiv。無料枠あり）。
  2. APIキー/フォームID を発行。
  3. リポジトリ Secrets に投入:
       ESP_PROVIDER = "kit" もしくは "beehiiv"
       （Kit）   KIT_API_KEY, KIT_FORM_ID
       （Beehiiv）BEEHIIV_API_KEY, BEEHIIV_PUBLICATION_ID
  4. 活性化後、leadmagnet のフォーム送信後 or 別ジョブから subscribe(email) を呼ぶよう配線。

Secrets 未投入なら全関数が安全に no-op（fail closed）＝既存運用を一切壊さない。
※ ESP の API 仕様は変わりうる。活性化時に各社の最新ドキュメントで確認すること。
"""
from __future__ import annotations
import os

import requests

from .util import log


def _provider() -> str:
    return (os.environ.get("ESP_PROVIDER") or "").strip().lower()


def is_active() -> bool:
    """ESPが使える状態か（Secretsが揃っているか）。"""
    p = _provider()
    if p == "kit":
        return bool(os.environ.get("KIT_API_KEY") and os.environ.get("KIT_FORM_ID"))
    if p == "beehiiv":
        return bool(os.environ.get("BEEHIIV_API_KEY") and os.environ.get("BEEHIIV_PUBLICATION_ID"))
    return False


def subscribe(email: str) -> bool:
    """購読者をESPに登録。ESP未設定なら no-op（False）。失敗しても例外は投げない（fail closed）。"""
    if not email or "@" not in email:
        return False
    if not is_active():
        log.info("email_api: ESP未設定のためsubscribe skip（Kei: ESPアカウント＋Secrets投入で活性化）")
        return False
    p = _provider()
    try:
        if p == "kit":
            r = requests.post(
                f"https://api.kit.com/v4/forms/{os.environ['KIT_FORM_ID']}/subscribers",
                headers={"X-Kit-Api-Key": os.environ["KIT_API_KEY"]},
                json={"email_address": email}, timeout=20)
        elif p == "beehiiv":
            pid = os.environ["BEEHIIV_PUBLICATION_ID"]
            r = requests.post(
                f"https://api.beehiiv.com/v2/publications/{pid}/subscriptions",
                headers={"Authorization": f"Bearer {os.environ['BEEHIIV_API_KEY']}"},
                json={"email": email, "reactivate_existing": True}, timeout=20)
        else:
            return False
        ok = r.status_code < 300
        log.info("email_api: subscribe %s -> HTTP %s", p, r.status_code)
        return ok
    except Exception as e:
        log.error("email_api: subscribe失敗: %s", e)
        return False


def main() -> None:
    # 活性化確認用（Secrets投入後に手動テスト: python -m src.email_api）。
    log.info("email_api active=%s provider=%s", is_active(), _provider() or "(none)")


if __name__ == "__main__":
    main()
