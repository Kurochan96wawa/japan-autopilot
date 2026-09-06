"""施策D: 記事から AMP Web Story を生成して docs/stories/ に公開する（第一者・偽装リスク無し）。

Google Search / Discover / Images の視覚枠に拾われる。og:image ＋ 記事の要点(h2) から 1記事=1ストーリー。
**有効なAMPだけを出す**方針：
  - インラインstyleは使わず、全CSSを <style amp-custom> に集約（AMPの必須要件）。
  - poster(og:image)が無い記事は skip（poster必須）。
  - publisher-logo(正方PNG)は Pillow で生成。Pillow が無ければ全体 skip（壊れたStoryを作らない）。
  - amp-story-cta-layer は先頭以外（最終ページ）のみに置く。
冪等：内容が同じなら書き換えない。実行: `python -m src.webstory`（daily後段 / extras task=webstory）。
"""
from __future__ import annotations
import html as _html
import re

from . import linker as _linker
from .util import SITE_DIR, load_settings, log

STORIES_DIR = "stories"
LOGO_REL = "stories/publisher-logo.png"

# 量産を避け主要記事だけを対象（slug部分一致）。
_SLUG_HINT = ("itinerary", "with-kids", "with-young-children", "best-", "-compared",
              "transport", "allergies", "diapers", "guide", "things-to-do", "vs-")
# Story化しないページ（ツール/法務/索引/noindex系）。
_SKIP_SLUG = ("embeds", "allergy-card", "get-the-japan-checklist", "how-we-make-guides",
              "about", "privacy", "contact", "index", "404", "japan-with-kids-")  # 末尾はハブ


def _base_url() -> str:
    try:
        b = (load_settings().get("site", {}) or {}).get("base_url") or "https://littletabi.com"
    except Exception:
        b = "https://littletabi.com"
    return b.rstrip("/")


def _ensure_logo() -> bool:
    """publisher-logo(96x96 PNG)を Pillow で生成。失敗時 False（Story生成を中止）。"""
    path = SITE_DIR / LOGO_REL
    if path.exists():
        return True
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        log.error("webstory: Pillow未導入のためWeb Story生成をskip: %s", e)
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (96, 96), (184, 0, 90))  # brand accent
        ImageDraw.Draw(img).text((28, 36), "lt", fill=(255, 255, 255))
        img.save(str(path), "PNG")
        log.info("webstory: publisher-logo生成 %s", LOGO_REL)
        return True
    except Exception as e:
        log.error("webstory: logo生成失敗: %s", e)
        return False


def _meta(html: str, key: str, attr: str = "property") -> str:
    m = re.search(r'<meta ' + attr + r'="' + re.escape(key) + r'"\s+content="([^"]*)"', html)
    return _html.unescape(m.group(1)) if m else ""


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=True)


def _extract(html: str):
    title = _meta(html, "og:title")
    if not title:
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        title = re.sub(r"\s*[|｜].*$", "", m.group(1)).strip() if m else ""
    if not title:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        title = re.sub("<[^>]+>", "", m.group(1)).strip() if m else "Japan with kids"
    img = _meta(html, "og:image")
    desc = _meta(html, "description", "name")
    pts = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)
    pts = [re.sub("<[^>]+>", "", p).strip() for p in pts]
    pts = [p for p in pts if p and "FAQ" not in p and 3 < len(p) < 90][:4]
    return title.strip(), img.strip(), desc.strip(), pts


_AMP_BOILERPLATE = (
    '<style amp-boilerplate>body{-webkit-animation:-amp-start 8s steps(1,end) 0s 1 normal both;'
    '-moz-animation:-amp-start 8s steps(1,end) 0s 1 normal both;'
    '-ms-animation:-amp-start 8s steps(1,end) 0s 1 normal both;'
    'animation:-amp-start 8s steps(1,end) 0s 1 normal both}'
    '@-webkit-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}'
    '@-moz-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}'
    '@-ms-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}'
    '@-o-keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}'
    '@keyframes -amp-start{from{visibility:hidden}to{visibility:visible}}</style>'
    '<noscript><style amp-boilerplate>body{-webkit-animation:none;-moz-animation:none;'
    '-ms-animation:none;animation:none}</style></noscript>'
)

_AMP_CUSTOM = (
    '<style amp-custom>'
    '.scrim{width:100%;height:100%;background:linear-gradient(transparent 35%,rgba(0,0,0,.62))}'
    '.fallback{width:100%;height:100%;background:#fff0f6}'
    '.txt{color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;'
    'text-shadow:0 1px 5px rgba(0,0,0,.65);padding:10px 14px}'
    '.txt h1{font-size:1.55rem;line-height:1.3;margin:.1em 0}'
    '.lead{font-size:1rem;opacity:.95}'
    '.pt{font-size:1.3rem;font-weight:700;line-height:1.35}'
    '.cta{display:inline-block;background:#b8005a;color:#fff;padding:11px 18px;border-radius:22px;'
    'text-decoration:none;font-weight:700;'
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}'
    '</style>'
)


def _page(pid: str, img: str, inner: str, cta: str = "") -> str:
    if img:
        fill = ('<amp-story-grid-layer template="fill">'
                f'<amp-img src="{_esc(img)}" width="720" height="1280" layout="responsive" '
                'alt="Japan with kids"></amp-img></amp-story-grid-layer>'
                '<amp-story-grid-layer template="fill"><div class="scrim"></div></amp-story-grid-layer>')
    else:
        fill = '<amp-story-grid-layer template="fill"><div class="fallback"></div></amp-story-grid-layer>'
    return (f'<amp-story-page id="{pid}">{fill}'
            f'<amp-story-grid-layer template="vertical"><div class="txt">{inner}</div></amp-story-grid-layer>'
            f'{cta}</amp-story-page>')


def _story_html(base: str, slug: str, title: str, img: str, desc: str, pts) -> str:
    canonical = _linker.page_url(base, slug)   # 2026-09-06: 拡張子なしURLに統一
    logo = f"{base}/{LOGO_REL}"
    pages = [_page("cover", img,
                   f'<h1>{_esc(title)}</h1>' + (f'<p class="lead">{_esc(desc)}</p>' if desc else ""))]
    for i, p in enumerate(pts):
        pages.append(_page(f"p{i}", img, f'<p class="pt">{_esc(p)}</p>'))
    cta = (f'<amp-story-cta-layer><a href="{canonical}" class="cta">Read the full guide &rarr;</a>'
           '</amp-story-cta-layer>')
    pages.append(_page("outro", img, '<p class="pt">Plan the whole trip with our free guide</p>', cta))
    return (
        '<!doctype html><html amp lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,minimum-scale=1,initial-scale=1">'
        f'<link rel="canonical" href="{canonical}">'
        f'<title>{_esc(title)}</title>'
        '<script async src="https://cdn.ampproject.org/v0.js"></script>'
        '<script async custom-element="amp-story" src="https://cdn.ampproject.org/v0/amp-story-1.0.js"></script>'
        + _AMP_BOILERPLATE + _AMP_CUSTOM +
        '</head><body>'
        f'<amp-story standalone title="{_esc(title)}" publisher="littletabi" '
        f'publisher-logo-src="{logo}" poster-portrait-src="{_esc(img)}">'
        + "".join(pages) +
        '</amp-story></body></html>'
    )


def _is_target(slug: str) -> bool:
    # 301統合済みの旧slugはWeb Storyを作らない（統合先へ寄せた導線を割り戻さないため）。
    from . import linker as _linker
    if slug in _linker.REDIRECTED_SLUGS:
        return False
    if any(k in slug for k in _SKIP_SLUG):
        return False
    return any(k in slug for k in _SLUG_HINT)


def _add_to_sitemap(locs) -> None:
    sm = SITE_DIR / "sitemap.xml"
    if not sm.exists():
        return
    try:
        xml = sm.read_text(encoding="utf-8")
    except Exception:
        return
    if "</urlset>" not in xml:
        return
    import datetime
    today = datetime.date.today().isoformat()
    add = ""
    for loc in locs:
        if loc in xml:
            continue
        add += (f"<url>\n<loc>{loc}</loc>\n<lastmod>{today}</lastmod>\n"
                "<changefreq>monthly</changefreq>\n<priority>0.5</priority>\n</url>\n")
    if add:
        sm.write_text(xml.replace("</urlset>", add + "</urlset>", 1), encoding="utf-8")
        log.info("webstory: sitemapにstories追加")


def _prune_redirected_stories() -> int:
    """301統合済みslugのWeb Story実体とsitemap行を取り除く（過去runの残骸対策）。"""
    from . import linker as _linker
    base = _base_url()
    removed = 0
    sm = SITE_DIR / "sitemap.xml"
    try:
        text = sm.read_text(encoding="utf-8") if sm.exists() else ""
    except Exception:
        text = ""
    for slug in _linker.REDIRECTED_SLUGS:
        f = SITE_DIR / STORIES_DIR / f"{slug}.html"
        if f.exists():
            try:
                f.unlink(); removed += 1
                log.info("webstory: 301統合済みのWeb Story削除 %s", slug)
            except Exception as e:
                log.error("webstory: Web Story削除失敗 %s: %s", slug, e)
        loc = f"{base}/{STORIES_DIR}/{slug}.html"
        text = re.sub(r"\s*<url>\s*<loc>" + re.escape(loc) + r"(?:\.html)?</loc>.*?</url>", "", text, flags=re.S)
    if text and sm.exists() and text != sm.read_text(encoding="utf-8"):
        sm.write_text(text, encoding="utf-8")
        log.info("webstory: sitemapから301統合済みstoriesを除去")
    return removed


def run() -> dict:
    base = _base_url()
    made = 0
    skipped = 0
    if not _ensure_logo():
        return {"stories": 0, "skipped": 0, "logo": False}
    out_locs = []
    for path in SITE_DIR.glob("*.html"):
        slug = path.stem
        if not _is_target(slug):
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        title, img, desc, pts = _extract(html)
        if not img or not pts:  # poster必須＋中身が無いものはskip（無効Story回避）
            skipped += 1
            continue
        story = _story_html(base, slug, title, img, desc, pts)
        dest = SITE_DIR / STORIES_DIR / f"{slug}.html"
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and dest.read_text(encoding="utf-8") == story:  # 冪等
                out_locs.append(_linker.page_url(base, f"{STORIES_DIR}/{slug}"))
                continue
            dest.write_text(story, encoding="utf-8")
            made += 1
            out_locs.append(_linker.page_url(base, f"{STORIES_DIR}/{slug}"))
            log.info("webstory: Web Story生成 %s", slug)
        except Exception as e:
            log.error("webstory: 生成失敗 %s: %s", slug, e)
    _prune_redirected_stories()
    _add_to_sitemap(out_locs)
    log.info("webstory完了: 生成=%d, skip=%d", made, skipped)
    return {"stories": made, "skipped": skipped, "logo": True}


def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("webstory実行失敗: %s", e)


if __name__ == "__main__":
    main()
