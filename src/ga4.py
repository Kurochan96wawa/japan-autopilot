"""GA4 Data API から記事ページの成果(PV/セッション/エンゲージ)を取得する。

必要な環境変数（GitHub Secrets）:
  - GA4_SERVICE_ACCOUNT_JSON … サービスアカウント鍵JSONの中身そのまま（または base64）
  - GA4_PROPERTY_ID           … 数値のプロパティID（Measurement ID G-... ではない）

依存: google-auth（requirements.txt に追加）。REST(analyticsdata v1beta)を直接叩くので
google-analytics-data(grpc)などの重い依存は不要。鍵未設定・取得失敗時は {} を返し、
週次PDCAは Pinterest 指標のみで継続する（1つの失敗で全体を落とさない設計）。
"""
from __future__ import annotations
import base64
import json
import os
from .util import log

_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
_RUN_REPORT = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"


def available() -> bool:
    return bool(os.environ.get("GA4_SERVICE_ACCOUNT_JSON") and os.environ.get("GA4_PROPERTY_ID"))


def _load_credentials():
    raw = os.environ.get("GA4_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        # 鍵をbase64文字列で貼ってある場合のフォールバック（GitHub Secretsで貼り崩れ対策）
        try:
            info = json.loads(base64.b64decode(raw))
        except Exception as e:
            log.error("GA4鍵のJSON/ base64パースに失敗: %s", e)
            return None
    try:
        from google.oauth2 import service_account  # 遅延import（未導入でも他機能は動く）
        return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    except Exception as e:
        log.error("GA4認証情報の構築に失敗(google-auth未導入?): %s", e)
        return None


def _access_token(creds) -> str | None:
    try:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        log.error("GA4アクセストークン取得失敗: %s", e)
        return None


def fetch_page_metrics(lookback_days: int = 28) -> dict:
    """{ pagePath: {pageviews, sessions, engagement_rate, avg_engagement_sec} } を返す。
    pagePath は "/articles/<slug>/" のようなパス。鍵未設定/失敗時は {}。"""
    pid = os.environ.get("GA4_PROPERTY_ID")
    if not pid:
        log.info("GA4_PROPERTY_ID未設定 → GA4集計はスキップ（PinterestのみでPDCA）")
        return {}
    creds = _load_credentials()
    if not creds:
        log.info("GA4サービスアカウント鍵が無効/未設定 → GA4集計はスキップ")
        return {}
    token = _access_token(creds)
    if not token:
        return {}

    import requests
    body = {
        "dateRanges": [{"startDate": f"{lookback_days}daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [
            {"name": "screenPageViews"},
            {"name": "sessions"},
            {"name": "engagementRate"},
            {"name": "userEngagementDuration"},
        ],
        "limit": 250,
    }
    try:
        r = requests.post(
            _RUN_REPORT.format(pid=pid),
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("GA4レポート取得失敗(集計はPinterestのみで継続): %s", e)
        return {}

    out: dict = {}
    for row in data.get("rows", []):
        dims = row.get("dimensionValues", [])
        mets = row.get("metricValues", [])
        if not dims:
            continue
        path = dims[0].get("value", "")

        def _num(i, cast=float, default=0):
            try:
                return cast(mets[i].get("value", default))
            except Exception:
                return default

        pv = _num(0, int)
        out[path] = {
            "pageviews": pv,
            "sessions": _num(1, int),
            "engagement_rate": _num(2, float),
            # userEngagementDuration は合計秒。PVで割って1閲覧あたりの目安に。
            "avg_engagement_sec": round(_num(3, float) / pv, 1) if pv else 0.0,
        }
    log.info("GA4: %dページ分の指標を取得（lookback=%d日）", len(out), lookback_days)
    return out
