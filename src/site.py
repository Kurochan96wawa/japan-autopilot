"""GitHub Pages 用の記事HTMLを生成。Pinが指す先のランディングページ。
1ページに複数アフィリリンク+開示文を置けるので、Pinに直貼りするより安全＆高CVR。
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from .util import load_settings, SITE_DIR, log

PAGE_TMPL = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | {site_name}</title>
<meta name="description" content="{meta}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta}">
<meta property="og:image" content="{img_url}">
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;margin:0 auto;padding:24px;line-height:1.7;color:#222}}
 img.hero{{width:100%;border-radius:12px}}
 a{{color:#b8005a}} h1{{font-size:1.7rem}} h2{{margin-top:1.6em}}
 .disc{{font-size:.85rem;color:#666;border-top:1px solid #eee;margin-top:2.5em;padding-top:1em}}
 .credit{{font-size:.75rem;color:#999}}
 nav{{font-size:.9rem;margin-bottom:1em}}
</style>
</head>
<body>
<nav><a href="./index.html">{site_name}</a></nav>
<h1>{title}</h1>
<img class="hero" src="{img_rel}" alt="{title}">
{credit_html}
{body}
<p class="disc">{disclosure}</p>
</body></html>
"""


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "post"


def render_article(content: dict, image_rel: str, credit: dict, slug: str) -> str:
    cfg = load_settings()
    base = cfg["site"]["base_url"].rstrip("/")
    lang = cfg["niche"]["language"]
    canonical = f"{base}/{slug}.html"
    credit_html = ""
    if credit.get("photographer"):
        credit_html = (f'<p class="credit">Photo by '
                       f'<a href="{credit.get("url","#")}">{credit["photographer"]}</a> on Pexels</p>')
    html = PAGE_TMPL.format(
        lang=lang,
        title=content["article_title"],
        site_name=cfg["site"]["site_name"],
        meta=content.get("meta_description", ""),
        canonical=canonical,
        img_url=f"{base}/{image_rel}",
        img_rel=image_rel,
        credit_html=credit_html,
        body=content["article_html"],
        disclosure=content.get("disclosure", ""),
    )
    out = SITE_DIR / f"{slug}.html"
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info("記事ページ生成: %s.html", slug)
    return canonical


def rebuild_index(state: dict) -> None:
    cfg = load_settings()
    name = cfg["site"]["site_name"]
    items = []
    for p in reversed(state.get("posted", [])[-200:]):
        if p.get("slug") and p.get("article_title"):
            items.append(f'<li><a href="./{p["slug"]}.html">{p["article_title"]}</a></li>')
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;margin:0 auto;padding:24px;line-height:1.8}}
a{{color:#b8005a;text-decoration:none}} li{{margin:.4em 0}}</style></head>
<body><h1>{name}</h1><p>Practical, honest guides for visiting Japan.</p>
<ul>{''.join(items)}</ul></body></html>"""
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    # GitHub PagesでJekyll処理を無効化（_で始まるパス等の事故防止）
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    log.info("index 再生成 (%d記事)", len(items))
