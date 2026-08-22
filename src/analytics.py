"""週次の改善ループ（④週次PDCA）。

2系統:
  1) update_strategy … Pinterest成果をLLMに渡し boost/avoid キーワードを更新（従来）。
  2) weekly_pdca     … GA4(ページ閲覧) と Pinterest(露出/外部クリック) を突き合わせ、
                       各記事を Winner/Fixable/Loser/データ不足 に分類 →
                       戦略へ反映＋Fixableにフラグ＋週次レポート(data/weekly_report.md)を生成。
しきい値は config/pdca.yaml に外出し（コードを触らず基準変更できる）。
GA4鍵が未登録でも Pinterest 指標のみで動く（グレースフルデグレード）。
"""
from __future__ import annotations
from datetime import date, timedelta
import yaml

from .util import log, CONFIG_DIR, DATA_DIR
from .llm import generate
from . import publish_pinterest as pin
from . import ga4
from .state import now_iso


# ============================================================
# 既存: Pinterest成果の集計 と LLMによる戦略更新
# ============================================================
def collect_metrics(state: dict) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=30)
    rows = []
    for p in state.get("posted", [])[-60:]:
        pid = p.get("pinterest_pin_id")
        if not pid:
            continue
        try:
            a = pin.get_pin_analytics(pid, start.isoformat(), end.isoformat())
        except Exception as e:
            log.warning("Pin分析取得失敗(0扱い) %s: %s", pid, e)
            a = {}
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


# ============================================================
# ④週次PDCA: GA4×Pinterestで分類 → 改善 → レポート
# ============================================================
_PDCA_DEFAULTS = {
    "ga4": {"enabled": True, "lookback_days": 28},
    "classify": {
        "min_impressions_to_judge": 30,
        "winner": {"min_pageviews": 50, "min_outbound_ctr": 0.02},
        "loser": {"max_pageviews": 5, "max_outbound_ctr": 0.003},
    },
    "fix": {
        "enabled": True, "max_fixes_per_week": 3, "flag_for_repin": True,
        "rewrite_article": False, "avoid_loser_keywords": True, "boost_winner_keywords": True,
    },
    "report": {"write_markdown": True, "path": "data/weekly_report.md", "keep_history_weeks": 12},
}


def load_pdca() -> dict:
    """config/pdca.yaml を読み、欠けたキーは既定値で補完して返す。"""
    path = CONFIG_DIR / "pdca.yaml"
    cfg = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            log.error("pdca.yaml読込失敗(既定値を使用): %s", e)
    merged = {k: dict(v) for k, v in _PDCA_DEFAULTS.items()}
    for k, v in (cfg or {}).items():
        if isinstance(v, dict):
            merged.setdefault(k, {})
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def _pin_metrics_for(post: dict, start: str, end: str) -> dict:
    pid = post.get("pinterest_pin_id")
    if not pid:
        return {"impressions": 0, "outbound_clicks": 0, "saves": 0, "pin_clicks": 0}
    try:
        a = pin.get_pin_analytics(pid, start, end)
        s = a.get("all", {}).get("summary_metrics", {}) if isinstance(a, dict) else {}
    except Exception as e:
        log.warning("Pin分析取得失敗(0扱い) %s: %s", pid, e)
        s = {}
    return {
        "impressions": int(s.get("IMPRESSION", 0) or 0),
        "outbound_clicks": int(s.get("OUTBOUND_CLICK", 0) or 0),
        "saves": int(s.get("SAVE", 0) or 0),
        "pin_clicks": int(s.get("PIN_CLICK", 0) or 0),
    }


def _ga4_pv_for(slug: str, ga_pages: dict) -> dict:
    """GA4のpagePath群から、このslugを含むパスのPV等を合算して返す。"""
    if not slug or not ga_pages:
        return {"pageviews": 0, "sessions": 0, "avg_engagement_sec": 0.0}
    pv = sessions = 0
    eng = 0.0
    hits = 0
    for path, m in ga_pages.items():
        if slug in path:
            pv += m.get("pageviews", 0)
            sessions += m.get("sessions", 0)
            eng += m.get("avg_engagement_sec", 0.0)
            hits += 1
    return {
        "pageviews": pv,
        "sessions": sessions,
        "avg_engagement_sec": round(eng / hits, 1) if hits else 0.0,
    }


def _classify_one(post: dict, pin_m: dict, ga_m: dict, cl: dict) -> dict:
    imp = pin_m["impressions"]
    out = pin_m["outbound_clicks"]
    pv = ga_m["pageviews"]
    ctr = (out / imp) if imp else 0.0

    win = cl["winner"]
    lose = cl["loser"]
    min_imp = cl["min_impressions_to_judge"]

    if imp < min_imp and pv < win["min_pageviews"]:
        label, reason = "Insufficient", f"露出{imp}/PV{pv}（データ不足・新しすぎ）"
    elif pv >= win["min_pageviews"] or ctr >= win["min_outbound_ctr"]:
        label, reason = "Winner", f"PV{pv} / CTR{ctr:.1%}"
    elif pv <= lose["max_pageviews"] and ctr <= lose["max_outbound_ctr"]:
        label, reason = "Loser", f"PV{pv} / CTR{ctr:.1%}（低調）"
    else:
        label, reason = "Fixable", f"PV{pv} / CTR{ctr:.1%}（露出はあるが伸び切らない）"

    return {
        "slug": post.get("slug", ""),
        "title": post.get("article_title", post.get("topic", "")),
        "keyword": post.get("primary_keyword", ""),
        "url": post.get("url", ""),
        "impressions": imp,
        "outbound_clicks": out,
        "outbound_ctr": round(ctr, 4),
        "pageviews": pv,
        "avg_engagement_sec": ga_m["avg_engagement_sec"],
        "label": label,
        "reason": reason,
        "post": post,
    }


def classify_posts(state: dict, pdca: dict, ga_pages: dict) -> list[dict]:
    lookback = int(pdca["ga4"].get("lookback_days", 28))
    end = date.today()
    start = end - timedelta(days=lookback)
    cl = pdca["classify"]
    results = []
    for post in state.get("posted", [])[-80:]:
        if not post.get("slug"):
            continue
        pin_m = _pin_metrics_for(post, start.isoformat(), end.isoformat())
        ga_m = _ga4_pv_for(post["slug"], ga_pages)
        results.append(_classify_one(post, pin_m, ga_m, cl))
    return results


def _merge_keywords(existing: list, add: list, cap: int = 8) -> list:
    seen = list(existing or [])
    for k in add:
        if k and k not in seen:
            seen.append(k)
    return seen[:cap]


def _write_report(results: list[dict], strat: dict, pdca: dict, ga_on: bool) -> str:
    buckets = {"Winner": [], "Fixable": [], "Loser": [], "Insufficient": []}
    for r in results:
        buckets.get(r["label"], buckets["Insufficient"]).append(r)
    for b in buckets.values():
        b.sort(key=lambda r: (r["pageviews"], r["outbound_ctr"]), reverse=True)

    today = date.today().isoformat()
    lines = [
        f"# 週次PDCAレポート {today}",
        "",
        f"- GA4: {'利用可' if ga_on else '未接続（鍵未登録のためPinterest指標のみで判定）'}"
        f" / 集計期間: 直近{pdca['ga4'].get('lookback_days', 28)}日",
        f"- 対象記事: {len(results)}件 "
        f"（Winner {len(buckets['Winner'])} / Fixable {len(buckets['Fixable'])} / "
        f"Loser {len(buckets['Loser'])} / データ不足 {len(buckets['Insufficient'])}）",
        "",
    ]

    def section(title, rows, note):
        lines.append(f"## {title}")
        lines.append(note)
        if not rows:
            lines.append("- （該当なし）")
        for r in rows[:15]:
            lines.append(
                f"- **{r['title']}** — PV {r['pageviews']}, "
                f"outbound {r['outbound_clicks']} (CTR {r['outbound_ctr']:.1%}), "
                f"imp {r['impressions']}  `{r['slug']}`"
            )
        lines.append("")

    section("Winners（伸びている → 横展開）", buckets["Winner"],
            "勝ち筋。似たテーマ・キーワードを増やす。boost_keywordsに反映済み。")
    section("Fixable（露出はあるが伸び切らない → テコ入れ）", buckets["Fixable"],
            "新角度の再Pin/本文補強の対象。needs_refreshフラグを付与。")
    section("Losers（低調 → 避ける/作り直し候補）", buckets["Loser"],
            "テーマ自体が弱い可能性。avoid_keywordsに反映済み。")
    section("データ不足（新しすぎ・判定保留）", buckets["Insufficient"],
            "もう1〜2週ようすを見る。")

    lines += [
        "## 戦略アップデート",
        f"- boost_keywords: {strat.get('boost_keywords', [])}",
        f"- avoid_keywords: {strat.get('avoid_keywords', [])}",
        "",
        "_このレポートは weekly-improve により自動生成・上書きされます。_",
    ]
    return "\n".join(lines)


def weekly_pdca(state: dict, settings_cfg: dict | None = None) -> dict:
    """GA4×Pinterestで記事を分類→戦略反映→Fixableにフラグ→週次レポート生成。
    返り値 summary は state['performance']['pdca'] に保存。本文の作り直しが必要なら
    summary['rewrite_slugs'] にslug一覧を入れて返す（実際の再生成は main 側が担当）。"""
    pdca = load_pdca()
    ga_on = bool(pdca["ga4"].get("enabled", True)) and ga4.available()
    ga_pages = ga4.fetch_page_metrics(int(pdca["ga4"].get("lookback_days", 28))) if ga_on else {}

    results = classify_posts(state, pdca, ga_pages)

    winners = [r for r in results if r["label"] == "Winner"]
    fixables = [r for r in results if r["label"] == "Fixable"]
    losers = [r for r in results if r["label"] == "Loser"]

    strat = state.setdefault("strategy", {})
    fixcfg = pdca["fix"]
    if fixcfg.get("boost_winner_keywords", True):
        strat["boost_keywords"] = _merge_keywords(
            strat.get("boost_keywords", []),
            [r["keyword"] for r in winners if r["keyword"]],
        )
    if fixcfg.get("avoid_loser_keywords", True):
        strat["avoid_keywords"] = _merge_keywords(
            strat.get("avoid_keywords", []),
            [r["keyword"] for r in losers if r["keyword"]],
        )
    strat["last_updated"] = now_iso()

    max_fixes = int(fixcfg.get("max_fixes_per_week", 3))
    targeted = fixables[:max_fixes]
    rewrite_slugs = []
    for r in targeted:
        post = r["post"]
        if fixcfg.get("flag_for_repin", True):
            post["needs_refresh"] = True
        if fixcfg.get("enabled", True) and fixcfg.get("rewrite_article", False):
            rewrite_slugs.append(r["slug"])

    report_md = _write_report(results, strat, pdca, ga_on)
    rep_cfg = pdca["report"]
    if rep_cfg.get("write_markdown", True):
        try:
            rel = rep_cfg.get("path", "data/weekly_report.md")
            name = rel.split("/")[-1] or "weekly_report.md"
            out_path = DATA_DIR / name
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(report_md)
            log.info("週次レポート出力: %s", out_path)
        except Exception as e:
            log.error("週次レポート書き込み失敗: %s", e)

    summary = {
        "at": now_iso(),
        "ga4": ga_on,
        "counts": {
            "winner": len(winners), "fixable": len(fixables),
            "loser": len(losers),
            "insufficient": len([r for r in results if r["label"] == "Insufficient"]),
            "total": len(results),
        },
        "flagged_fixable": [r["slug"] for r in targeted],
        "rewrite_slugs": rewrite_slugs,
    }

    perf = state.setdefault("performance", {})
    hist = perf.setdefault("pdca_history", [])
    hist.append({k: v for k, v in summary.items() if k != "rewrite_slugs"})
    keep = int(rep_cfg.get("keep_history_weeks", 12))
    perf["pdca_history"] = hist[-keep:]
    perf["pdca"] = {k: v for k, v in summary.items() if k != "rewrite_slugs"}

    log.info("週次PDCA: %s (GA4=%s)", summary["counts"], ga_on)
    return summary
