"""GSC連動のSEO自己改善エンジン（⑤の本丸）。

Google Search Console の Search Analytics API で各ページの実クエリ・表示回数・CTR・
平均掲載順位を取得し、データに基づく具体的なSEO改善アクションを自動実行する:

  1) 低CTRページ … 実際に流入しているクエリに合わせて <title> と meta description を
     自動リライト（docs のHTMLを直接書き換え。本文は触らない＝安全・低コスト）。
  2) あと一歩ページ（掲載順位 8〜20位）… needs_refresh を立てて日次の再Pinで後押しし、
     週次レポートに「強化候補」として記載。
  3) コンテンツギャップ … 表示はあるが専用記事が無い検索クエリを新規ネタとして
     topics_queue に投入（勘ではなく実需ドリブンの新規記事）。

そして週次レポートに「SEO改善」セクションを追記する。

依存: google-auth（既存）。認証は GA4 と同じサービスアカウント鍵 GA4_SERVICE_ACCOUNT_JSON を
再利用（その鍵のメールを GSC プロパティに閲覧者として追加し、Search Console API を有効化しておく）。
サイトは GSC_SITE_URL（既定 "sc-domain:littletabi.com"）。鍵未設定/未接続なら安全にスキップする。

weekly-improve から `python -m src.main improve` の後に `python -m src.seo` で単独実行する。
"""
from __future__ import annotations
import base64
import json
import os
import re
from datetime import date, timedelta

from .util import load_settings, SITE_DIR, DATA_DIR, CONFIG_DIR, log
from .state import load_state, save_state, now_iso
from .llm import generate

try:
    import yaml
except Exception:
    yaml = None

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_QUERY_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"

# しきい値の既定値（config/pdca.yaml の seo: で上書き可能）
_SEO_DEFAULTS = {
    "enabled": True,
    "lookback_days": 28,
    "min_impressions": 20,        # これ未満の表示回数のページ/クエリは判断材料が薄いので除外
    "low_ctr_max": 0.02,          # CTRがこれ未満かつ上位なら「タイトル/メタ改善」対象
    "striking_min_pos": 8.0,      # 掲載順位がこの範囲なら「あと一歩」
    "striking_max_pos": 20.0,
    "max_title_rewrites": 3,      # 1週間にタイトル/メタを書き換える上限（変動の管理）
    "max_new_topics": 3,          # 1週間に投入する新規ネタの上限
}


def _load_seo_cfg() -> dict:
    cfg = dict(_SEO_DEFAULTS)
    path = CONFIG_DIR / "pdca.yaml"
    if yaml and path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for k, v in (data.get("seo") or {}).items():
                cfg[k] = v
        except Exception as e:
            log.error("pdca.yaml seo: 読込失敗(既定値): %s", e)
    return cfg


def _site_url() -> str:
    env = os.environ.get("GSC_SITE_URL")
    if env:
        return env
    try:
        from urllib.parse import urlparse
        host = urlparse(load_settings()["site"]["base_url"]).netloc
        if host:
            return "sc-domain:" + host
    except Exception:
        pass
    return ""


def _credentials():
    raw = os.environ.get("GA4_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        try:
            info = json.loads(base64.b64decode(raw))
        except Exception as e:
            log.error("GSC鍵パース失敗: %s", e)
            return None
    try:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    except Exception as e:
        log.error("GSC認証構築失敗(google-auth?): %s", e)
        return None


def available() -> bool:
    return bool(os.environ.get("GA4_SERVICE_ACCOUNT_JSON") and _site_url())


def _query(creds, site: str, body: dict) -> dict:
    from google.auth.transport.requests import Request
    import requests
    creds.refresh(Request())
    from urllib.parse import quote
    url = _QUERY_URL.format(site=quote(site, safe=""))
    r = requests.post(url, headers={"Authorization": f"Bearer {creds.token}"}, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_search_data(days: int):
    """(pages, queries) を返す。pagesは {url:{clicks,impressions,ctr,position}}、
    queriesは [{query,page,clicks,impressions,ctr,position}]。未接続/失敗時は ({}, [])。"""
    site = _site_url()
    creds = _credentials()
    if not site or not creds:
        log.info("GSC未接続（鍵/サイト未設定）→ SEO改善はスキップ")
        return {}, []
    end = date.today()
    start = end - timedelta(days=days)
    base = {"startDate": start.isoformat(), "endDate": end.isoformat(), "rowLimit": 500}
    try:
        pg = _query(creds, site, dict(base, dimensions=["page"]))
        qp = _query(creds, site, dict(base, dimensions=["query", "page"]))
    except Exception as e:
        log.error("GSC取得失敗(SEO改善スキップ): %s", e)
        return {}, []
    pages = {}
    for row in pg.get("rows", []):
        url = (row.get("keys") or [""])[0]
        pages[url] = {
            "clicks": row.get("clicks", 0), "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0.0), "position": row.get("position", 0.0),
        }
    queries = []
    for row in qp.get("rows", []):
        keys = row.get("keys") or ["", ""]
        queries.append({
            "query": keys[0], "page": keys[1] if len(keys) > 1 else "",
            "clicks": row.get("clicks", 0), "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0.0), "position": row.get("position", 0.0),
        })
    log.info("GSC: %dページ / %dクエリ取得", len(pages), len(queries))
    return pages, queries


def _slug_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    return name[:-5] if name.endswith(".html") else name


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _rewrite_title_meta(slug: str, queries: list, current_title: str, site_name: str) -> dict | None:
    """実際に流入しているクエリに合わせて <title> と meta description を作り直し、
    docs/<slug>.html を直接書き換える。成功時 {title, meta} を返す。"""
    path = SITE_DIR / f"{slug}.html"
    if not path.exists():
        return None
    qlist = ", ".join(q["query"] for q in queries[:8]) or "(none)"
    prompt = f"""You are an SEO editor improving a family-travel-in-Japan article's search snippet.
The page currently underperforms on click-through despite getting impressions.
Real Google search queries bringing impressions to this page: {qlist}
Current title tag: {current_title}

Write a better, honest title tag and meta description that match these searchers' intent and
raise click-through — specific and compelling, never clickbait, no ALL CAPS, no fake urgency.

Return ONLY JSON:
{{"title": "<= 60 characters, includes the core query intent>",
  "meta": "<= 155 characters, concrete and inviting, answers the searcher>"}}"""
    try:
        out = generate(prompt, as_json=True)
        new_title = (out.get("title") or "").strip()[:65]
        new_meta = (out.get("meta") or "").strip()[:160]
        if not new_title or not new_meta:
            return None
    except Exception as e:
        log.error("タイトル/メタ生成失敗 %s: %s", slug, e)
        return None

    def esc(s):
        return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    try:
        html = path.read_text(encoding="utf-8")
    except Exception:
        return None
    et, em = esc(new_title), esc(new_meta)
    html = re.sub(r"<title>.*?</title>", f"<title>{et} | {esc(site_name)}</title>", html, count=1, flags=re.S)
    # 注意: 以前ここが ("">) （ダブルクォート2つ）になっており、実在のHTML content="...">
    # に一度もマッチしていなかった。結果、title と og/twitter は改善されるのに
    # Googleがスニペットに使う <meta name="description"> だけが旧文面のまま残り続けていた
    # （2026-06-29のseo.py導入以降ずっと）。2026-08-22 修正。
    html = re.sub(r'(<meta name="description" content=")[^"]*(">)', rf"\1{em}\2", html, count=1)
    html = re.sub(r'(<meta property="og:title" content=")[^"]*(">)', rf"\1{et}\2", html, count=1)
    html = re.sub(r'(<meta property="og:description" content=")[^"]*(">)', rf"\1{em}\2", html, count=1)
    html = re.sub(r'(<meta name="twitter:title" content=")[^"]*(">)', rf"\1{et}\2", html, count=1)
    html = re.sub(r'(<meta name="twitter:description" content=")[^"]*(">)', rf"\1{em}\2", html, count=1)

    # 2026-08-22: <title> だけ書き換えて <h1> と JSON-LD headline を放置すると、
    # 「タイトルの約束」と「ページの見出し」が食い違う。Googleはこの乖離を検知すると
    # title を h1 側に書き戻すことがあり、せっかくのクエリ最適化が検索結果に反映されない。
    # 見出しと構造化データも新しいタイトルに揃える。
    html = re.sub(r"(<h1[^>]*>).*?(</h1>)", lambda m: m.group(1) + et + m.group(2),
                  html, count=1, flags=re.S)
    # JSON-LD の中はHTMLエスケープではなくJSONエスケープを使う（&amp; を入れてはいけない）
    jt = json.dumps(new_title)[1:-1]
    html = re.sub(r'("headline":\s*")(?:[^"\\]|\\.)*(")', lambda m: m.group(1) + jt + m.group(2),
                  html, count=1)

    path.write_text(html, encoding="utf-8")
    log.info("SEO: タイトル/メタ改善 %s → %s", slug, new_title)
    return {"title": new_title, "meta": new_meta}


def run_seo_improve(state: dict) -> str:
    """SEO改善を実行し、週次レポートに追記するMarkdown断片を返す。"""
    seo = _load_seo_cfg()
    if not seo.get("enabled", True):
        return ""
    cfg = load_settings()
    site_name = cfg["site"]["site_name"]
    if not available():
        section = ("\n## SEO改善（GSC連動）\n"
                   "- GSC未接続（サービスアカウントをGSCに追加 + Search Console API有効化 + "
                   "GSC_SITE_URL 設定で有効化されます）。接続後、低CTRページのタイトル自動改善・"
                   "あと一歩ページの強化・実需クエリからの新規ネタ起案が回り始めます。\n")
        _append_report(section)
        return section

    pages, queries = fetch_search_data(int(seo["lookback_days"]))
    if not pages:
        section = "\n## SEO改善（GSC連動）\n- まだ検索データがありません（インデックス進行待ち）。次週から判定します。\n"
        _append_report(section)
        return section

    min_impr = int(seo["min_impressions"])
    # slug -> post 参照
    by_slug = {p.get("slug"): p for p in state.get("posted", []) if p.get("slug")}
    # ページごとの代表クエリ
    q_by_page = {}
    for q in queries:
        q_by_page.setdefault(q["page"], []).append(q)
    for lst in q_by_page.values():
        lst.sort(key=lambda x: x["impressions"], reverse=True)

    rewritten, striking, new_topics = [], [], []

    # 1) 低CTRページのタイトル/メタ改善
    cand = []
    for url, m in pages.items():
        if m["impressions"] < min_impr:
            continue
        if m["ctr"] < float(seo["low_ctr_max"]) and m["position"] <= float(seo["striking_max_pos"]) + 10:
            cand.append((url, m))
    cand.sort(key=lambda x: x[1]["impressions"], reverse=True)
    for url, m in cand[: int(seo["max_title_rewrites"])]:
        slug = _slug_from_url(url)
        post = by_slug.get(slug)
        cur_title = post.get("article_title", slug) if post else slug
        res = _rewrite_title_meta(slug, q_by_page.get(url, []), cur_title, site_name)
        if res:
            if post is not None:
                post["seo_title"] = res["title"]
                post["needs_refresh"] = True
            rewritten.append((slug, res["title"], m))

    # 2) あと一歩ページ（8〜20位）
    for url, m in pages.items():
        if m["impressions"] < min_impr:
            continue
        if float(seo["striking_min_pos"]) <= m["position"] <= float(seo["striking_max_pos"]):
            slug = _slug_from_url(url)
            post = by_slug.get(slug)
            if post is not None:
                post["needs_refresh"] = True
            striking.append((slug, m))
    striking.sort(key=lambda x: x[1]["impressions"], reverse=True)

    # 3) コンテンツギャップ（表示はあるが専用記事が無いクエリ）→ 新規ネタ
    # 判定の核: GSC上でそのクエリがホームページに着地している = 専用記事が無くGoogleがhomeを出している。
    base = cfg["site"]["base_url"].rstrip("/")
    existing = [_norm(s) for s in by_slug.keys()]
    topics_q = state.setdefault("topics_queue", [])
    existing_topics = {_norm(t.get("topic", "") if isinstance(t, dict) else t) for t in topics_q}
    seen = set()
    gap = []
    for q in sorted(queries, key=lambda x: x["impressions"], reverse=True):
        nq = _norm(q["query"])
        if not nq or nq in seen or q["impressions"] < min_impr:
            continue
        seen.add(nq)
        # 着地ページが個別記事なら、その記事が既にそのクエリを担っている＝ギャップではない
        landing = (q.get("page") or "").rstrip("/")
        if landing and landing != base:
            continue
        # 既存slug/既存ネタが実質そのクエリを内包していれば除外（語が全て含まれる）
        if any(all(w in e for w in nq.split()) for e in existing):
            continue
        if nq in existing_topics:
            continue
        gap.append(q)
    for q in gap[: int(seo["max_new_topics"])]:
        title = q["query"].strip().title()
        topics_q.append({"topic": f"{title} (Japan with kids)", "primary_keyword": q["query"].strip(),
                         "source": "gsc_gap", "added_at": now_iso()})
        new_topics.append(q)
    if new_topics:
        existing_topics  # noqa

    # --- レポート ---
    lines = ["\n## SEO改善（GSC連動）",
             f"- 集計: 直近{seo['lookback_days']}日 / 対象ページ{len(pages)} / クエリ{len(queries)}"]
    lines.append("\n### タイトル/メタを自動改善（低CTR）")
    if rewritten:
        for slug, title, m in rewritten:
            lines.append(f"- `{slug}` → 「{title}」（imp {m['impressions']}, CTR {m['ctr']:.1%}, 順位 {m['position']:.1f}）")
    else:
        lines.append("- （該当なし）")
    lines.append("\n### あと一歩ページ（8〜20位 → 強化＋再Pin優先）")
    if striking:
        for slug, m in striking[:10]:
            lines.append(f"- `{slug}`（順位 {m['position']:.1f}, imp {m['impressions']}, CTR {m['ctr']:.1%}）")
    else:
        lines.append("- （該当なし）")
    lines.append("\n### 新規ネタ起案（検索需要はあるが記事が無いクエリ）")
    if new_topics:
        for q in new_topics:
            lines.append(f"- 「{q['query']}」（imp {q['impressions']}, 順位 {q['position']:.1f}）→ topics_queueへ投入")
    else:
        lines.append("- （該当なし）")
    section = "\n".join(lines) + "\n"

    state.setdefault("performance", {})["seo"] = {
        "at": now_iso(), "rewritten": [s for s, _, _ in rewritten],
        "striking": [s for s, _ in striking[:10]], "new_topics": [q["query"] for q in new_topics],
    }
    _append_report(section)
    log.info("SEO改善: リライト%d / あと一歩%d / 新規ネタ%d",
             len(rewritten), len(striking), len(new_topics))
    return section


def _append_report(section: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / "weekly_report.md"
        with open(path, "a", encoding="utf-8") as f:
            f.write(section)
    except Exception as e:
        log.error("SEOレポート追記失敗: %s", e)


def main() -> None:
    state = load_state()
    try:
        run_seo_improve(state)
    except Exception as e:
        log.error("SEO改善 実行失敗(他工程は継続): %s", e)
    save_state(state)
    log.info("SEO改善 完了")


if __name__ == "__main__":
    main()
