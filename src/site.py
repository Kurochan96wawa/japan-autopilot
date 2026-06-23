"""GitHub Pages 用の記事HTMLを生成。Pinが指す先のランディングページ。
1ページに複数アフィリリンク+開示文を置けるので、Pinに直貼りするより安全＆高CVR。
ヘッダー/ナビ/フッター/About/開示ページを備え、初見でも信頼できるサイトにする。
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from .util import load_settings, SITE_DIR, log

BRAND = "littletabi"
TAGLINE = "Honest, parent-tested guides for visiting Japan with kids."

BASE_CSS = """
:root{--ink:#1f2937;--muted:#6b7280;--accent:#b8005a;--soft:#fff0f6;--line:#ececf1;--bg:#fffdfb}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;margin:0;color:var(--ink);background:var(--bg);line-height:1.7}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:760px;margin:0 auto;padding:0 20px}
header.site{border-bottom:1px solid var(--line);background:#fff;position:sticky;top:0;z-index:10}
header.site .wrap{display:flex;align-items:center;justify-content:space-between;min-height:64px}
.brand{font-weight:800;font-size:1.2rem;letter-spacing:-.02em;color:var(--ink)}
.brand b{color:var(--accent)}
nav.main a{margin-left:18px;color:var(--ink);font-size:.95rem;font-weight:500}
nav.main a:hover{color:var(--accent);text-decoration:none}
main{padding:8px 0}
.hero{padding:30px 0 6px}
.hero h1{font-size:2rem;line-height:1.2;margin:.1em 0}
.hero p{color:var(--muted);font-size:1.06rem;margin:.5em 0 0}
article h1{font-size:1.85rem;line-height:1.25;margin:.2em 0 .3em}
article h2{margin-top:1.7em}
img.hero-img{width:100%;border-radius:14px;margin:.4em 0}
ul.cards{list-style:none;padding:0;margin:26px 0 8px;display:grid;gap:14px}
li.card{border:1px solid var(--line);border-radius:14px;padding:18px 20px;background:#fff;transition:box-shadow .15s ease,transform .15s ease}
li.card:hover{box-shadow:0 8px 24px rgba(0,0,0,.06);transform:translateY(-1px)}
li.card a.title{font-weight:700;font-size:1.12rem;color:var(--ink)}
li.card a.title:hover{color:var(--accent);text-decoration:none}
li.card p{color:var(--muted);margin:.4em 0 0;font-size:.95rem}
.credit{font-size:.75rem;color:#9aa0aa;margin:.1em 0 1em}
.disc{font-size:.85rem;color:var(--muted);background:var(--soft);border:1px solid #ffe0ee;border-radius:12px;margin:2.4em 0 0;padding:14px 16px}
.empty{color:var(--muted);padding:18px 0}
footer.site{border-top:1px solid var(--line);margin-top:52px;background:#fff;color:var(--muted);font-size:.9rem}
footer.site .wrap{padding:26px 20px}
footer.site .links{display:flex;flex-wrap:wrap;gap:8px 20px;margin-bottom:10px}
footer.site a{color:var(--muted)}
footer.site a:hover{color:var(--accent)}
.tiny{font-size:.8rem;color:#9aa0aa;margin:.4em 0 0}
"""


def _header() -> str:
    return (
        '<header class="site"><div class="wrap">'
        '<a class="brand" href="/index.html">little<b>tabi</b></a>'
        '<nav class="main">'
        '<a href="/index.html">Home</a>'
        '<a href="/about.html">About</a>'
        '<a href="/disclosure.html">Disclosure</a>'
        '</nav></div></header>'
    )


def _footer() -> str:
    year = datetime.now(timezone.utc).year
    return (
        '<footer class="site"><div class="wrap">'
        '<div class="links">'
        '<a href="/index.html">Home</a>'
        '<a href="/about.html">About</a>'
        '<a href="/disclosure.html">Affiliate Disclosure &amp; Privacy</a>'
        '</div>'
        '<p>littletabi publishes independent, research-based travel guides for families '
        'visiting Japan. We are not affiliated with any tourism board or the companies we mention.</p>'
        '<p class="tiny">Some links are affiliate links; if you book or buy through them we may earn a '
        f'small commission at no extra cost to you. &copy; {year} littletabi.</p>'
        '</div></footer>'
    )


def _document(lang: str, title_tag: str, head_extra: str, body_inner: str) -> str:
    return (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title_tag}</title>\n"
        f"{head_extra}"
        f"<style>{BASE_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{_header()}\n"
        f"{body_inner}\n"
        f"{_footer()}\n"
        "</body>\n</html>\n"
    )


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "post"


def render_article(content: dict, image_rel: str, credit: dict, slug: str) -> str:
    cfg = load_settings()
    base = cfg["site"]["base_url"].rstrip("/")
    lang = cfg["niche"]["language"]
    site_name = cfg["site"]["site_name"]
    title = content["article_title"]
    meta = content.get("meta_description", "")
    canonical = f"{base}/{slug}.html"
    credit_html = ""
    if credit.get("photographer"):
        credit_html = (
            '<p class="credit">Photo by '
            f'<a href="{credit.get("url", "#")}" rel="nofollow noopener">{credit["photographer"]}</a> on Pexels</p>'
        )
    head_extra = (
        f'<meta name="description" content="{meta}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        '<meta property="og:type" content="article">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{meta}">\n'
        f'<meta property="og:image" content="{base}/{image_rel}">\n'
    )
    body_inner = (
        '<main class="wrap"><article>\n'
        f"<h1>{title}</h1>\n"
        f'<img class="hero-img" src="/{image_rel}" alt="{title}">\n'
        f"{credit_html}\n"
        f"{content['article_html']}\n"
        f'<p class="disc">{content.get("disclosure", "")}</p>\n'
        "</article></main>"
    )
    html = _document(lang, f"{title} | {site_name}", head_extra, body_inner)
    out = SITE_DIR / f"{slug}.html"
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info("記事ページ生成: %s.html", slug)
    return canonical


def _write_page(slug: str, lang: str, title_tag: str, body_inner: str) -> None:
    html = _document(lang, title_tag, "", body_inner)
    (SITE_DIR / f"{slug}.html").write_text(html, encoding="utf-8")


def _about_inner() -> str:
    return (
        '<main class="wrap"><article>\n'
        "<h1>About littletabi</h1>\n"
        "<p><strong>littletabi</strong> is an independent guide for parents planning a trip to Japan "
        "with their children &mdash; from toddlers to teens. We focus on the practical, parent-specific "
        "questions the big travel sites skip: stroller access, kid-friendly food, getting around with "
        "little ones, what to pack, and staying safe and sane on the road.</p>\n"
        "<h2>How we write</h2>\n"
        "<p>Each guide is researched and written to be specific and genuinely useful &mdash; never "
        "clickbait. Because details like prices, opening hours and rules change often, please always "
        "confirm the latest information on official websites before you travel.</p>\n"
        "<h2>Independence</h2>\n"
        "<p>littletabi is not affiliated with any government tourism organisation or the businesses we "
        'mention. Some of our links are affiliate links &mdash; see our <a href="/disclosure.html">'
        "Affiliate Disclosure &amp; Privacy</a> page for details.</p>\n"
        "</article></main>"
    )


def _disclosure_inner() -> str:
    return (
        '<main class="wrap"><article>\n'
        "<h1>Affiliate Disclosure &amp; Privacy</h1>\n"
        "<h2>Affiliate disclosure</h2>\n"
        "<p>Some links on littletabi are affiliate links. If you click one and make a booking or "
        "purchase, we may earn a small commission at no additional cost to you. We only recommend "
        "products and services we believe are genuinely useful for families travelling to Japan. "
        "These commissions help keep the site free to read.</p>\n"
        "<h2>Privacy</h2>\n"
        "<p>littletabi is a static website. We do not ask for or store your personal information, we "
        "don&rsquo;t sell data, and we don&rsquo;t set advertising or tracking cookies.</p>\n"
        "<h2>Photos</h2>\n"
        "<p>Photography is sourced from Pexels under the Pexels License. Individual photographers are "
        "credited on each article where applicable.</p>\n"
        "</article></main>"
    )


def _write_cname(cfg: dict) -> None:
    host = urlparse(cfg["site"]["base_url"]).netloc
    if host and not host.endswith("github.io"):
        (SITE_DIR / "CNAME").write_text(host + "\n", encoding="utf-8")


def _migrate_legacy(cfg: dict) -> None:
    """旧テンプレートで生成済みの記事HTMLを新テンプレートに包み直す。
    canonical/og の旧プレースホルダURLも現行 base_url に修正する。自己修復。"""
    base = cfg["site"]["base_url"].rstrip("/")
    skip = {"index.html", "about.html", "disclosure.html"}
    for path in SITE_DIR.glob("*.html"):
        if path.name in skip:
            continue
        try:
            txt = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'class="site"' in txt:
            continue  # 既に新テンプレート
        tm = re.search(r"<title>(.*?)</title>", txt, re.S)
        title_tag = tm.group(1).strip() if tm else cfg["site"]["site_name"]
        lm = re.search(r'<html lang="([^"]+)"', txt)
        lang = lm.group(1) if lm else "en"
        cm = re.search(r"</nav>(.*)</body>", txt, re.S)
        inner = (cm.group(1).strip() if cm else "")
        inner = inner.replace('class="hero"', 'class="hero-img"')
        inner = inner.replace("https://YOUR_GITHUB_USERNAME.github.io/japan-autopilot", base)
        head_tags = re.findall(r"<(?:meta|link)[^>]*>", txt)
        keep = [h for h in head_tags if ("og:" in h or 'name="description"' in h or 'rel="canonical"' in h)]
        head_extra = "".join(
            h.replace("https://YOUR_GITHUB_USERNAME.github.io/japan-autopilot", base) + "\n" for h in keep
        )
        body_inner = '<main class="wrap"><article>\n' + inner + "\n</article></main>"
        path.write_text(_document(lang, title_tag, head_extra, body_inner), encoding="utf-8")
        log.info("legacy記事を新テンプレに移行: %s", path.name)


def rebuild_index(state: dict) -> None:
    cfg = load_settings()
    site_name = cfg["site"]["site_name"]
    lang = cfg["niche"].get("language", "en")
    cards = []
    for p in reversed(state.get("posted", [])[-200:]):
        if p.get("slug") and p.get("article_title"):
            raw = p.get("meta_description") or p.get("last_pin_desc") or ""
            desc = re.sub(r"#\w+", "", raw).strip()
            if len(desc) > 140:
                desc = desc[:140].rstrip() + "…"
            desc_html = f"<p>{desc}</p>" if desc else ""
            cards.append(
                f'<li class="card"><a class="title" href="/{p["slug"]}.html">{p["article_title"]}</a>{desc_html}</li>'
            )
    if cards:
        list_html = f'<ul class="cards">{"".join(cards)}</ul>'
    else:
        list_html = '<p class="empty">New guides are published regularly &mdash; check back soon.</p>'
    body_inner = (
        '<main class="wrap">\n'
        f'<section class="hero"><h1>{site_name}</h1><p>{TAGLINE}</p></section>\n'
        f"{list_html}\n"
        "</main>"
    )
    html = _document(lang, site_name, "", body_inner)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    _write_page("about", lang, f"About | {site_name}", _about_inner())
    _write_page("disclosure", lang, f"Affiliate Disclosure & Privacy | {site_name}", _disclosure_inner())
    _write_cname(cfg)
    _migrate_legacy(cfg)
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    log.info("index/about/disclosure 再生成 (%d記事)", len(cards))
