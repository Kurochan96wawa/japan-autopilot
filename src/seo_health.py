# -*- coding: utf-8 -*-
"""無人運用の“早期検知”レイヤー。
Search Console の表示回数を前週比で見て、急落（ペナルティ/障害の代理シグナル）を検知。
立ち上げ期は『そもそも表示が出ているか（インデックス進捗）』も併せてレポートする。

注: 『手動による対策(Manual Action)』テキストは GSC API では取得できない（UIのみ）。
よって本モジュールは表示回数の急落を代理シグナルにし、weekly_report.md に要約を書く。"""
from __future__ import annotations
import os
import json
import datetime

SITE = os.environ.get("GSC_SITE_URL", "sc-domain:littletabi.com")
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _session():
    raw = os.environ.get("GA4_SERVICE_ACCOUNT_JSON")  # 既存Secretを流用
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return AuthorizedSession(creds)
    except Exception as e:
        print("seo_health: 認証不可:", e)
        return None


def _totals(sess, start: str, end: str):
    import requests as _rq
    site = _rq.utils.quote(SITE, safe="")
    url = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
           f"{site}/searchAnalytics/query")
    try:
        r = sess.post(url, json={"startDate": start, "endDate": end, "dimensions": []}, timeout=30)
        r.raise_for_status()
        rows = r.json().get("rows", [])
        if not rows:
            return 0, 0
        return int(rows[0].get("impressions", 0)), int(rows[0].get("clicks", 0))
    except Exception as e:
        print("seo_health: GSC取得失敗:", e)
        return 0, 0


def check(drop: float = 0.5) -> dict:
    """前週比で表示回数を比較。alert は『前週>50 かつ 今週が前週の(1-drop)未満』。"""
    sess = _session()
    if not sess:
        return {"ok": False, "reason": "no_credentials"}
    t = datetime.date.today()
    d = datetime.timedelta(days=7)
    this_imp, this_clk = _totals(sess, str(t - d), str(t))
    prev_imp, prev_clk = _totals(sess, str(t - 2 * d), str(t - d))
    alert = prev_imp > 50 and this_imp < prev_imp * (1 - drop)
    return {"ok": True, "alert": alert,
            "this_imp": this_imp, "prev_imp": prev_imp,
            "this_clk": this_clk, "prev_clk": prev_clk}


def report(drop: float = 0.5) -> str:
    """weekly_report.md に追記するMarkdown断片。"""
    r = check(drop)
    if not r.get("ok"):
        return "## サイト健全性（GSC）\n\n認証情報が無く未計測。\n"
    lines = ["## サイト健全性（GSC・表示回数の前週比）", ""]
    lines.append(f"- 今週: 表示 {r['this_imp']} / クリック {r['this_clk']}")
    lines.append(f"- 前週: 表示 {r['prev_imp']} / クリック {r['prev_clk']}")
    if r["alert"]:
        lines.append("- ⚠ 表示回数が前週比で急落。手動対策・インデックス障害・サイト不具合の可能性。"
                     "Search ConsoleのUIで『手動による対策』『セキュリティの問題』を確認すること。")
    elif r["prev_imp"] == 0 and r["this_imp"] == 0:
        lines.append("- まだ表示回数0。インデックス進行中（新規ドメインは数週かかる）。"
                     "URL検査での手動インデックス申請とサイトマップ送信を継続。")
    else:
        lines.append("- 急落なし。")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
