"""SEO仕上げ：①重複(cannibalization)統合 ②ハブのピラー加筆 ③sitemap整合。site構築後に冪等で再適用。

regen/_build_hubs/_write_seo_files で上書きされても、daily実行のたびに本モジュールが後段で自動的に直す。
LLM不要・外部依存ゼロ。数値は捏造せず「公式で確認」と明記（誠実＆正確）。

実行: `python -m src.seo_fixups`（daily.yml / extras.yml の task=seo_fixups から）。
"""
from __future__ import annotations
import datetime
import re
from .util import SITE_DIR, load_settings, log
from . import linker as _linker

# ── ① 重複統合：旧スラッグ -> 正(canonical)スラッグ（弱い方を強い方=マネーページへ寄せる）──
# linker.REDIRECT_MAP を単一の正とする（301 と canonical が食い違わないようにするため）。
_CANONICAL_OVERRIDES = dict(_linker.REDIRECT_MAP)

# ── ③ sitemapに必ず載せたい静的ページ（site.pyの投稿追跡に乗らない手動ページ）──
_SITEMAP_ENSURE = [
    "plan.html",
    "shinkansen-family-fare-calculator.html",
    "shinkansen-cost-for-families.html",
    "eating-out-in-japan-with-food-allergies.html",
]

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
    '<a href="/stroller-friendly-tokyo-navigating-the-city-with-kids">stroller-friendly Tokyo</a> '
    'and <a href="/kyoto-with-a-stroller-accessible-routes-kid-friendly-spots">Kyoto with a stroller</a> '
    'guides for step-free routes.</p>'
    '<h3>Shinkansen and long-distance</h3>'
    '<p>For the bullet train, reserving seats is worth it when travelling as a family, especially in peak '
    'periods. If you have a stroller or large cases, note that the dedicated oversized-baggage spaces now '
    'need to be reserved in advance &mdash; our '
    '<a href="/shinkansen-oversized-baggage-rules-for-families-in-2026">Shinkansen oversized-baggage guide</a> '
    'explains how, and the '
    '<a href="/japan-rail-pass-with-kids-is-it-worth-it-for-families">Japan Rail Pass guide</a> '
    'helps you decide whether a pass is worth it for your itinerary (it usually is not for a Tokyo-only trip).</p>'
    '<h3>Taxis and car seats</h3>'
    '<p>Regular taxis generally do not carry child car seats. For city hops this is usually fine for short '
    'rides, but for longer drives or rural areas a rental car with properly fitted seats is the safer plan &mdash; '
    'see <a href="/renting-a-car-in-japan-with-car-seats-family-travel-guide">renting a car with car seats</a>.</p>'
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


def _build_redirects() -> int:
    """docs/_redirects を linker.REDIRECT_MAP から冪等に生成する（Cloudflare Pages の301）。

    PR #18 では手書きの docs/_redirects をコミットしていたため、履歴の巻き戻しと
    再生成で消えた。生成物はsrc側が持つ、という方針に合わせてここで作り直す。
    """
    lines = [
        "# Cloudflare Pages 301 redirects — 自動生成 (src/seo_fixups.py, 元データ: src/linker.REDIRECT_MAP)",
        "# 手で編集しないこと。各行: /旧パス  /統合先  301（.html と拡張子なしの両形式）",
        "",
    ]
    for old, target in sorted(_linker.REDIRECT_MAP.items()):
        lines.append(f"/{old}       /{target}  301")
        lines.append(f"/{old}.html  /{target}  301")
    body = "\n".join(lines) + "\n"
    path = SITE_DIR / "_redirects"
    try:
        if path.exists() and path.read_text(encoding="utf-8") == body:
            return 0
        path.write_text(body, encoding="utf-8")
        log.info("seo_fixups: _redirects 生成 (%d slug)", len(_linker.REDIRECT_MAP))
        return 1
    except Exception as e:
        log.error("seo_fixups: _redirects生成失敗: %s", e)
        return 0


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
        want = f'<link rel="canonical" href="{_linker.page_url(base, target)}">'
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
        pat = r"\s*<url>\s*<loc>[^<]*/" + re.escape(old) + r"(?:\.html)?</loc>[\s\S]*?</url>"
        new = re.sub(pat, "", xml, count=1)
        if new != xml:
            xml = new
            changed += 1
            log.info("seo_fixups: sitemapから重複URL除去 %s", old)

    # ② 手動の静的ページが抜けていれば追加（plan.html 等）
    for page in _SITEMAP_ENSURE:
        loc = _linker.page_url(base, page)          # 2026-09-06: 拡張子なしURLで載せる
        if f"<loc>{loc}</loc>" in xml:
            continue
        block = (
            "<url>\n<loc>{u}</loc>\n<lastmod>{d}</lastmod>\n"
            "<changefreq>monthly</changefreq>\n<priority>0.7</priority>\n</url>\n"
        ).format(u=loc, d=today)
        if "</urlset>" in xml:
            xml = xml.replace("</urlset>", block + "</urlset>", 1)
            changed += 1
            log.info("seo_fixups: sitemapに追加 %s", page)

    if changed:
        sm.write_text(xml, encoding="utf-8")
    return changed


# 記事→ツールの内部リンクを冪等注入（発見性向上。ツールは自然リンクの持ち駒）。
# 各要素: (対象slug, 目印文字列, リンクの有無判定キー, 挿入するHTML)
_TOOL_LINKS = [
    (
        "japan-family-itinerary-tokyo-kyoto-osaka-with-young-children",
        "<strong>Rainy day:</strong> The museum is largely indoors.</p>",
        "shinkansen-family-fare-calculator",
        '\n<p><strong>Working out the fare?</strong> Kids 6\u201311 are about half price and under-6s often ride free '
        '\u2014 our <a href="/shinkansen-family-fare-calculator">Shinkansen family fare calculator</a> does the maths, '
        'and <a href="/shinkansen-cost-for-families">how much the Shinkansen costs for a family</a> explains the rules.</p>',
    ),
]


def _inject_tool_links() -> int:
    done = 0
    for slug, marker, present_key, html in _TOOL_LINKS:
        path = SITE_DIR / (slug + ".html")
        if not path.exists():
            continue
        page = path.read_text(encoding="utf-8")
        if present_key in page:          # 既にリンク済みなら触らない（冪等）
            continue
        if marker not in page:           # 目印が本文から消えていたら安全側でスキップ
            log.info("seo_fixups: tool-link marker not found in %s", slug)
            continue
        page = page.replace(marker, marker + html, 1)
        path.write_text(page, encoding="utf-8")
        done += 1
        log.info("seo_fixups: ツール内部リンク注入 %s", slug)
    return done


# ============================================================
# 文脈内部リンク（収益ページ・ツールへの導線）
# ============================================================
# 2026-08-22: 内部リンクの実測で、ホテル比較(収益ページ)の被リンクが4本と最も弱く、
# しかも GSC で実需要のあるクエリ（"tokyo hotel with kitchenette" 系）を持つ唯一のページ
# だった。宿泊クラスタの記事が2本しかないため related ブロックだけでは増やせない。
# そこで話題が実際に隣接する記事から、本文の文脈として1本ずつ張る。
#
# 上の _TOOL_LINKS は本文中の固定文言を目印にしており、本文が再生成されると目印が消えて
# スキップされる（実際に "marker not found" が出ていた）。こちらは related ブロック /
# 末尾開示 / </article> という**構造的な位置**を使うので、本文が変わっても効き続ける。
_CONTEXT_LINKS = [
    ("ryokan-stays-with-kids-in-japan-family-inns-etiquette-2026",
     "best-family-hotels-tokyo-connecting-rooms",
     '<p><strong>Mixing a ryokan with a city stay?</strong> Most families pair one or two ryokan nights '
     'with a Tokyo base &mdash; see our pick of '
     '<a href="/best-family-hotels-tokyo-connecting-rooms">Tokyo family hotels with connecting rooms '
     'and kitchenettes</a>.</p>'),
    ("family-onsen-japan-private-baths-kid-friendly-guide",
     "best-family-hotels-tokyo-connecting-rooms",
     '<p><strong>Where to stay either side of the onsen trip?</strong> '
     '<a href="/best-family-hotels-tokyo-connecting-rooms">Tokyo family hotels with connecting rooms</a> '
     'covers the city nights, including rooms with a kitchenette.</p>'),
    ("family-day-trips-from-tokyo-kid-friendly-escapes",
     "best-family-hotels-tokyo-connecting-rooms",
     '<p><strong>Day trips work best from a fixed base.</strong> If you have not booked yet, see '
     '<a href="/best-family-hotels-tokyo-connecting-rooms">family hotels in Tokyo with connecting rooms</a>.</p>'),
    ("stroller-friendly-tokyo-navigating-the-city-with-kids",
     "best-family-hotels-tokyo-connecting-rooms",
     '<p><strong>Stroller-friendly starts with the hotel.</strong> Lifts, room size and a place to park the buggy '
     'matter more than the neighbourhood &mdash; see '
     '<a href="/best-family-hotels-tokyo-connecting-rooms">Tokyo family hotels with connecting rooms</a>.</p>'),
    ("tokyo-s-best-themed-cafes-for-families-beyond-maid-cafes",
     "best-family-hotels-tokyo-connecting-rooms",
     '<p><strong>Staying central helps.</strong> Most of these cafes are an easy hop from the areas covered in '
     '<a href="/best-family-hotels-tokyo-connecting-rooms">our Tokyo family hotel picks</a>.</p>'),
    ("japan-family-itinerary-tokyo-kyoto-osaka-with-young-children",
     "best-family-hotels-tokyo-connecting-rooms",
     '<p><strong>Booking the Tokyo nights?</strong> '
     '<a href="/best-family-hotels-tokyo-connecting-rooms">Family hotels with connecting rooms and kitchenettes</a> '
     'covers the options that actually fit four people.</p>'),
    ("navigating-food-allergies-in-japan-with-kids-a-guide",
     "eating-out-in-japan-with-food-allergies",
     '<p><strong>What this looks like in practice:</strong> '
     '<a href="/eating-out-in-japan-with-food-allergies">how families actually manage food allergies in '
     'Japanese restaurants</a> walks through ordering, chains and the dashi problem.</p>'),
    ("kid-friendly-japanese-meals-navigating-picky-eaters",
     "eating-out-in-japan-with-food-allergies",
     '<p><strong>Allergies as well as picky eating?</strong> See '
     '<a href="/eating-out-in-japan-with-food-allergies">eating out in Japan with food allergies</a>.</p>'),
]


def _inject_context_links() -> int:
    """収益ページ/コンパニオン記事への文脈リンクを冪等に注入する。

    既にそのページへリンクしていれば触らない。挿入位置は related ブロックの直前
    （無ければ末尾開示、それも無ければ </article> の直前）。
    """
    done = 0
    for src, target, html in _CONTEXT_LINKS:
        path = SITE_DIR / (src + ".html")
        if not path.exists() or not (SITE_DIR / (target + ".html")).exists():
            continue
        page = path.read_text(encoding="utf-8")
        if f'href="/{target}"' in page:      # 既にリンク済み（冪等）
            continue
        for anchor in ('<section class="related">', '<div class="disc bottom"', "</article>"):
            if anchor in page:
                page = page.replace(anchor, html + anchor, 1)
                path.write_text(page, encoding="utf-8")
                done += 1
                log.info("seo_fixups: 文脈リンク注入 %s → %s", src, target)
                break
        else:
            log.info("seo_fixups: 挿入位置が見つからない %s", src)
    return done


def _normalize_urls() -> int:
    """docs/ 配下の自サイトURLを拡張子なしへ正規化する（冪等・2026-09-06）。

    Cloudflare Pages は /x.html を /x へ 308 で正規化する。生成側は linker.page_url を
    使うようにしたが、過去に生成済みのページや本文中の内部リンクには .html が残る。
    ここで一括して寄せることで「canonicalがリダイレクトされるURL」「内部リンクが毎回
    1ホップ余分に踏む」状態を消す。ci_assert が再発をfail-closedで見張る。
    """
    fixed = 0
    for path in sorted(SITE_DIR.rglob("*.html")):
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        new = _linker.normalize_urls(html)
        if new != html:
            path.write_text(new, encoding="utf-8")
            fixed += 1
    if fixed:
        log.info("seo_fixups: 拡張子なしURLへ正規化 %d ページ", fixed)
    return fixed


def run() -> dict:
    r = _build_redirects()
    c = _consolidate_canonicals()
    h = _enrich_hubs()
    s = _fix_sitemap()
    t = _inject_tool_links()
    x = _inject_context_links()
    u = _normalize_urls()     # 最後に置く: 上の各処理が .html を書いても必ず寄せ切る
    log.info("seo_fixups完了: _redirects=%d, canonical統合=%d, ハブ加筆=%d, sitemap修正=%d, 文脈リンク=%d, URL正規化=%d",
             r, c, h, s, x, u)
    return {"redirects": r, "canonicals": c, "hubs": h, "sitemap": s,
            "tool_links": t, "context_links": x, "normalized": u}


def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("seo_fixups失敗: %s", e)


if __name__ == "__main__":
    main()
