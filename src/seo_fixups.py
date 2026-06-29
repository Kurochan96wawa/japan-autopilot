"""SEO仕上げ：①重複(cannibalization)統合 ②ハブのピラー加筆 ③sitemap整合。site構築後に冪等で再適用。

regen/_build_hubs/_write_seo_files で上書きされても、daily実行のたびに本モジュールが後段で自動的に直す。
LLM不要・外部依存ゼロ。数値は捏造せず「公式で確認」と明記（誠実＆正確）。

実行: `python -m src.seo_fixups`（daily.yml / extras.yml の task=seo_fixups から）。
"""
from __future__ import annotations
import datetime
import re
from .util import SITE_DIR, load_settings, log

# ── ① 重複統合：旧スラッグ -> 正(canonical)スラッグ（弱い方を強い方=マネーページへ寄せる）──
_CANONICAL_OVERRIDES = {
    "tokyo-disney-vs-disneysea-for-kids": "tokyo-disneyland-vs-disneysea-young-kids",
    "tokyo-family-hotels-connecting-rooms-kitchenettes": "best-family-hotels-tokyo-connecting-rooms",
}

# ── ③ sitemapに必ず載せたい静的ページ（site.pyの投稿追跡に乗らない手動ページ）──
_SITEMAP_ENSURE = ["plan.html"]

# ── ② ハブ加筆：transportハブに入れるピラー本文（事実ベース・価格は書かない）──
_TRANSPORT_PILLAR = (
    '<section id="pillar-transport" class="pillar" style="margin:1.4em 0">'
    '<h2>How families actually get around Japan</h2>'
    '<p>Japan is one of the easiest countries in the world to explore by public transport with '
    'children &mdash; but a few family-specific things are worth knowing before you go. Below is the '
    'short version; each linked guide goes deeper.</p>'
    '<h3>IC cards (Suica / PASMO) &mdash; tap and go</h3>'
    '<p>A rechargeable IC card lets you tap through ticket gates and pay on most trains, subways and '
    'buses without buying paper tickets each time, and works at convenience stores too. Children can '
    'have their own discounted children&rsquo;s IC card. It removes a lot of friction when you are '
    'travelling with kids and luggage. (Confirm the current card options and any registration rules '
    'on the official transit operator&rsquo;s site.)</p>'
    '<h3>Child fares</h3>'
    '<p>As a general rule, primary-school-age children (roughly 6&ndash;11) pay a reduced child fare, '
    'and very young children travel free within set limits when accompanied by a paying adult. The '
    'exact ages, limits and reserved-seat rules vary by operator, so check the official fare page for '
    'your route before relying on it.</p>'
    '<h3>Strollers, elevators and crowds</h3>'
    '<p>Most major stations have elevators, but they can be tucked away and the walk between lines is '
    'sometimes long. A compact, easily folded stroller is the most flexible choice, and travelling '
    'just outside the busiest rush hours makes a real difference with little ones. See our '
    '<a href="/stroller-friendly-tokyo-navigating-the-city-with-kids.html">stroller-friendly Tokyo</a> '
    'and <a href="/kyoto-with-a-stroller-accessible-routes-kid-friendly-spots.html">Kyoto with a stroller</a> '
    'guides for step-free routes.</p>'
    '<h3>Shinkansen and long-distance</h3>'
    '<p>For the bullet train, reserving seats is worth it when travelling as a family, especially in peak '
    'periods. If you have a stroller or large cases, note that the dedicated oversized-baggage spaces now '
    'need to be reserved in advance &mdash; our '
    '<a href="/shinkansen-oversized-baggage-rules-for-families-in-2026.html">Shinkansen oversized-baggage guide</a> '
    'explains how, and the '
    '<a href="/japan-rail-pass-with-kids-is-it-worth-it-for-families.html">Japan Rail Pass guide</a> '
    'helps you decide whether a pass is worth it for your itinerary (it usually is not for a Tokyo-only trip).</p>'
    '<h3>Taxis and car seats</h3>'
    '<p>Regular taxis generally do not carry child car seats. For city hops this is usually fine for short '
    'rides, but for longer drives or rural areas a rental car with properly fitted seats is the safer plan &mdash; '
    'see <a href="/renting-a-car-in-japan-with-car-seats-family-travel-guide.html">renting a car with car seats</a>.</p>'
    '<p class="pillar-note" style="font-size:.85rem;color:#6b7280">Fares, ages and rules change and vary by '
    'operator &mdash; always confirm the current details on the official transit site before you travel.</p>'
    '</section>'
)

_HUB_PILLARS = {
    "japan-with-kids-transport": _TRANSPORT_PILLAR,
}


def _base() -> str:
    try:
        b = (load_settings().get("site", {}) or {}).get("base_url")
        return (b or "https://littletabi.com").rstrip("/")
    except Exception:
        return "https://littletabi.com"


def _consolidate_canonicals() -> int:
    base = _base()
    fixed = 0
    for old, target in _CANONICAL_OVERRIDES.items():
        path = SITE_DIR / f"{old}.html"
        if not path.exists() or not (SITE_DIR / f"{target}.html").exists():
            log.info("seo_fixups: canonical skip %s（旧 or 正 が無い）", old)
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        want = f'<link rel="canonical" href="{base}/{target}.html">'
        if 'rel="canonical"' in html:
            new = re.sub(r'<link rel="canonical"[^>]*>', want, html, count=1)
        else:
            new = html.replace("</head>", want + "\n</head>", 1)
        if new != html:
            path.write_text(new, encoding="utf-8")
            fixed += 1
            log.info("seo_fixups: canonical %s -> %s", old, target)
    return fixed


def _enrich_hubs() -> int:
    done = 0
    for slug, block in _HUB_PILLARS.items():
        path = SITE_DIR / f"{slug}.html"
        if not path.exists():
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'id="pillar-transport"' in html:  # 冪等：既に入っていれば何もしない
            continue
        if '<div class="grid"' in html:
            new = html.replace('<div class="grid"', block + '<div class="grid"', 1)
        elif "</article>" in html:
            new = html.replace("</article>", block + "</article>", 1)
        else:
            continue
        if new != html:
            path.write_text(new, encoding="utf-8")
            done += 1
            log.info("seo_fixups: hub加筆 %s", slug)
    return done


def _fix_sitemap() -> int:
    """sitemap整合：①統合した重複URLを除去 ②必須静的ページ(plan.html等)を確実に収録。"""
    sm = SITE_DIR / "sitemap.xml"
    if not sm.exists():
        return 0
    try:
        xml = sm.read_text(encoding="utf-8")
    except Exception:
        return 0
    base = _base()
    today = datetime.date.today().isoformat()
    changed = 0

    # ① canonicalで束ねた弱い方は sitemap から外す（自己矛盾シグナルを避ける）
    for old in _CANONICAL_OVERRIDES:
        pat = r"\s*<url>\s*<loc>[^<]*/" + re.escape(old) + r"\.html</loc>[\s\S]*?</url>"
        new = re.sub(pat, "", xml, count=1)
        if new != xml:
            xml = new
            changed += 1
            log.info("seo_fixups: sitemapから重複URL除去 %s", old)

    # ② 手動の静的ページが抜けていれば追加（plan.html 等）
    for page in _SITEMAP_ENSURE:
        if f"/{page}<" in xml:
            continue
        block = (
            "<url>\n<loc>{b}/{p}</loc>\n<lastmod>{d}</lastmod>\n"
            "<changefreq>monthly</changefreq>\n<priority>0.7</priority>\n</url>\n"
        ).format(b=base, p=page, d=today)
        if "</urlset>" in xml:
            xml = xml.replace("</urlset>", block + "</urlset>", 1)
            changed += 1
            log.info("seo_fixups: sitemapに追加 %s", page)

    if changed:
        sm.write_text(xml, encoding="utf-8")
    return changed


def run() -> dict:
    c = _consolidate_canonicals()
    h = _enrich_hubs()
    s = _fix_sitemap()
    log.info("seo_fixups完了: canonical統合=%d, ハブ加筆=%d, sitemap修正=%d", c, h, s)
    return {"canonicals": c, "hubs": h, "sitemap": s}


def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("seo_fixups失敗: %s", e)


if __name__ == "__main__":
    main()
