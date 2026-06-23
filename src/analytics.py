"""週次の改善ループ。
過去のPin成果を集計 → LLMに渡して「伸ばすキーワード/避けるテーマ」を更新 →
strategy として state に保存。次回以降のネタ生成・記事生成がこれを参照する＝自己改善。
"""
from __future__ import annotations
from datetime import date, timedelta
from .util import log
from .llm import generate
from . import publish_pinterest as pin
from .state import now_iso


def collect_metrics(state: dict) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=30)
    rows = []
    for p in state.get("posted", [])[-60:]:
        pid = p.get("pinterest_pin_id")
        if not pid:
            continue
        a = pin.get_pin_analytics(pid, start.isoformat(), end.isoformat())
        summary = a.get("all", {}).get("summary_metrics", {}) if isinstance(a, dict) else {}
        rows.append({
            "topic": p.get("topic"),
            "keyword": p.get("primary_keyword"),
            "impressions": summary.get("IMPRESSION", 0),
            "pin_clicks": summary.get("PIN_CLICK", 0),
            "outbound_clicks": summary.get("OUTBOUND_CLICK", 0),
            "saves": summary.get("SAVE", 0),
        })
    return rows


def update_strategy(state: dict) -> dict:
    rows = collect_metrics(state)
    if not rows:
        log.info("成果データなし。strategyは現状維持。")
        return state

    prompt = f"""You are optimizing a Pinterest content strategy.
Here is per-post performance (last 30 days):
{rows}

Based on what drives impressions, saves and especially OUTBOUND clicks (= traffic that
can convert to affiliate revenue), decide what to do next.

Return ONLY JSON:
{{
  "boost_keywords": ["<keywords/themes to make MORE of, max 8>"],
  "avoid_keywords": ["<themes that underperform, max 8>"],
  "notes": "<2-3 sentence human-readable takeaway>"
}}"""
    try:
        out = generate(prompt, as_json=True)
        strat = state.setdefault("strategy", {})
        strat["boost_keywords"] = out.get("boost_keywords", [])[:8]
        strat["avoid_keywords"] = out.get("avoid_keywords", [])[:8]
        strat["last_updated"] = now_iso()
        state.setdefault("performance", {}).setdefault("notes", []).append(
            {"at": now_iso(), "note": out.get("notes", "")}
        )
        log.info("strategy更新: boost=%s avoid=%s", strat["boost_keywords"], strat["avoid_keywords"])
    except Exception as e:
        log.error("strategy更新失敗: %s", e)
    return state
