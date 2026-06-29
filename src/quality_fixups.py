"""読者目線の品質仕上げ（冪等・LLM不要）。公開済みdocsに対し、外部監査で出た重大3点を後段で自動修正する。

対応する指摘（読者目線クオリティ監査 2026-06-29）:
  #1 マネーページに“固有名詞”が無い → 実在の宿/プランを名指しした「Our specific picks」表を注入（収益直結）。
  #3 アレルギー記事に“伝える道具”が無い → 日本語フレーズ＋印刷用アレルギーカードを記事内に注入し、
     さらに単体の印刷用ツールページ docs/tools/allergy-card.html を生成（リードマグネット/被引用資産にもなる）。
  #5 テーマと無関係な定型バレットのにじみ → 交通/ベビー以外の記事から汎用バレット(stroller/nursing)を除去。

設計の流儀は src/seo_fixups.py と同じ：
  * LLM不要・外部依存ゼロ。daily実行のたびに後段で冪等に再適用（regen/rebuildで本文が作り直されても戻る）。
  * 固有名詞は捏造しない。実在が確認できたもののみ記載し、容量/価格/部屋タイプは「公式で確認」と明記。
  * アフィリンクは Booking(=Travelpayoutsスクリプトが自動アフィリ化) / Klook。rel="sponsored nofollow noopener"。

実行: `python -m src.quality_fixups`（daily.yml / extras.yml の task=quality_fixups から）。
"""
from __future__ import annotations
import datetime
import re
from .util import SITE_DIR, load_settings, log

# ============================================================
# #1 マネーページに“固有名詞”を入れる（実在の宿/プランを名指し）
# ============================================================
# Booking.com 検索リンクは tpembars.com(Travelpayouts marker 544191) が自動アフィリ化する。
def _bk(name: str) -> str:
    q = name.replace(" ", "+")
    return ("https://www.booking.com/searchresults.html?ss=" + q)

_KLOOK_EXPERIENCES = ("https://affiliate.klook.com/redirect?aid=125283&aff_adid=1314337"
                      "&k_site=https%3A%2F%2Fwww.klook.com%2Fen-US%2Fdestination%2Fco1012-japan%2F")
_KLOOK_ESIM = ("https://affiliate.klook.com/redirect?aid=125283&aff_adid=1314337"
               "&k_site=https%3A%2F%2Fwww.klook.com%2Fen-US%2Factivity%2F"
               "109393-japan-esim-high-speed-internet-qr-code-voucher%2F")

_SPONSORED = 'rel="sponsored nofollow noopener" target="_blank"'
_NOFOLLOW = 'rel="nofollow noopener" target="_blank"'

# ---- best-family-hotels-tokyo-connecting-rooms ----
_HOTELS_PICKS = (
    '<section id="specific-picks" class="specific-picks" style="margin:1.6em 0;border:1px solid #ffe0ee;'
    'border-radius:14px;padding:4px 18px 8px;background:#fffafc">'
    '<h2>Our specific picks: real family hotels to shortlist</h2>'
    '<p>The table above compares <em>types</em> of stay. Here are real, named properties parents actually book for '
    'these needs, with what makes each one good for kids. Room types, capacity and prices change &mdash; '
    'always confirm on the official site or booking page before you book (as of 2026).</p>'
    '<table><thead><tr><th>Hotel</th><th>Area</th><th>Why it works for families</th><th>Check it</th></tr></thead>'
    '<tbody>'
    '<tr><td><strong>MIMARU SUITES Tokyo Asakusa</strong></td><td>Asakusa</td>'
    '<td>Apartment hotel where every room has 2+ bedrooms, a kitchen and a washing machine; sleeps up to ~6. '
    'Great for picky eaters and laundry on longer trips.</td>'
    '<td><a href="' + _bk("MIMARU SUITES Tokyo Asakusa") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '<tr><td><strong>MIMARU Tokyo Ikebukuro</strong></td><td>Ikebukuro</td>'
    '<td>Offers connecting rooms (two adjoining rooms with a door) plus kitchen and dining &mdash; parents get some '
    'privacy while kids settle. Good transport hub for day trips.</td>'
    '<td><a href="' + _bk("MIMARU Tokyo Ikebukuro") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '<tr><td><strong>MIMARU Tokyo Station East</strong></td><td>Near Tokyo Station</td>'
    '<td>Connecting-room options and a kitchen, steps from Tokyo Station &mdash; the easiest base for Shinkansen '
    'day trips with kids and luggage.</td>'
    '<td><a href="' + _bk("MIMARU Tokyo Station East") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '<tr><td><strong>Disney Ambassador Hotel</strong></td><td>Tokyo Disney Resort</td>'
    '<td>Official Disney hotel. The Family Room sleeps up to 6 (two sets of twin beds, ~97 m&sup2;), plus easy '
    'park access &mdash; ideal if Disney is the centre of your trip.</td>'
    '<td><a href="https://www.tokyodisneyresort.jp/en/hotel/dah/room/detail/family/" ' + _NOFOLLOW + '>Official site</a></td></tr>'
    '<tr><td><strong>Tokyo Disneyland Hotel</strong></td><td>Tokyo Disney Resort</td>'
    '<td>Official Disney hotel right by the park gates. The Family Room (Park View) sleeps up to 5 (~93 m&sup2;) '
    '&mdash; handy for multi-generation trips.</td>'
    '<td><a href="https://www.tokyodisneyresort.jp/en/hotel/tdh/room/detail/stnd_family_a/" ' + _NOFOLLOW + '>Official site</a></td></tr>'
    '</tbody></table>'
    '<p style="font-size:.85rem;color:#6b7280">Disney official hotels are booked on the Tokyo Disney Resort site, not '
    'general booking sites. For the MIMARU apartment hotels, the link opens a live search so you can compare current '
    'rates and dates. We are not affiliated with these hotels; we recommend them on merit and earn a small commission '
    'only on qualifying bookings, at no extra cost to you.</p>'
    '</section>'
)

# ---- japan-esim-for-families-compared ----
_ESIM_PICKS = (
    '<section id="specific-picks" class="specific-picks" style="margin:1.6em 0;border:1px solid #ffe0ee;'
    'border-radius:14px;padding:4px 18px 8px;background:#fffafc">'
    '<h2>Our specific picks: named eSIMs families use</h2>'
    '<p>Instead of guessing, here are real eSIM options parents use in Japan. Data allowances, validity and prices '
    'change often &mdash; confirm the current plan on the provider&rsquo;s site before buying (as of 2026).</p>'
    '<table><thead><tr><th>eSIM</th><th>Best for</th><th>Why families pick it</th><th>Check it</th></tr></thead>'
    '<tbody>'
    '<tr><td><strong>Klook Japan eSIM (Softbank 5G / DOCOMO)</strong></td><td>Most families</td>'
    '<td>Large daily-data or fixed-GB options on major Japanese networks, QR-code setup before you fly, and tethering '
    'so one parent&rsquo;s phone can share data with the family&rsquo;s other devices. Easy for non-techy parents.</td>'
    '<td><a href="' + _KLOOK_ESIM + '" ' + _SPONSORED + '>See plans &amp; price</a></td></tr>'
    '<tr><td><strong>Ubigi</strong></td><td>Frequent travellers</td>'
    '<td>Well-known eSIM app with flexible Japan data packs and easy top-ups in-app &mdash; a common alternative worth '
    'comparing on price for your trip length.</td>'
    '<td><a href="https://cellulardata.ubigi.com/" ' + _NOFOLLOW + '>Official site</a></td></tr>'
    '<tr><td><strong>Airalo</strong></td><td>Light data users</td>'
    '<td>Popular budget eSIM marketplace with small Japan data packs &mdash; fine if you mostly need maps and '
    'translation rather than streaming kids&rsquo; videos.</td>'
    '<td><a href="https://www.airalo.com/japan-esim" ' + _NOFOLLOW + '>Official site</a></td></tr>'
    '</tbody></table>'
    '<p style="font-size:.85rem;color:#6b7280">Rule of thumb: for a 1&ndash;2 week family trip with maps, translation '
    'and the occasional kids&rsquo; video, pick a plan with tethering and a generous daily allowance. We earn a small '
    'commission only on qualifying purchases, at no extra cost to you.</p>'
    '</section>'
)

# ---- tokyo-disneyland-vs-disneysea-young-kids ----
_DISNEY_PICKS = (
    '<section id="specific-picks" class="specific-picks" style="margin:1.6em 0;border:1px solid #ffe0ee;'
    'border-radius:14px;padding:4px 18px 8px;background:#fffafc">'
    '<h2>Named rides &amp; areas for little kids (so you can plan)</h2>'
    '<p>Both parks rent strollers at the gate and have baby centres with nursing and changing rooms. Height '
    'requirements and ride availability change &mdash; confirm current details on the official Tokyo Disney Resort '
    'site before you go (as of 2026).</p>'
    '<table><thead><tr><th>Park</th><th>Gentle rides toddlers usually love</th><th>Best for</th></tr></thead>'
    '<tbody>'
    '<tr><td><strong>Tokyo Disneyland</strong></td>'
    '<td>&ldquo;it&rsquo;s a small world&rdquo;, Pooh&rsquo;s Hunny Hunt, Western River Railroad, Castle Carrousel, '
    'Dumbo, Omnibus, Baymax Happy Ride &mdash; lots of no/low height-limit rides.</td>'
    '<td>Toddlers and under-5s; classic characters and parades.</td></tr>'
    '<tr><td><strong>Tokyo DisneySea</strong></td>'
    '<td>Aquatopia, Caravan Carousel, DisneySea Transit Steamer Line, Jasmine&rsquo;s Flying Carpets, plus the newer '
    'Fantasy Springs area (Frozen, Tangled, Peter Pan).</td>'
    '<td>Slightly older kids (5+) and families who want newer themed areas; some big rides have height limits.</td></tr>'
    '</tbody></table>'
    '<p>Short on time? Pre-book park tickets so you skip the queue at the gate with tired kids: '
    '<a href="' + _KLOOK_EXPERIENCES + '" ' + _SPONSORED + '><strong>Check family tickets &amp; experiences on Klook &rarr;</strong></a></p>'
    '<p style="font-size:.85rem;color:#6b7280">For under-5s, Disneyland generally has more rides with no height '
    'requirement; DisneySea suits families with a wider age range. We earn a small commission only on qualifying '
    'purchases, at no extra cost to you.</p>'
    '</section>'
)

_MONEY_INJECT = {
    "best-family-hotels-tokyo-connecting-rooms": _HOTELS_PICKS,
    "japan-esim-for-families-compared": _ESIM_PICKS,
    "tokyo-disneyland-vs-disneysea-young-kids": _DISNEY_PICKS,
}


def _inject_money_picks() -> int:
    done = 0
    for slug, block in _MONEY_INJECT.items():
        path = SITE_DIR / f"{slug}.html"
        if not path.exists():
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'id="specific-picks"' in html:  # 冪等
            continue
        # 比較表の直後に差し込む（無ければ最初の<h2>の直前、さらに無ければ</article>直前）
        m = re.search(r"</table>", html)
        if m:
            at = m.end()
            new = html[:at] + block + html[at:]
        elif "<h2" in html:
            at = html.find("<h2")
            new = html[:at] + block + html[at:]
        elif "</article>" in html:
            new = html.replace("</article>", block + "</article>", 1)
        else:
            continue
        if new != html:
            path.write_text(new, encoding="utf-8")
            done += 1
            log.info("quality_fixups: 固有名詞ピック注入 %s", slug)
    return done


# ============================================================
# #3 アレルギー記事に“伝える道具”（日本語フレーズ＋印刷カード）
# ============================================================
ALLERGY_SLUG = "navigating-food-allergies-in-japan-with-kids-a-guide"
ALLERGY_TOOL_REL = "tools/allergy-card.html"

# 記事内に差し込む実用ブロック（フレーズ＋カードへの導線）。
_ALLERGY_INLINE = (
    '<section id="allergy-card" class="allergy-tools" style="margin:1.8em 0;border:1px solid #ffe0ee;'
    'border-radius:14px;padding:6px 18px 10px;background:#fffafc">'
    '<h2>The tools you actually need: Japanese allergy phrases &amp; a printable card</h2>'
    '<p>Knowing which chains are allergy-aware helps, but what keeps your child safe at the table is being able to '
    '<em>communicate</em>. Show the phrases below on your phone, or carry a printed card. Japanese reads top-down here '
    'so staff can read it directly.</p>'
    '<table><thead><tr><th>What you want to say (English)</th><th>Show this (Japanese)</th></tr></thead><tbody>'
    '<tr><td>My child has food allergies.</td><td lang="ja">この子は食物アレルギーがあります。</td></tr>'
    '<tr><td>It is a severe allergy. Even a small amount is dangerous.</td><td lang="ja">重いアレルギーです。少しでも入ると危険です。</td></tr>'
    '<tr><td>Does this dish contain ___ ?</td><td lang="ja">この料理に ___ は入っていますか？</td></tr>'
    '<tr><td>Could you make it without ___ ?</td><td lang="ja">___ を抜いてもらえますか？</td></tr>'
    '<tr><td>Please be careful about cross-contamination.</td><td lang="ja">調理のときに他の食材が混ざらないよう注意してください。</td></tr>'
    '<tr><td>We have an adrenaline auto-injector (EpiPen).</td><td lang="ja">エピペン（アドレナリン注射）を持っています。</td></tr>'
    '<tr><td>Emergency: please call an ambulance (119).</td><td lang="ja">緊急です。119番に電話してください（救急車）。</td></tr>'
    '</tbody></table>'
    '<p><strong>Common allergens to write on your card</strong> (English &rarr; Japanese): '
    'egg 卵 (tamago) · milk 乳・牛乳 (gyūnyū) · wheat 小麦 (komugi) · '
    'buckwheat そば (soba) · peanut 落花生・ピーナッツ · '
    'shrimp えび (ebi) · crab かに (kani) · walnut くるみ (kurumi) · '
    'soy 大豆 (daizu) · sesame ごま (goma) · fish 魚 (sakana) · '
    'cashew カシューナッツ · kiwi キウイ · peach もも (momo) · '
    'apple りんご (ringo) · gelatin ゼラチン.</p>'
    '<p style="margin:.4em 0 .2em"><a class="readmore" href="/' + ALLERGY_TOOL_REL + '" target="_blank">'
    '→ Open the free printable allergy card (fill in your child&rsquo;s allergens, then print or save)</a></p>'
    '<p style="font-size:.82rem;color:#6b7280">Japanese phrases are provided for communication only and are not medical '
    'advice. Japan&rsquo;s labelling list changes (walnut became mandatory in recent years) &mdash; confirm the current '
    'mandatory and recommended allergens on the Consumer Affairs Agency site, and always speak with restaurant staff '
    'about your child&rsquo;s specific needs.</p>'
    '</section>'
)


def _inject_allergy_inline() -> int:
    path = SITE_DIR / f"{ALLERGY_SLUG}.html"
    if not path.exists():
        return 0
    try:
        html = path.read_text(encoding="utf-8")
    except Exception:
        return 0
    if 'id="allergy-card"' in html:  # 冪等
        return 0
    # FAQの直前に差し込む（無ければ Related の前、さらに無ければ </article> 直前）
    if "<h2>FAQ</h2>" in html:
        new = html.replace("<h2>FAQ</h2>", _ALLERGY_INLINE + "<h2>FAQ</h2>", 1)
    elif '<section class="related">' in html:
        new = html.replace('<section class="related">', _ALLERGY_INLINE + '<section class="related">', 1)
    elif "</article>" in html:
        new = html.replace("</article>", _ALLERGY_INLINE + "</article>", 1)
    else:
        return 0
    if new != html:
        path.write_text(new, encoding="utf-8")
        log.info("quality_fixups: アレルギー伝達ブロック注入 %s", ALLERGY_SLUG)
        return 1
    return 0


# 単体の印刷用ツールページ（リードマグネット/被引用資産にもなる）。
def _allergy_tool_html() -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Printable Japanese Allergy Card for Kids (free) | littletabi</title>'
        '<meta name="description" content="Free printable allergy card in Japanese for children travelling in Japan. '
        'Fill in your child\'s allergens, add key phrases, then print or save.">'
        '<link rel="canonical" href="https://littletabi.com/' + ALLERGY_TOOL_REL + '">'
        '<style>'
        ':root{--ink:#1f2937;--muted:#6b7280;--accent:#b8005a;--soft:#fff0f6;--line:#ececf1}'
        'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;'
        'color:var(--ink);background:#fffdfb;margin:0;line-height:1.6}'
        '.wrap{max-width:720px;margin:0 auto;padding:22px 18px}'
        'a{color:var(--accent)}h1{font-size:1.5rem;margin:.2em 0}'
        '.card{border:2px solid var(--accent);border-radius:14px;padding:18px 20px;margin:18px 0;background:#fff}'
        '.card h2{margin:.1em 0 .3em;font-size:1.15rem;color:var(--accent)}'
        '.row{margin:.5em 0;padding-bottom:.5em;border-bottom:1px dashed var(--line)}'
        '.ja{font-size:1.15rem}.en{color:var(--muted);font-size:.9rem}'
        '.fill{display:inline-block;min-width:160px;border-bottom:1.5px solid var(--ink);height:1.2em}'
        '.btn{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:10px;'
        'padding:11px 20px;font-weight:700;cursor:pointer;text-decoration:none;font-size:1rem}'
        '.note{font-size:.82rem;color:var(--muted)}'
        '.brand{font-weight:800;color:var(--ink);text-decoration:none}.brand b{color:var(--accent)}'
        '@media print{.noprint{display:none}body{background:#fff}.card{box-shadow:none}}'
        '</style></head><body><div class="wrap">'
        '<p class="noprint"><a class="brand" href="/index.html">little<b>tabi</b></a></p>'
        '<h1>Printable Japanese allergy card for kids</h1>'
        '<p class="noprint">Write your child&rsquo;s allergens in the blanks, then <button class="btn" '
        'onclick="window.print()">Print / Save as PDF</button>. Show this to restaurant staff in Japan.</p>'
        '<div class="card">'
        '<h2>アレルギーカード &middot; Allergy Card</h2>'
        '<div class="row"><div class="ja">この子は次の食物アレルギーがあります。</div>'
        '<div class="en">This child is allergic to the following foods:</div>'
        '<div style="margin:.4em 0"><span class="fill"></span> <span class="fill"></span> <span class="fill"></span></div></div>'
        '<div class="row"><div class="ja">重いアレルギーです。少しでも入ると危険です。</div>'
        '<div class="en">It is a severe allergy. Even a trace is dangerous.</div></div>'
        '<div class="row"><div class="ja">上記の食材を使わずに調理してもらえますか？接触（コンタミ）にも注意してください。</div>'
        '<div class="en">Could you prepare food without these, and avoid cross-contamination?</div></div>'
        '<div class="row"><div class="ja">緊急時は119番（救急車）に電話してください。エピペンを持っています。</div>'
        '<div class="en">In an emergency, please call 119 (ambulance). We carry an EpiPen.</div></div>'
        '<div class="row"><div class="en"><strong>Child&rsquo;s name / age:</strong> <span class="fill"></span> '
        '&nbsp; <strong>Carer&rsquo;s phone:</strong> <span class="fill"></span></div></div>'
        '</div>'
        '<p class="note"><strong>Allergen words to copy in</strong> (EN &rarr; JA): '
        'egg 卵 · milk 牛乳 · wheat 小麦 · buckwheat そば · '
        'peanut 落花生 · shrimp えび · crab かに · walnut くるみ · '
        'soy 大豆 · sesame ごま · fish 魚 · cashew カシューナッツ · '
        'kiwi キウイ · peach もも · apple りんご · gelatin ゼラチン.</p>'
        '<p class="note">Provided for communication only; not medical advice. Japan&rsquo;s mandatory allergen list '
        'changes &mdash; confirm the current list on the Consumer Affairs Agency site and always confirm with staff. '
        'From <a href="/' + ALLERGY_SLUG + '.html">littletabi.com</a>.</p>'
        '<p class="noprint"><a href="/' + ALLERGY_SLUG + '.html">&larr; Back to the food-allergy guide</a></p>'
        '</div></body></html>'
    )


def _build_allergy_tool() -> int:
    path = SITE_DIR / ALLERGY_TOOL_REL
    html = _allergy_tool_html()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 既存と同一なら書かない（無駄コミット回避）
        if path.exists() and path.read_text(encoding="utf-8") == html:
            return 0
        path.write_text(html, encoding="utf-8")
        log.info("quality_fixups: 印刷用アレルギーカード生成 %s", ALLERGY_TOOL_REL)
        return 1
    except Exception as e:
        log.error("quality_fixups: allergyツール生成失敗: %s", e)
        return 0


# ============================================================
# #5 テーマと無関係な定型バレットを除去
# ============================================================
# 交通/ベビー系の記事では妥当なので除去しない（slugで判定）。
_BULLET_KEEP_SLUG = ("transport", "stroller", "getting-around", "public-transport",
                     "baby", "diaper", "carrier", "car-seat", "rail", "shinkansen", "accommodation")
# 除去対象の汎用バレット（前段監査で実際ににじみが確認された定型文）。
_OFFTOPIC_BULLET_PATTpat = [
    r"<li>[^<]*stroller-friendly transportation[^<]*</li>",
    r"<li>[^<]*nursing and changing facilities[^<]*</li>",
]


def _strip_offtopic_bullets() -> int:
    fixed = 0
    for path in SITE_DIR.glob("*.html"):
        slug = path.stem
        if any(k in slug for k in _BULLET_KEEP_SLUG):
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        new = html
        for pat in _OFFTOPIC_BULLET_PATTpat:
            new = re.sub(pat, "", new, flags=re.IGNORECASE)
        if new != html:
            path.write_text(new, encoding="utf-8")
            fixed += 1
            log.info("quality_fixups: 無関係バレット除去 %s", slug)
    return fixed


# ============================================================
# sitemap に印刷ツールページを収録
# ============================================================
def _ensure_sitemap_tool() -> int:
    sm = SITE_DIR / "sitemap.xml"
    if not sm.exists():
        return 0
    try:
        xml = sm.read_text(encoding="utf-8")
    except Exception:
        return 0
    try:
        base = (load_settings().get("site", {}) or {}).get("base_url") or "https://littletabi.com"
    except Exception:
        base = "https://littletabi.com"
    base = base.rstrip("/")
    loc = f"{base}/{ALLERGY_TOOL_REL}"
    if f"/{ALLERGY_TOOL_REL}<" in xml or loc in xml:
        return 0
    today = datetime.date.today().isoformat()
    block = (f"<url>\n<loc>{loc}</loc>\n<lastmod>{today}</lastmod>\n"
             "<changefreq>monthly</changefreq>\n<priority>0.6</priority>\n</url>\n")
    if "</urlset>" in xml:
        xml = xml.replace("</urlset>", block + "</urlset>", 1)
        sm.write_text(xml, encoding="utf-8")
        log.info("quality_fixups: sitemapにツールページ追加")
        return 1
    return 0


def run() -> dict:
    m = _inject_money_picks()
    t = _build_allergy_tool()
    a = _inject_allergy_inline()
    b = _strip_offtopic_bullets()
    s = _ensure_sitemap_tool()
    log.info("quality_fixups完了: 固有名詞=%d, allergyツール=%d, allergy注入=%d, バレット除去=%d, sitemap=%d",
             m, t, a, b, s)
    return {"money_picks": m, "allergy_tool": t, "allergy_inline": a, "bullets": b, "sitemap": s}


def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("quality_fixups失敗: %s", e)


if __name__ == "__main__":
    main()
