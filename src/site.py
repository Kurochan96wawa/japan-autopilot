"""GitHub Pages 用サイト生成。Pinが指す先のランディング兼ブログ。
業界標準の構造（ヒーロー＋サムネイル付きカード＋サイドバー＋筆者欄＋フッター法務）で、
初見でも自然に見え、PC/スマホ両対応。記事はリサーチ型・編集部名義（AI生成を偽らない）。
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from .util import load_settings, SITE_DIR, log

BRAND = "littletabi"
TAGLINE = "Honest, practical guides for families travelling to Japan with kids."
BYLINE = "By the littletabi editors"
# 連絡フォーム（Formspreeの無料フォームID。未設定なら案内文を表示）
CONTACT_FORM_ACTION = ""

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

NAV_LINKS = [("/index.html", "Home"), ("/about.html", "About"), ("/contact.html", "Contact")]
NAV_JS = "<script>function tmenu(){var n=document.getElementById('nav');n.classList.toggle('open');}</script>"


def _header() -> str:
    links = "".join(f'<a href="{u}">{t}</a>' for u, t in NAV_LINKS)
    return (
        '<header class="site"><div class="wrap bar">'
        '<a class="brand" href="/index.html">little<b>tabi</b></a>'
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
        '<p>Independent, research-based travel guides for families visiting Japan. '
        'We are not affiliated with any tourism board or the companies we mention.</p></div>'
        '<div><h5>Explore</h5><ul>'
        '<li><a href="/index.html">Home</a></li>'
        '<li><a href="/about.html">About</a></li>'
        '<li><a href="/contact.html">Contact</a></li></ul></div>'
        '<div><h5>Legal</h5><ul>'
        '<li><a href="/disclosure.html">Affiliate Disclosure</a></li>'
        '<li><a href="/privacy.html">Privacy Policy</a></li></ul></div>'
        '</div>'
        f'<div class="legal">Some links are affiliate links; if you book or buy through them we may '
        f'earn a small commission at no extra cost to you. As an Amazon Associate we earn from qualifying '
        f'purchases. &copy; {year} littletabi. All rights reserved.</div>'
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
        f"{NAV_JS}\n"
        "</body>\n</html>\n"
    )


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "post"


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
        items = "".join(f'<li><a href="/{s}.html">{t}</a></li>' for s, t in popular)
        pop_html = f'<div class="widget"><h4>Popular guides</h4><ul>{items}</ul></div>'
    return (
        '<aside class="side">'
        '<div class="widget about"><h4>About littletabi</h4>'
        '<p>We write honest, practical guides for parents exploring Japan with kids — '
        'transport, food, what to pack and where to go. '
        '<a href="/about.html">More about us →</a></p></div>'
        f"{pop_html}"
        '<div class="widget"><h4>Start here</h4><ul>'
        '<li><a href="/index.html">All guides</a></li>'
        '<li><a href="/about.html">How we create our guides</a></li>'
        '<li><a href="/disclosure.html">Affiliate disclosure</a></li>'
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
    transparency = ('<p class="transparency">How we create our guides: littletabi guides are '
                    'researched from public sources and written with AI assistance, then reviewed by '
                    'our editors for usefulness and accuracy. Prices, hours and rules change — '
                    'please confirm details on official sites before you travel.</p>')
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
    canonical = f"{base}/{slug}.html"
    date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
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
        '<meta name="author" content="littletabi editors">\n'
    )
    hero_html = f'<img class="hero-img" src="/{image_rel}" alt="{title}">'
    category = content.get("board_hint") or "Japan with kids"
    html = _article_page(
        lang=lang, title_tag=f"{title} | {site_name}", head_extra=head_extra,
        title=title, category=category, date_str=date_str, hero_html=hero_html,
        credit_html=credit_html, body_html=content["article_html"],
        disclosure_html=content.get("disclosure", ""), popular=[],
    )
    out = SITE_DIR / f"{slug}.html"
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info("記事ページ生成: %s.html", slug)
    return canonical


def _static_page(slug: str, lang: str, title_tag: str, inner: str) -> None:
    body_inner = f'<div class="wrap single narrow"><article class="post">{inner}</article></div>'
    (SITE_DIR / f"{slug}.html").write_text(_document(lang, title_tag, "", body_inner), encoding="utf-8")


def _about_inner() -> str:
    return (
        "<h1>About littletabi</h1>"
        "<p><strong>littletabi</strong> is an independent guide for parents planning a trip to Japan "
        "with their children &mdash; from toddlers to teens. We focus on the practical, parent-specific "
        "questions the big travel sites skip: stroller access, kid-friendly food, getting around with "
        "little ones, what to pack, and staying safe and sane on the road.</p>"
        "<h2>How we create our guides</h2>"
        "<p>Our guides are researched from public sources and written with the help of AI, then reviewed "
        "by our editors for usefulness, clarity and accuracy. We aim to be specific and honest &mdash; "
        "never clickbait, and we don't claim first-hand experiences we haven't had. Because details like "
        "prices, opening hours and rules change often, please always confirm the latest information on "
        "official websites before you travel.</p>"
        "<h2>Independence &amp; funding</h2>"
        "<p>littletabi is not affiliated with any government tourism organisation or the businesses we "
        'mention. Some of our links are affiliate links, which help keep the site free &mdash; see our '
        '<a href="/disclosure.html">Affiliate Disclosure</a>. Questions or corrections? '
        '<a href="/contact.html">Get in touch</a>.</p>'
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
        "<p>littletabi is a static website. We do not ask for, collect or store personal information, "
        "and we do not require you to create an account. We do not set advertising or tracking cookies. "
        "Our hosting and content-delivery providers may automatically log standard technical data (such "
        "as IP address and browser type) for security and operations, as is typical for any website.</p>"
        "<h2>Contact form</h2>"
        "<p>If you contact us through our form, the details you submit (such as your name, email and "
        "message) are processed by our third-party form provider solely to deliver your message to us. "
        "We use them only to respond to you.</p>"
        "<h2>Affiliate links &amp; third parties</h2>"
        "<p>We use affiliate links (see our <a href='/disclosure.html'>Affiliate Disclosure</a>). When "
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
        "<p>Questions? <a href='/contact.html'>Contact us</a>.</p>"
    )


def _contact_inner() -> str:
    if CONTACT_FORM_ACTION:
        form = (
            f'<form class="cform" action="{CONTACT_FORM_ACTION}" method="POST">'
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
    skip = {"index.html", "about.html", "disclosure.html", "privacy.html", "contact.html"}
    for path in SITE_DIR.glob("*.html"):
        if path.name in skip:
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


def rebuild_index(state: dict) -> None:
    cfg = load_settings()
    site_name = cfg["site"]["site_name"]
    lang = cfg["niche"].get("language", "en")
    posts = [p for p in reversed(state.get("posted", [])[-200:])
             if p.get("slug") and p.get("article_title")]
    popular = [(p["slug"], p["article_title"]) for p in posts[:6]]

    if posts:
        f = posts[0]
        feat = (
            '<section class="hero-feat">'
            f'<div class="ph"><a href="/{f["slug"]}.html"><img src="{_thumb(f)}" alt="{f["article_title"]}"></a></div>'
            '<div class="tx"><span class="eyebrow">Featured guide</span>'
            f'<h1><a href="/{f["slug"]}.html">{f["article_title"]}</a></h1>'
            f'<p>{_excerpt(f)}</p>'
            f'<p class="meta">{BYLINE}</p>'
            f'<a class="readmore" href="/{f["slug"]}.html">Read the guide →</a></div>'
            '</section>'
        )
        cards = []
        for p in posts[1:]:
            cards.append(
                '<article class="card">'
                f'<a class="ph" href="/{p["slug"]}.html"><img src="{_thumb(p)}" alt="{p["article_title"]}"></a>'
                '<div class="body">'
                f'<h3><a href="/{p["slug"]}.html">{p["article_title"]}</a></h3>'
                f'<p>{_excerpt(p)}</p>'
                f'<p class="meta">{BYLINE}</p>'
                '</div></article>'
            )
        grid = (f'<h2 class="sec-title">Latest guides</h2><div class="grid">{"".join(cards)}</div>'
                if cards else "")
    else:
        feat = ""
        grid = '<p class="empty">New guides are published regularly &mdash; check back soon.</p>'

    body_inner = (
        f'<div class="wrap">{feat}</div>'
        '<div class="wrap layout">'
        f'<main>{grid}</main>'
        f'{_sidebar(popular)}'
        '</div>'
    )
    head_extra = (f'<meta name="description" content="{TAGLINE}">\n'
                  f'<link rel="canonical" href="{cfg["site"]["base_url"].rstrip("/")}/">\n')
    html = _document(lang, f"{site_name}", head_extra, body_inner)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    _static_page("about", lang, f"About | {site_name}", _about_inner())
    _static_page("disclosure", lang, f"Affiliate Disclosure | {site_name}", _disclosure_inner())
    _static_page("privacy", lang, f"Privacy Policy | {site_name}", _privacy_inner())
    _static_page("contact", lang, f"Contact | {site_name}", _contact_inner())
    _write_cname(cfg)
    _migrate_legacy(cfg, popular)
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    log.info("サイト再生成 (記事%d / featured+grid+sidebar)", len(posts))
