"""GitHub Pages 用サイト生成。Pinが指す先のランディング兼ブログ。
業界標準の構造（ヒーロー＋サムネイル付きカード＋サイドバー＋筆者欄＋フッター法務）で、
初見でも自然に見え、PC/スマホ両対応。記事はリサーチ型・編集部名義（AI生成を偽らない）。
SEO: 全ページにOG/Twitterカード、記事にJSON-LD(Article/FAQPage/BreadcrumbList)、
     ビルド毎に sitemap.xml と robots.txt を自動生成。既存記事には _upgrade_seo で後付け。
"""
from __future__ import annotations
import hashlib
import pathlib
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from .util import load_settings, SITE_DIR, log
from . import images
from . import linker, eeat, indexnow

BRAND = "littletabi"
TAGLINE = "Honest, practical guides for families travelling to Japan with kids."
BYLINE = "By the littletabi editors"
# 連絡フォーム（Formspreeの無料フォームID。未設定なら案内文を表示）
CONTACT_FORM_ACTION = "https://api.web3forms.com/submit"
WEB3FORMS_KEY = "e0c3512d-69a9-46e8-94a3-61bd2e94bd8b"
# GA4 計測タグ（非秘密。空文字なら埋め込まない）。全ページの<head>に出力される。
GA4_MEASUREMENT_ID = "G-GD1XLKR8S3"
# Travelpayouts Drive（アウトバウンド旅行リンクを自動でアフィリ化する公開埋め込み。秘密値ではない）。
# 空文字なら埋め込まない。全ページの<head>に出力される。
TPDRIVE_SRC = "https://tpembars.com/NTQ0MTkx.js?t=544191"

BASE_CSS = """
:root{--ink:#1f2937;--muted:#6b7280;--accent:#b8005a;--accent2:#7a1546;--soft:#fff0f6;--line:#ececf1;--bg:#fffdfb;--card:#ffffff}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;margin:0;color:var(--ink);background:var(--bg);line-height:1.7}
img{max-width:100%;display:block}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
.narrow{max-width:760px}
header.site{border-bottom:1px solid var(--line);background:rgba(255,255,255,.92);backdrop-filter:saturate(160%) blur(6px);position:sticky;top:0;z-index:20}
header.site .bar{display:flex;align-items:center;justify-content:space-between;min-height:66px;gap:16px}
.brand{font-weight:800;font-size:1.35rem;letter-spacing:-.02em;color:var(--ink)}
.brand b{color:var(--accent)}
nav.main{display:flex;flex-wrap:wrap;gap:18px}
nav.main a{color:var(--ink);font-size:.96rem;font-weight:600}
nav.main a:hover{color:var(--accent);text-decoration:none}
.navtoggle{display:none;border:1px solid var(--line);background:#fff;border-radius:10px;padding:8px 10px;font-size:1rem;cursor:pointer}
.layout{display:grid;grid-template-columns:1fr 320px;gap:40px;margin:30px 0 10px}
.single{margin:30px 0}
.hero-feat{display:grid;grid-template-columns:1.15fr 1fr;gap:26px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;margin:28px 0 8px}
.hero-feat .ph{aspect-ratio:16/10;background:#f3eef1}
.hero-feat .ph img{width:100%;height:100%;object-fit:cover}
.hero-feat .tx{padding:8px 28px 18px 0}
.eyebrow{display:inline-block;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:var(--accent);background:var(--soft);padding:4px 10px;border-radius:999px}
.hero-feat h1{font-size:1.9rem;line-height:1.18;margin:.5em 0 .3em}
.hero-feat h1 a{color:var(--ink)}
.hero-feat p{color:var(--muted);margin:.2em 0 .8em}
.meta{font-size:.82rem;color:var(--muted)}
.readmore{display:inline-block;margin-top:.7em;font-weight:700}
.sec-title{font-size:1.15rem;margin:8px 0 4px;border-left:4px solid var(--accent);padding-left:10px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;transition:box-shadow .15s ease,transform .15s ease}
.card:hover{box-shadow:0 10px 28px rgba(0,0,0,.07);transform:translateY(-2px)}
.card .ph{aspect-ratio:3/2;background:#f3eef1}
.card .ph img{width:100%;height:100%;object-fit:cover}
.card .body{padding:15px 17px 18px}
.card h3{font-size:1.1rem;line-height:1.3;margin:.1em 0 .35em}
.card h3 a{color:var(--ink)}
.card h3 a:hover{color:var(--accent);text-decoration:none}
.card p{color:var(--muted);font-size:.92rem;margin:.2em 0 .5em}
aside.side{display:flex;flex-direction:column;gap:22px}
.widget{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 18px}
.widget h4{margin:.1em 0 .6em;font-size:1rem}
.widget.about p{color:var(--muted);font-size:.92rem;margin:.2em 0 0}
.widget ul{list-style:none;margin:.2em 0 0;padding:0}
.widget ul li{padding:7px 0;border-bottom:1px dashed var(--line)}
.widget ul li:last-child{border-bottom:0}
.widget ul li a{color:var(--ink);font-size:.94rem}
.widget ul li a:hover{color:var(--accent);text-decoration:none}
.widget.note{background:var(--soft);border-color:#ffe0ee;color:var(--muted);font-size:.85rem}
article.post h1{font-size:2rem;line-height:1.2;margin:.2em 0 .25em}
article.post .byline{font-size:.86rem;color:var(--muted);margin:0 0 14px}
article.post img.hero-img{width:100%;border-radius:14px;margin:.3em 0 .4em;aspect-ratio:16/9;object-fit:cover}
article.post h2{margin-top:1.7em}
article.post ul{padding-left:1.2em}
article.post table{width:100%;border-collapse:collapse;margin:1.2em 0;font-size:.94rem}
article.post th,article.post td{border:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}
article.post thead th{background:var(--soft);color:var(--ink)}
article.post tbody tr:nth-child(even){background:#fbfafc}
article.post figure.bodyimg{margin:1.7em 0}
article.post figure.bodyimg img{width:100%;border-radius:14px;aspect-ratio:16/9;object-fit:cover}
article.post figure.bodyimg figcaption{font-size:.74rem;color:#9aa0aa;margin-top:.35em}
.disc{font-size:.86rem;color:var(--muted);background:var(--soft);border:1px solid #ffe0ee;border-radius:12px;padding:13px 16px}
.disc.top{margin:0 0 18px}
.disc.bottom{margin:2.2em 0 0}
.credit{font-size:.75rem;color:#9aa0aa;margin:.1em 0 1em}
.transparency{font-size:.82rem;color:var(--muted);border-top:1px solid var(--line);margin-top:2em;padding-top:1em}
.empty{color:var(--muted);padding:18px 0}
.cform{display:flex;flex-direction:column;gap:12px;max-width:520px}
.cform label{font-size:.9rem;font-weight:600}
.cform input,.cform textarea{width:100%;border:1px solid var(--line);border-radius:10px;padding:11px 12px;font:inherit}
.cform button{align-self:flex-start;background:var(--accent);color:#fff;border:0;border-radius:10px;padding:11px 20px;font-weight:700;cursor:pointer}
.cform button:hover{background:var(--accent2)}
footer.site{border-top:1px solid var(--line);margin-top:56px;background:#fff;color:var(--muted);font-size:.9rem}
footer.site .cols{display:grid;grid-template-columns:1.5fr 1fr 1fr;gap:24px;padding:34px 0 10px}
footer.site h5{color:var(--ink);font-size:.92rem;margin:0 0 8px}
footer.site .colbrand b{color:var(--accent)}
footer.site ul{list-style:none;margin:0;padding:0}
footer.site ul li{padding:4px 0}
footer.site a{color:var(--muted)}
footer.site a:hover{color:var(--accent)}
footer.site .legal{border-top:1px solid var(--line);padding:14px 0 26px;font-size:.8rem;color:#9aa0aa}
@media(max-width:880px){
.layout{grid-template-columns:1fr;gap:30px}
.hero-feat{grid-template-columns:1fr}
.hero-feat .tx{padding:0 20px 22px}
.hero-feat .ph{aspect-ratio:16/9}
.grid{grid-template-columns:1fr}
footer.site .cols{grid-template-columns:1fr;gap:18px}
nav.main{display:none;width:100%;flex-direction:column;gap:0}
nav.main.open{display:flex}
nav.main a{padding:11px 2px;border-bottom:1px solid var(--line)}
header.site .bar{flex-wrap:wrap}
.navtoggle{display:inline-block}
}
"""

NAV_LINKS = [("/", "Home"), ("/about", "About"), ("/contact", "Contact")]
NAV_JS = "<script>function tmenu(){var n=document.getElementById('nav');n.classList.toggle('open');}</script>"


# ============================================================
# SEO ヘルパー（OG/Twitter, JSON-LD, sitemap/robots, 既存ページ後付け）
# ============================================================
def _esc_attr(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _social_tags(title: str, desc: str, url: str, image: str = "",
                 type_: str = "website", published: str | None = None) -> str:
    """Open Graph + Twitter Card メタ群を返す（PinterestのRich Pin/SNS共有の見栄えにも効く）。"""
    t, d = _esc_attr(title), _esc_attr(desc)
    tags = [
        '<meta name="robots" content="max-image-preview:large, max-snippet:-1, max-video-preview:-1">',
        f'<meta property="og:type" content="{type_}">',
        f'<meta property="og:site_name" content="{BRAND}">',
        f'<meta property="og:title" content="{t}">',
        f'<meta property="og:description" content="{d}">',
        f'<meta property="og:url" content="{_esc_attr(url)}">',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{_esc_attr(image)}">')
    tags.append('<meta name="twitter:card" content="summary_large_image">')
    tags.append(f'<meta name="twitter:title" content="{t}">')
    tags.append(f'<meta name="twitter:description" content="{d}">')
    if image:
        tags.append(f'<meta name="twitter:image" content="{_esc_attr(image)}">')
    if published:
        tags.append(f'<meta property="article:published_time" content="{published}">')
    return "\n".join(tags) + "\n"


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _faq_jsonld(body_html: str):
    """記事本文の <h2>FAQ</h2> セクションから Q&A を抽出し schema.org FAQPage を組む。"""
    if not body_html:
        return None
    m = re.search(r"<h2[^>]*>\s*FAQ.*?</h2>(.*)$", body_html, re.S | re.I)
    if not m:
        return None
    section = m.group(1)
    nx = re.search(r"<h2", section)
    if nx:
        section = section[:nx.start()]
    pairs = re.findall(r"<h3[^>]*>(.*?)</h3>(.*?)(?=<h3|$)", section, re.S | re.I)
    items = []
    for q, a in pairs:
        qt, at = _strip_tags(q), _strip_tags(a)
        if qt and at:
            items.append({"@type": "Question", "name": qt,
                          "acceptedAnswer": {"@type": "Answer", "text": at}})
    if len(items) < 2:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items}


def _jsonld_block(*objs) -> str:
    out = []
    for o in objs:
        if not o:
            continue
        s = json.dumps(o, ensure_ascii=False).replace("<", "\\u003c")
        out.append(f'<script type="application/ld+json">{s}</script>')
    return ("\n".join(out) + "\n") if out else ""


# ============================================================
# 静的ページの公開日を安定させる（毎runのノイズ差分を止める）
# ============================================================
# 2026-08-22 実測: ハブ6本と how-we-make-guides が毎runで datePublished/dateModified を
# 現在時刻（秒単位）で書き直していた。_static_page がページを作り直してJSON-LDを消し、
# 直後のバックフィルが now() で入れ直す、というループになっていたため。
# 中身が変わっていないのに毎回「今公開しました」とGoogleに伝えることになり、
# 無意味なコミットも毎run生まれる。初出日を保存し、更新日は本文が変わったときだけ動かす。
_PAGE_DATES_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "page_dates.json"


def _stable_dates(key: str, body_html: str) -> tuple:
    """(datePublished, dateModified) を返す。本文が変わらない限り同じ値を返す。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha256((body_html or "").encode("utf-8")).hexdigest()[:16]
    try:
        store = json.loads(_PAGE_DATES_PATH.read_text(encoding="utf-8"))
    except Exception:
        store = {}
    rec = store.get(key)
    if isinstance(rec, dict) and rec.get("published"):
        published = rec["published"]
        modified = rec.get("modified") or published
        if rec.get("hash") != digest:          # 本文が変わったときだけ更新日を進める
            modified = now
    else:
        published = modified = now
    store[key] = {"published": published, "modified": modified, "hash": digest}
    try:
        _PAGE_DATES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PAGE_DATES_PATH.write_text(json.dumps(store, ensure_ascii=False, sort_keys=True,
                                               indent=0), encoding="utf-8")
    except Exception as e:
        log.error("page_dates保存失敗: %s", e)
    return published, modified


def _article_jsonld(title, desc, url, image, date_iso, category, body_html, base,
                    modified_iso: str | None = None) -> str:
    article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": (title or "")[:110], "description": desc or "",
        "image": [image] if image else [],
        "datePublished": date_iso, "dateModified": modified_iso or date_iso,
        "author": {"@type": "Organization", "name": "littletabi editors"},
        "publisher": {"@type": "Organization", "name": "littletabi"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "inLanguage": "en",
    }
    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": category or "Japan with kids", "item": base + "/"},
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ],
    }
    return _jsonld_block(article, breadcrumb, _faq_jsonld(body_html))


def _write_seo_files(cfg) -> None:
    """docs/ 配下の全 *.html を走査して sitemap.xml と robots.txt を生成する。"""
    base = cfg["site"]["base_url"].rstrip("/")
    today = datetime.now(timezone.utc).date().isoformat()
    rows = []
    for path in sorted(SITE_DIR.glob("*.html")):
        name = path.name
        if name.endswith(".html") and name[:-5] in linker.REDIRECTED_SLUGS:
            continue  # Phase 2-2: 301統合先へ寄せる旧slugはサイトマップから除外
        if name == "404.html":
            continue  # noindex のページをsitemapに載せない（2026-09-06に混入を発見）
        # 2026-09-06: Cloudflare Pages が /x.html を /x へ308するので、loc も拡張子なしにする。
        # （以前は sitemap 全URLが「リダイレクトされるURL」だった）
        loc = linker.page_url(base, name)
        if name == "index.html":
            pr = "1.0"
        elif name in ("about.html", "disclosure.html", "privacy.html", "contact.html"):
            pr = "0.4"
        else:
            pr = "0.8"
        rows.append(
            f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>{pr}</priority></url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows) + "\n</urlset>\n"
    )
    (SITE_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"
    (SITE_DIR / "robots.txt").write_text(robots, encoding="utf-8")
    # AIクローラ向けのサイト要約（AEO: 何を・どんな品質で出しているかを機械可読で提示）
    llms_txt = (
        "# littletabi — AI-assisted, regularly updated family-travel guides for Japan\n\n"
        "> Honest, practical guides for families visiting Japan with kids.\n"
        "> Written with AI and edited for clarity. Each guide shows a last-updated date.\n"
        "> Prices and opening hours change — we ask readers to confirm on official sites.\n\n"
        "## Principles\n"
        "- We do not fake first-hand experience. We are upfront that guides are AI-assisted.\n"
        "- Topics: transport, food & allergies, baby gear, itineraries, hotels, eSIM.\n\n"
        "## Key resources\n"
        f"- Guides index: {base}/sitemap.xml\n"
        f"- How we make guides: {base}/how-we-make-guides\n"
        f"- Affiliate disclosure: {base}/disclosure\n"
    )
    (SITE_DIR / "llms.txt").write_text(llms_txt, encoding="utf-8")
    # IndexNow 所有確認キーを毎回出力（Bing等への即時通知に使用）
    try:
        indexnow.write_key_file(str(SITE_DIR))
    except Exception as e:
        log.error("IndexNowキー出力に失敗(続行): %s", e)
    log.info("sitemap.xml/robots.txt/llms.txt 生成 (%d URL)", len(rows))


def _upgrade_seo(cfg) -> None:
    """既存の記事HTMLに、本文を作り直さずに Twitter Card と JSON-LD(Article/FAQ/Breadcrumb)を
    後付けする（<head>へ注入）。JSON-LDが既にあるページはスキップ＝冪等。"""
    base = cfg["site"]["base_url"].rstrip("/")
    skip = {"index.html", "about.html", "disclosure.html", "privacy.html", "contact.html"}
    for path in SITE_DIR.glob("*.html"):
        if path.name in skip:
            continue
        try:
            txt = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "application/ld+json" in txt:
            continue
        tm = re.search(r"<title>(.*?)</title>", txt, re.S)
        title = (tm.group(1).split("|")[0].strip() if tm else path.stem)
        dm = re.search(r'<meta name="description" content="([^"]*)"', txt)
        desc = dm.group(1) if dm else TAGLINE
        cm = re.search(r'<link rel="canonical" href="([^"]*)"', txt)
        url = cm.group(1) if cm else linker.page_url(base, path.name)
        im = re.search(r'<meta property="og:image" content="([^"]*)"', txt)
        image = im.group(1) if im else ""
        am = re.search(r'<article class="post">(.*?)</article>', txt, re.S)
        body_html = am.group(1) if am else txt
        add = ""
        if "twitter:card" not in txt:
            add += _social_tags(title, desc, url, image, "article")
        _pub, _mod = _stable_dates(path.name, body_html)
        add += _article_jsonld(title, desc, url, image, _pub,
                               "Japan with kids", body_html, base, modified_iso=_mod)
        if add and "</head>" in txt:
            txt = txt.replace("</head>", add + "</head>", 1)
            path.write_text(txt, encoding="utf-8")
            log.info("SEO後付け: %s", path.name)


# 既存記事HTMLに残る“東京で執筆・編集/日本の編集者がレビュー”等の不正確な表現を正直化する置換表。
# フッターやAbout文は記事を作り直さない限り更新されないため、バックフィルで文字列置換する（冪等・LLM不要）。
_HONESTY_FIXES = [
    ("written and edited from Tokyo",
     "written with AI and an automated quality process"),
    ("written and edited by our team in Japan",
     "written with AI and an automated quality process"),
    ("reviewed by our editors in Japan for usefulness and accuracy",
     "checked with an automated quality process for usefulness and accuracy"),
    ("reviewed by our editors in Japan",
     "checked with an automated quality process"),
]


def _upgrade_eeat_links(cfg) -> None:
    """既存記事HTMLに“本文を作り直さずに”次を冪等で後付けする（LLM不要・レート制限回避）:
    ①関連ガイドの内部リンク ②rel=sponsored ③正直な透明性ノート ④Organization JSON-LD。
    これで過去記事もコンテンツ再生成なしに改善が反映される。"""
    base = cfg["site"]["base_url"].rstrip("/")
    skip = {"index.html", "about.html", "disclosure.html", "privacy.html",
            "contact.html", "how-we-make-guides.html"}
    # 2026-09-05: assets/pages/ 由来の手組みページ（計算機・コンパニオン記事・ホテル比較）は
    # 文面もリンクも別管理なので、バックフィルで書き換えない（計算機のUIが消えた事故の再発防止）
    try:
        skip |= {p.name for p in (SITE_DIR.parent / "assets" / "pages").glob("*.html")}
    except Exception:
        pass
    clusters = linker.load_clusters()
    titles = linker.load_titles()
    note = eeat.trust_note()
    for path in SITE_DIR.glob("*.html"):
        if path.name in skip:
            continue
        try:
            txt = path.read_text(encoding="utf-8")
        except Exception:
            continue
        slug = path.stem
        changed = False
        # Phase 2-2 / 2026-08-22改: 301統合した旧slugへの内部リンクは「削除」ではなく
        # 「統合先へ張り替え」る。以前は <li> ごと消していたため、統合で集約されるはずの
        # 内部リンク資産をそのまま捨てていた（統合先の被リンクが0本になっていた）。
        for _old, _new in linker.REDIRECT_MAP.items():
            if _new == slug:                       # 自分自身へのリンクは作らない
                _pat = re.compile(r'<li>\s*<a[^>]*href="/' + re.escape(_old) + r'(?:\.html)?"[^>]*>.*?</a>\s*</li>', re.S)
                if _pat.search(txt):
                    txt = _pat.sub("", txt); changed = True
                continue
            _href = re.compile(r'(href=")/' + re.escape(_old) + r'(?:\.html)?(")')
            if _href.search(txt):
                txt = _href.sub(r"\1/" + _new + r"\2", txt)
                changed = True
        # 張り替えで同じ統合先への<li>が重複しうるので、2本目以降を落とす
        for _new in set(linker.REDIRECT_MAP.values()):
            _pat = re.compile(r'<li>\s*<a[^>]*href="/' + re.escape(_new) + r'(?:\.html)?"[^>]*>.*?</a>\s*</li>', re.S)
            _hits = list(_pat.finditer(txt))
            if len(_hits) > 1:
                for m in reversed(_hits[1:]):
                    txt = txt[:m.start()] + txt[m.end():]
                changed = True

        # ① 内部リンク（関連ガイド）を bottom 開示の直前に挿入
        # 2026-08-22: 以前は「関連ブロックが無いときだけ挿入」だったため、clusters.yaml を
        # 直しても既存ページは古いリンクを持ち続け、新設定が新規ページにしか効かなかった
        # （トラストストリップと同型の skip-if-present 問題）。中身が変わったら差し替える。
        links = linker.related(slug, clusters)
        if links:
            items = "".join(
                f"<li><a href=\"/{s}.html\">{titles.get(s, s.replace('-', ' '))}</a></li>"
                for s in links)
            block = ("<section class=\"related\"><h2>Related guides</h2>"
                     f"<ul>{items}</ul></section>")
            _rel = re.compile(r'<section class="related">.*?</section>', re.S)
            if _rel.search(txt):
                if _rel.search(txt).group(0) != block:      # 同一なら書かない（無駄な差分を出さない）
                    txt = _rel.sub(lambda _m: block, txt, count=1)
                    changed = True
            else:
                if '<div class="disc bottom"' in txt:
                    txt = txt.replace('<div class="disc bottom"', block + '<div class="disc bottom"', 1)
                else:
                    txt = txt.replace("</article>", block + "</article>", 1)
                changed = True

        # ② 透明性ノートの正直化（旧 <p class="transparency"> を置換 / 無ければ追加）
        if 'class="verify"' not in txt:
            if 'class="transparency"' in txt:
                txt = re.sub(r'<p class="transparency">.*?</p>', note, txt, count=1, flags=re.S)
            else:
                txt = txt.replace("</article>", note + "</article>", 1)
            changed = True

        # ③ Organization JSON-LD（未挿入時のみ）
        if '"Organization"' not in txt and "</head>" in txt:
            txt = txt.replace("</head>", eeat.org_jsonld(base) + "</head>", 1)
            changed = True

        # ④ アフィリリンクに rel=sponsored（冪等）
        new_txt = eeat.add_rel_to_affiliates(txt)
        if new_txt != txt:
            txt = new_txt
            changed = True

        # ⑤ 旧フッター/About文の不正確表現を正直化（記事を作り直さずに反映・冪等）
        for bad, good in _HONESTY_FIXES:
            if bad in txt:
                txt = txt.replace(bad, good)
                changed = True

        if changed:
            path.write_text(txt, encoding="utf-8")
            log.info("E-E-A-T/内部リンク後付け: %s", path.name)


def _header() -> str:
    links = "".join(f'<a href="{u}">{t}</a>' for u, t in NAV_LINKS)
    return (
        '<header class="site"><div class="wrap bar">'
        '<a class="brand" href="/">little<b>tabi</b></a>'
        '<button class="navtoggle" onclick="tmenu()" aria-label="Menu">☰</button>'
        f'<nav class="main" id="nav">{links}</nav>'
        '</div></header>'
    )


def _footer() -> str:
    year = datetime.now(timezone.utc).year
    return (
        '<footer class="site"><div class="wrap">'
        '<div class="cols">'
        '<div class="colbrand"><h5>little<b>tabi</b></h5>'
        '<p>Independent, research-based guides for families visiting Japan, written with AI and an automated '
        'quality process. We are not affiliated with any tourism board or the companies we mention.</p></div>'
        '<div><h5>Explore</h5><ul>'
        '<li><a href="/">Home</a></li>'
        '<li><a href="/about">About</a></li>'
        '<li><a href="/how-we-make-guides">How we make our guides</a></li>'
        '<li><a href="/contact">Contact</a></li></ul></div>'
        '<div><h5>Legal</h5><ul>'
        '<li><a href="/disclosure">Affiliate Disclosure</a></li>'
        '<li><a href="/privacy">Privacy Policy</a></li></ul></div>'
        '</div>'
        f'<div class="legal">Some links are affiliate links; if you book or buy through them we may '
        f'earn a small commission at no extra cost to you. As an Amazon Associate we earn from qualifying '
        f'purchases. &copy; {year} littletabi. All rights reserved.</div>'
        '</div></footer>'
    )


def _ga_snippet() -> str:
    if not GA4_MEASUREMENT_ID:
        return ""
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_MEASUREMENT_ID}"></script>\n'
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        f"gtag('js',new Date());gtag('config','{GA4_MEASUREMENT_ID}');</script>\n"
    )


def _tpdrive_snippet() -> str:
    """Travelpayouts Drive の埋め込み（非同期で外部スクリプトを読み込む）。空なら出力しない。"""
    if not TPDRIVE_SRC:
        return ""
    return (
        '<script>(function(){var s=document.createElement("script");s.async=1;'
        f's.src="{TPDRIVE_SRC}";document.head.appendChild(s);}})();</script>\n'
    )


def _document(lang: str, title_tag: str, head_extra: str, body_inner: str) -> str:
    return (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{_ga_snippet()}"
        f"{_tpdrive_snippet()}"
        f"<title>{title_tag}</title>\n"
        f"{head_extra}"
        f"<style>{BASE_CSS}{eeat.EEAT_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{_header()}\n"
        f"{body_inner}\n"
        f"{_footer()}\n"
        f"{NAV_JS}\n"
        "</body>\n</html>\n"
    )


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "post"


# 本文画像は「ブランド名」で誤ヒット（例: "Universal Studios Japan"→北京の写真）しないよう、
# 記事固有の image_query は使わず、必ず日本の汎用シーンに限定する。slugで分散して記事ごとに変える。
_SAFE_BODY_QUERIES = [
    "Japan family travel", "Tokyo street scene", "Japan with children",
    "Japanese train station", "Japan city park", "Osaka street Japan",
    "Kyoto street", "Japanese family walking", "Japan neighborhood", "Japanese street food",
]


def _safe_body_query(slug: str) -> str:
    # Phase 2-3: slug が都市を含むなら本文画像クエリに必ずその都市を入れる。
    # 都市が入らないと images._rank_photos の場所整合(alt照合)が効かないため。
    cities = images._cities_in(slug or "")
    if cities:
        city = sorted(cities)[0].title()
        templates = [
            "{c} Japan family with children",
            "{c} street scene Japan family",
            "{c} Japan park families",
            "{c} family travel Japan",
        ]
        t = templates[sum(ord(ch) for ch in (slug or "x")) % len(templates)]
        return t.format(c=city)
    return _SAFE_BODY_QUERIES[sum(ord(c) for c in (slug or "x")) % len(_SAFE_BODY_QUERIES)]


def _inject_body_images(body_html: str, imgs: list) -> str:
    """本文の段落区切りに、横長の実写をfigureで分散挿入（中盤に均等配置）。"""
    if not imgs or not body_html:
        return body_html
    positions = [m.end() for m in re.finditer(r"</p>", body_html)]
    if len(positions) < 2:
        return body_html  # 段落が少なすぎると不自然なので挿入しない
    slots = []
    for k in range(1, len(imgs) + 1):
        idx = len(positions) * k // (len(imgs) + 1)
        idx = max(1, min(idx, len(positions) - 1))
        slots.append(positions[idx])
    result = body_html
    for pos, im in sorted(zip(slots, imgs), key=lambda x: x[0], reverse=True):
        cap = ""
        if im.get("photographer"):
            cap = (
                '<figcaption>Photo by '
                f'<a href="{im.get("url", "#")}" rel="nofollow noopener">{im["photographer"]}</a> on Pexels</figcaption>'
            )
        alt = (im.get("alt") or "").replace('"', "")
        fig = f'<figure class="bodyimg"><img src="/{im["rel"]}" alt="{alt}" loading="lazy">{cap}</figure>'
        result = result[:pos] + fig + result[pos:]
    return result


def _excerpt(p: dict) -> str:
    raw = p.get("meta_description") or p.get("last_pin_desc") or ""
    desc = re.sub(r"#\w+", "", raw).strip()
    if len(desc) > 150:
        desc = desc[:150].rstrip() + "…"
    return desc


def _thumb(p: dict) -> str:
    variants = p.get("image_variants") or []
    rel = variants[0] if variants else f"img/{p.get('slug','')}.jpg"
    return "/" + rel.lstrip("/")


def _sidebar(popular: list) -> str:
    pop_html = ""
    if popular:
        items = "".join(f'<li><a href="/{s}">{t}</a></li>' for s, t in popular)
        pop_html = f'<div class="widget"><h4>Popular guides</h4><ul>{items}</ul></div>'
    return (
        '<aside class="side">'
        '<div class="widget about"><h4>About littletabi</h4>'
        '<p>We write honest, practical guides for parents exploring Japan with kids — '
        'transport, food, what to pack and where to go. '
        '<a href="/about">More about us →</a></p></div>'
        f"{pop_html}"
        '<div class="widget"><h4>Start here</h4><ul>'
        '<li><a href="/">All guides</a></li>'
        '<li><a href="/about">How we create our guides</a></li>'
        '<li><a href="/disclosure">Affiliate disclosure</a></li>'
        '</ul></div>'
        '<div class="widget note">Some links are affiliate links. If you book or buy through them, '
        'we may earn a small commission at no extra cost to you.</div>'
        '</aside>'
    )


def _article_page(*, lang, title_tag, head_extra, title, category, date_str,
                  hero_html, credit_html, body_html, disclosure_html, popular):
    meta_line = BYLINE + (f" · {date_str}" if date_str else "")
    cat_html = f'<span class="eyebrow">{category}</span>' if category else ""
    top_disc = ('<div class="disc top">This guide may contain affiliate links. If you book or buy '
                'through them, we may earn a small commission at no extra cost to you.</div>')
    # 透明性ノートは実態どおり“AI生成・最終更新日・公式で要確認”に正直化（架空の人間レビューは謳わない）
    transparency = eeat.trust_note()
    body_inner = (
        '<div class="wrap layout">'
        '<main><article class="post">'
        f"{cat_html}"
        f"<h1>{title}</h1>"
        f'<p class="byline">{meta_line}</p>'
        f"{hero_html}"
        f"{credit_html}"
        f"{top_disc}"
        f"{body_html}"
        f'<div class="disc bottom">{disclosure_html}</div>'
        f"{transparency}"
        "</article></main>"
        f"{_sidebar(popular)}"
        "</div>"
    )
    return _document(lang, title_tag, head_extra, body_inner)


def render_article(content: dict, image_rel: str, credit: dict, slug: str) -> str:
    cfg = load_settings()
    base = cfg["site"]["base_url"].rstrip("/")
    lang = cfg["niche"]["language"]
    site_name = cfg["site"]["site_name"]
    title = content["article_title"]
    meta = content.get("meta_description", "")
    canonical = linker.page_url(base, slug)
    og_img = f"{base}/{image_rel}"
    date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    category = content.get("board_hint") or "Japan with kids"
    credit_html = ""
    if credit.get("photographer"):
        credit_html = (
            '<p class="credit">Photo by '
            f'<a href="{credit.get("url", "#")}" rel="nofollow noopener">{credit["photographer"]}</a> on Pexels</p>'
        )
    head_extra = (
        f'<meta name="description" content="{_esc_attr(meta)}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        '<meta name="author" content="littletabi editors">\n'
        + _social_tags(title, meta, canonical, og_img, "article", published=date_iso)
    )
    hero_html = f'<img class="hero-img" src="/{image_rel}" alt="{_esc_attr(title)}">'

    # 本文に横長の実写を2枚差し込む。記事固有のimage_query(ブランド名で誤ヒットしうる)ではなく、
    # 必ず日本の汎用シーンクエリを使う。失敗時は無画像で続行。
    body_html = content.get("article_html", "")
    try:
        body_imgs = images.fetch_body_images(_safe_body_query(slug), slug, n=2, skip=0)
        body_html = _inject_body_images(body_html, body_imgs)
    except Exception as e:
        log.error("本文画像の挿入に失敗(無画像で続行): %s", e)

    # 内部リンク（トピッククラスタ）を本文末に付与＝孤立ページ解消・回遊/権威分配
    try:
        body_html = linker.inject_links(body_html, slug, linker.load_clusters(), linker.load_titles())
    except Exception as e:
        log.error("内部リンク挿入に失敗(続行): %s", e)

    # JSON-LD（Article + FAQPage + BreadcrumbList）は本文確定後に組む
    head_extra += _article_jsonld(title, meta, canonical, og_img, date_iso,
                                  category, content.get("article_html", ""), base)
    head_extra += eeat.org_jsonld(base)   # Organization(任意でPublisher) を全記事に

    html = _article_page(
        lang=lang, title_tag=f"{title} | {site_name}", head_extra=head_extra,
        title=title, category=category, date_str=date_str, hero_html=hero_html,
        credit_html=credit_html, body_html=body_html,
        disclosure_html=content.get("disclosure", ""), popular=[],
    )
    html = eeat.add_rel_to_affiliates(html)   # 収益リンクに rel="sponsored" を自動付与
    out = SITE_DIR / f"{slug}.html"
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info("記事ページ生成: %s.html", slug)
    return canonical


def _static_page(slug: str, lang: str, title_tag: str, inner: str, desc: str | None = None) -> None:
    """静的ページを書き出す。

    2026-08-22: desc を受け取れるようにした。従来は全ページ TAGLINE 固定だったため、
    **カテゴリハブ6本を含む12ページが同一の meta description を共有**していた。
    ハブはカテゴリ系クエリで拾うべきページなのに説明文が全部同じ、という状態だった。
    """
    cfg = load_settings()
    base = cfg["site"]["base_url"].rstrip("/")
    url = linker.page_url(base, slug)
    title = title_tag.split("|")[0].strip()
    desc = (desc or TAGLINE).strip()[:155]
    head_extra = (
        f'<meta name="description" content="{_esc_attr(desc)}">\n'
        f'<link rel="canonical" href="{url}">\n'
        + _social_tags(title, desc, url, "", "website")
    )
    body_inner = f'<div class="wrap single narrow"><article class="post">{inner}</article></div>'
    (SITE_DIR / f"{slug}.html").write_text(_document(lang, title_tag, head_extra, body_inner), encoding="utf-8")


def _about_inner() -> str:
    return (
        "<h1>About littletabi</h1>"
        "<p><strong>littletabi</strong> is an independent guide for parents planning a trip to Japan "
        "with their children &mdash; from toddlers to teens. We focus on the practical, parent-specific "
        "questions the big travel sites skip: stroller access, kid-friendly food, getting around with "
        "little ones, what to pack, and staying safe and sane on the road.</p>"
        "<h2>How we create our guides</h2>"
        "<p>We are upfront about how littletabi works: our guides are written with AI and an automated "
        "quality process, drawing on publicly available information about Japan. We do <strong>not</strong> "
        "claim to have personally visited every place, and we never invent first-hand stories. Instead we "
        "focus on being specific, useful and honest, and on keeping information current &mdash; each guide "
        "shows a last-updated date. Because details like prices, opening hours and rules change often, "
        "please always confirm the latest information on official websites before you travel. "
        "<a href=\"/how-we-make-guides.html\">Read more about how we make these guides</a>.</p>"
        "<h2>Independence &amp; funding</h2>"
        "<p>littletabi is not affiliated with any government tourism organisation or the businesses we "
        'mention. Some of our links are affiliate links, which help keep the site free &mdash; see our '
        '<a href="/disclosure">Affiliate Disclosure</a>. Questions or corrections? '
        '<a href="/contact">Get in touch</a>.</p>'
    )


def _disclosure_inner() -> str:
    return (
        "<h1>Affiliate Disclosure</h1>"
        "<h2>Affiliate links</h2>"
        "<p>Some links on littletabi are affiliate links. If you click one and make a booking or "
        "purchase, we may earn a small commission at no additional cost to you. We only recommend "
        "products and services we believe are genuinely useful for families travelling to Japan. "
        "These commissions help keep the site free to read.</p>"
        "<h2>Amazon Associates</h2>"
        "<p>As an Amazon Associate we earn from qualifying purchases.</p>"
        "<h2>Editorial independence</h2>"
        "<p>Affiliate relationships never determine our recommendations. We are not paid to feature any "
        "specific product, and our guides are written independently.</p>"
        "<h2>Photos</h2>"
        "<p>Photography is sourced from Pexels under the Pexels License. Individual photographers are "
        "credited on each article where applicable.</p>"
    )


def _privacy_inner() -> str:
    today = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    return (
        "<h1>Privacy Policy</h1>"
        f"<p class='byline'>Last updated: {today}</p>"
        "<p>This Privacy Policy explains how littletabi (we, us) handles "
        "information when you visit our website.</p>"
        "<h2>Information we collect</h2>"
        "<p>littletabi is a static website. We use Google Analytics (GA4) to understand aggregate, "
        "anonymised traffic such as page views and referral sources. We do not ask for, collect or "
        "store personal information through the site, and we do not require you to create an account. "
        "Google Analytics may set cookies and process usage data as described in Google's policies. "
        "Our hosting and content-delivery providers may automatically log standard technical data (such "
        "as IP address and browser type) for security and operations, as is typical for any website.</p>"
        "<h2>Contact form</h2>"
        "<p>If you contact us through our form, the details you submit (such as your name, email and "
        "message) are processed by our third-party form provider solely to deliver your message to us. "
        "We use them only to respond to you.</p>"
        "<h2>Affiliate links &amp; third parties</h2>"
        "<p>We use affiliate links (see our <a href='/disclosure'>Affiliate Disclosure</a>). When "
        "you click an external or affiliate link, the destination site's own privacy policy applies. "
        "We are not responsible for the content or practices of third-party sites.</p>"
        "<h2>Children's privacy</h2>"
        "<p>Our content is written for parents. We do not knowingly collect any personal information "
        "from children.</p>"
        "<h2>Your choices</h2>"
        "<p>Because we don't collect personal data through the site itself, there is nothing for us "
        "to access, change or delete. For anything you sent via the contact form, contact us to request "
        "deletion.</p>"
        "<h2>Changes</h2>"
        "<p>We may update this policy from time to time; the date above reflects the latest version.</p>"
        "<p>Questions? <a href='/contact'>Contact us</a>.</p>"
    )


def _contact_inner() -> str:
    if CONTACT_FORM_ACTION:
        form = (
            f'<form class="cform" action="{CONTACT_FORM_ACTION}" method="POST">'
            f'<input type="hidden" name="access_key" value="{WEB3FORMS_KEY}">'
            '<label>Your name<input type="text" name="name" required></label>'
            '<label>Your email<input type="email" name="email" required></label>'
            '<label>Message<textarea name="message" rows="6" required></textarea></label>'
            '<button type="submit">Send message</button>'
            '</form>'
        )
    else:
        form = ('<p class="disc">Our contact form is being set up. In the meantime, you can reach us '
                'through our social profiles.</p>')
    return (
        "<h1>Contact us</h1>"
        "<p>Questions, corrections or partnership enquiries? We would love to hear from you. "
        "We aim to reply within a few days.</p>"
        f"{form}"
    )


def _write_cname(cfg: dict) -> None:
    host = urlparse(cfg["site"]["base_url"]).netloc
    if host and not host.endswith("github.io"):
        (SITE_DIR / "CNAME").write_text(host + "\n", encoding="utf-8")


def _migrate_legacy(cfg: dict, popular: list) -> None:
    """旧テンプレ記事を新・記事レイアウト（筆者欄/サイドバー/開示）に包み直し、
    canonical/og の旧プレースホルダURLも現行 base_url に修正する。自己修復。"""
    base = cfg["site"]["base_url"].rstrip("/")
    lang_default = cfg["niche"].get("language", "en")
    skip = {"index.html", "about.html", "disclosure.html", "privacy.html",
            "contact.html", "how-we-make-guides.html"}
    for path in SITE_DIR.glob("*.html"):
        # 静的ページ（about等）とカテゴリハブ(japan-with-kids-*)は記事ではないので移行対象外。
        # これを除外しないと、bylineの無い静的ページを“旧記事”と誤認して本文を空に潰してしまう。
        if path.name in skip or path.name.startswith("japan-with-kids-"):
            continue
        try:
            txt = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'article class="post"' in txt and 'class="byline"' in txt:
            continue
        tm = re.search(r"<title>(.*?)</title>", txt, re.S)
        title_tag = tm.group(1).strip() if tm else cfg["site"]["site_name"]
        lm = re.search(r'<html lang="([^"]+)"', txt)
        lang = lm.group(1) if lm else lang_default
        h1m = re.search(r"<h1[^>]*>(.*?)</h1>", txt, re.S)
        title = h1m.group(1).strip() if h1m else title_tag.split("|")[0].strip()
        him = re.search(r'<img[^>]*class="hero(?:-img)?"[^>]*>', txt)
        hero_html = him.group(0).replace('class="hero"', 'class="hero-img"') if him else ""
        hero_html = hero_html.replace('src="img/', 'src="/img/')
        crm = re.search(r'<p class="credit">.*?</p>', txt, re.S)
        credit_html = crm.group(0) if crm else ""
        dm = re.search(r'<p class="disc">(.*?)</p>', txt, re.S)
        disclosure_html = dm.group(1).strip() if dm else (
            "Some links may be affiliate links; we may earn a small commission at no extra cost to you. "
            "As an Amazon Associate we earn from qualifying purchases.")
        body = txt
        cut_start = None
        for pat in (r'<img[^>]*class="hero[^"]*"[^>]*>', r'<p class="credit">.*?</p>'):
            mm = re.search(pat, body, re.S)
            if mm:
                cut_start = mm.end() if cut_start is None else max(cut_start, mm.end())
        cut_end = None
        de = re.search(r'<p class="disc">', body)
        if de:
            cut_end = de.start()
        if cut_start is not None and cut_end is not None and cut_end > cut_start:
            body_html = body[cut_start:cut_end].strip()
        else:
            bm = re.search(r"</h1>(.*?)<p class=\"disc\">", txt, re.S)
            body_html = bm.group(1).strip() if bm else ""
        body_html = body_html.replace("https://YOUR_GITHUB_USERNAME.github.io/japan-autopilot", base)
        head_tags = re.findall(r"<(?:meta|link)[^>]*>", txt)
        keep = [h for h in head_tags if ("og:" in h or 'name="description"' in h or 'rel="canonical"' in h)]
        head_extra = "".join(
            h.replace("https://YOUR_GITHUB_USERNAME.github.io/japan-autopilot", base) + "\n" for h in keep
        )
        html = _article_page(
            lang=lang, title_tag=title_tag, head_extra=head_extra, title=title,
            category="Japan with kids", date_str="", hero_html=hero_html,
            credit_html=credit_html, body_html=body_html, disclosure_html=disclosure_html,
            popular=popular,
        )
        path.write_text(html, encoding="utf-8")
        log.info("legacy記事を新レイアウトに移行: %s", path.name)


# カテゴリ（クラスタ）ハブ。トピッククラスタごとに一覧ランディングを作り、回遊と主題権威を強化。
CLUSTER_META = {
    "transport": ("Getting Around Japan with Kids",
                  "Trains, the Japan Rail Pass, strollers, car seats and day trips — how to move around Japan with little ones."),
    "food": ("Eating in Japan with Kids",
             "Kid-friendly meals, food allergies, sushi, ramen, themed cafes and konbini snacks for picky eaters."),
    "baby": ("Babies & Toddlers in Japan",
             "Diapers, formula, baby carriers, what to pack and beating jet lag with the littlest travellers."),
    "accommodation": ("Where to Stay in Japan with Kids",
                      "Family hotels with connecting rooms, ryokan and family-friendly onsen that work for kids."),
    "attractions": ("Things to Do in Japan with Kids",
                    "Disney, Universal, Nara's deer, gacha and seasonal tips for family-friendly fun."),
    "practical": ("Japan Trip Planning for Families",
                  "Money and budgeting, essential Japanese phrases and itineraries for your family trip."),
}


def _hub_slug(name: str) -> str:
    return f"japan-with-kids-{name}"


def _build_hubs(clusters: dict, slug_to_post: dict, lang: str, site_name: str) -> list:
    """各クラスタのハブ（カテゴリ一覧）ページを生成して [(hub_slug, hub_title)] を返す。"""
    hubs = []
    for name, c in (clusters or {}).items():
        title_h, intro = CLUSTER_META.get(name, (name.replace("-", " ").title(), TAGLINE))
        order = [c.get("pillar")] + [s for s in c.get("members", []) or [] if s != c.get("pillar")]
        members = [slug_to_post[s] for s in order if s in slug_to_post]
        if not members:
            continue
        cards = "".join(
            '<article class="card">'
            f'<a class="ph" href="/{p["slug"]}"><img src="{_thumb(p)}" alt="{p["article_title"]}"></a>'
            '<div class="body">'
            f'<h3><a href="/{p["slug"]}">{p["article_title"]}</a></h3>'
            f'<p>{_excerpt(p)}</p></div></article>'
            for p in members
        )
        inner = (f"<h1>{title_h}</h1><p>{intro}</p>"
                 f'<div class="grid">{cards}</div>')
        _static_page(_hub_slug(name), lang, f"{title_h} | {site_name}", inner, desc=intro)
        hubs.append((_hub_slug(name), title_h))
    return hubs


def _topics_block(hubs: list) -> str:
    """ホームページ用の『トピックで探す』導線（ハブへのリンク群）。"""
    if not hubs:
        return ""
    items = "".join(f'<li><a href="/{s}">{t}</a></li>' for s, t in hubs)
    return ('<div class="wrap"><h2 class="sec-title">Browse by topic</h2>'
            f'<div class="widget"><ul class="topics">{items}</ul></div></div>')


def rebuild_index(state: dict) -> None:
    cfg = load_settings()
    base = cfg["site"]["base_url"].rstrip("/")
    site_name = cfg["site"]["site_name"]
    lang = cfg["niche"].get("language", "en")
    posts = [p for p in reversed(state.get("posted", [])[-200:])
             if p.get("slug") and p.get("article_title")
             and p["slug"] not in linker.REDIRECTED_SLUGS]
    popular = [(p["slug"], p["article_title"]) for p in posts[:6]]
    slug_to_post = {p["slug"]: p for p in posts}
    hubs = _build_hubs(linker.load_clusters(), slug_to_post, lang, site_name)

    if posts:
        f = posts[0]
        feat = (
            '<section class="hero-feat">'
            f'<div class="ph"><a href="/{f["slug"]}"><img src="{_thumb(f)}" alt="{f["article_title"]}"></a></div>'
            '<div class="tx"><span class="eyebrow">Featured guide</span>'
            f'<h1><a href="/{f["slug"]}">{f["article_title"]}</a></h1>'
            f'<p>{_excerpt(f)}</p>'
            f'<p class="meta">{BYLINE}</p>'
            f'<a class="readmore" href="/{f["slug"]}">Read the guide →</a></div>'
            '</section>'
        )
        cards = []
        for p in posts[1:]:
            cards.append(
                '<article class="card">'
                f'<a class="ph" href="/{p["slug"]}"><img src="{_thumb(p)}" alt="{p["article_title"]}"></a>'
                '<div class="body">'
                f'<h3><a href="/{p["slug"]}">{p["article_title"]}</a></h3>'
                f'<p>{_excerpt(p)}</p>'
                f'<p class="meta">{BYLINE}</p>'
                '</div></article>'
            )
        grid = (f'<h2 class="sec-title">Latest guides</h2><div class="grid">{"".join(cards)}</div>'
                if cards else "")
        og_img = f"{base}{_thumb(f)}"
    else:
        feat = ""
        grid = '<p class="empty">New guides are published regularly &mdash; check back soon.</p>'
        og_img = ""

    body_inner = (
        f'<div class="wrap">{feat}</div>'
        f'{_topics_block(hubs)}'
        '<div class="wrap layout">'
        f'<main>{grid}</main>'
        f'{_sidebar(popular)}'
        '</div>'
    )
    head_extra = (
        f'<meta name="description" content="{_esc_attr(TAGLINE)}">\n'
        f'<link rel="canonical" href="{base}/">\n'
        + _social_tags(site_name, TAGLINE, base + "/", og_img, "website")
    )
    html = _document(lang, f"{site_name}", head_extra, body_inner)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    _static_page("about", lang, f"About | {site_name}", _about_inner(),
                 desc="Who writes littletabi, how the guides are made, and why we publish what we can verify.")
    _static_page("disclosure", lang, f"Affiliate Disclosure | {site_name}", _disclosure_inner(),
                 desc="How littletabi makes money: which links are affiliate links, and what that does and does not change.")
    _static_page("privacy", lang, f"Privacy Policy | {site_name}", _privacy_inner(),
                 desc="What littletabi collects, what it does not, and how analytics and the email list are handled.")
    _static_page("contact", lang, f"Contact | {site_name}", _contact_inner(),
                 desc="Corrections, questions and partnership enquiries for littletabi.")
    # 透明性ページ（AI生成であることを正面から説明＝E-E-A-Tと安心を両立）
    _static_page("how-we-make-guides", lang, f"How We Make These Guides | {site_name}", eeat.HOW_WE_MAKE,
                 desc="Our process: AI-assisted drafting, automated checks, and what we verify against official sources before publishing.")
    _write_cname(cfg)
    _migrate_legacy(cfg, popular)
    _upgrade_seo(cfg)          # 既存記事にOG/Twitter/JSON-LDを後付け（冪等）
    _upgrade_eeat_links(cfg)   # 既存記事に内部リンク/rel=sponsored/透明性/Org schemaを後付け（LLM不要・冪等）
    _write_seo_files(cfg)      # sitemap.xml + robots.txt + llms.txt を生成
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    log.info("サイト再生成 (記事%d / featured+grid+sidebar+SEO)", len(posts))
