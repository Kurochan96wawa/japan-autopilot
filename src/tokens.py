"""アクセストークン自動更新。
落とし穴: Meta(IG/Threads)のlong-livedトークンは60日で失効し、失効すると再認証が必要。
Pinterestのアクセストークンも短命(約30日, refresh_tokenは約1年)。
→ 定期的に更新し、新トークンを GitHub Secrets に書き戻して無人運用を継続する。

必要な追加Secrets（任意・自動更新したい場合のみ）:
  GH_PAT              … repo の Secrets を更新できるPersonal Access Token
  GH_REPO             … "owner/repo"
  PINTEREST_REFRESH_TOKEN, PINTEREST_APP_ID, PINTEREST_APP_SECRET … Pinterest更新用

CLI: python -m src.tokens refresh
"""
from __future__ import annotations
import os
import sys
import base64
import requests
from .util import log


# ---------- GitHub Secrets 書き戻し ----------
def _gh_update_secret(name: str, value: str) -> bool:
    pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GH_REPO")
    if not pat or not repo:
        log.warning("GH_PAT/GH_REPO未設定。%s は更新せずログのみ。", name)
        return False
    try:
        from nacl import encoding, public
    except ImportError:
        log.error("pynaclが必要: pip install pynacl")
        return False
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    pk = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
                      headers=h, timeout=30).json()
    sealed = public.SealedBox(public.PublicKey(pk["key"], encoding.Base64Encoder))
    enc = base64.b64encode(sealed.encrypt(value.encode())).decode()
    r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        headers=h, json={"encrypted_value": enc, "key_id": pk["key_id"]}, timeout=30)
    ok = r.status_code in (201, 204)
    log.info("Secret更新 %s: %s", name, "OK" if ok else f"NG {r.status_code} {r.text}")
    return ok


# ---------- Meta (Threads / Instagram) ----------
def refresh_meta(kind: str) -> str | None:
    """kind: 'threads' | 'instagram'"""
    if kind == "threads":
        token = os.environ.get("THREADS_ACCESS_TOKEN")
        url = "https://graph.threads.net/refresh_access_token"
        grant = "th_refresh_token"
        secret_name = "THREADS_ACCESS_TOKEN"
    else:
        token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        url = "https://graph.instagram.com/refresh_access_token"
        grant = "ig_refresh_token"
        secret_name = "INSTAGRAM_ACCESS_TOKEN"
    if not token:
        log.info("%s トークン未設定。スキップ。", kind)
        return None
    r = requests.get(url, params={"grant_type": grant, "access_token": token}, timeout=30)
    if r.status_code >= 400:
        log.error("%s 更新失敗 %s: %s", kind, r.status_code, r.text)
        return None
    new = r.json().get("access_token")
    if new:
        _gh_update_secret(secret_name, new)
    return new


# ---------- Pinterest ----------
def refresh_pinterest() -> str | None:
    rt = os.environ.get("PINTEREST_REFRESH_TOKEN")
    cid = os.environ.get("PINTEREST_APP_ID")
    cs = os.environ.get("PINTEREST_APP_SECRET")
    if not (rt and cid and cs):
        log.info("Pinterest更新用の情報未設定。スキップ（手動更新でも可）。")
        return None
    basic = base64.b64encode(f"{cid}:{cs}".encode()).decode()
    r = requests.post(
        "https://api.pinterest.com/v5/oauth/token",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": rt}, timeout=30)
    if r.status_code >= 400:
        log.error("Pinterest更新失敗 %s: %s", r.status_code, r.text)
        return None
    new = r.json().get("access_token")
    if new:
        _gh_update_secret("PINTEREST_ACCESS_TOKEN", new)
    return new


def refresh_all():
    log.info("トークン更新開始")
    refresh_pinterest()
    refresh_meta("instagram")
    refresh_meta("threads")
    log.info("トークン更新完了")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        refresh_all()
    else:
        print("usage: python -m src.tokens refresh")
