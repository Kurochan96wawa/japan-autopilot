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

#4（dataviz前面＋透明性）・#2（新幹線の家族予約手順）も同ファイルで後段冪等適用する。

実行: `python -m src.quality_fixups`（daily.yml / extras.yml の task=quality_fixups から）。
"""
from __future__ import annotations
import datetime
import pathlib
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
_KLOOK_TDR = ("https://affiliate.klook.com/redirect?aid=125283&aff_adid=1314337"
              "&k_site=https%3A%2F%2Fwww.klook.com%2Fen-US%2Factivity%2F695-tokyo-disney-resort-1-day-pass-tokyo%2F")
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
    '<td>Connecting-room options and a kitchen, about 15 min on foot from Tokyo Station (3 min from Hatchobori Station) &mdash; the easiest base for Shinkansen '
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
    '<tr><td><strong>Hilton Tokyo Bay</strong></td><td>Maihama (Disney)</td>'
    '<td>Tokyo Disney Resort official partner hotel on the Maihama waterfront. The &ldquo;Happy Magic&rdquo; family '
    'rooms have bunk beds kids love, with a park shuttle at the door.</td>'
    '<td><a href="' + _bk("Hilton Tokyo Bay Maihama") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '<tr><td><strong>Grand Nikko Tokyo Bay Maihama</strong></td><td>Maihama (Disney)</td>'
    '<td>Official Tokyo Disney Resort hotel with Japanese- and Western-style family rooms and a Disney Resort '
    'Cruiser shuttle to the parks.</td>'
    '<td><a href="' + _bk("Grand Nikko Tokyo Bay Maihama") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '<tr><td><strong>Keio Plaza Hotel Tokyo</strong></td><td>Shinjuku</td>'
    '<td>Large, well-connected Shinjuku hotel with family rooms; themed Hello Kitty rooms are a hit with younger '
    'kids (check current availability).</td>'
    '<td><a href="' + _bk("Keio Plaza Hotel Tokyo Shinjuku") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '<tr><td><strong>Tokyu Stay Shinjuku</strong></td><td>Shinjuku</td>'
    '<td>Every room has a washer-dryer and kitchenette with flexible bedding &mdash; ideal for longer family stays '
    'and doing laundry mid-trip.</td>'
    '<td><a href="' + _bk("Tokyu Stay Shinjuku") + '" ' + _SPONSORED + '>See rates</a></td></tr>'
    '</tbody></table>'
    '<p style="margin:1em 0 .3em;font-weight:600">Planning the rest of your Tokyo trip?</p>'
    '<p style="font-size:.95rem">Families using a Tokyo hotel base often add a '
    '<a href="https://tp.media/r?marker=744378&trs=544191&p=8919&u=https%3A%2F%2Fwww.welcomepickups.com%2Ftokyo%2F&campaign_id=627" ' + _SPONSORED + '>private airport transfer</a> '
    '(door-to-hotel, child seats on request), a '
    '<a href="https://tp.media/r?marker=744378&trs=544191&p=5867&u=https%3A%2F%2Fradicalstorage.com%2Fluggage-storage%2Ftokyo&campaign_id=209" ' + _SPONSORED + '>luggage-storage drop</a> '
    'for the gap between check-out and a late flight, and '
    '<a href="' + _KLOOK_EXPERIENCES + '" ' + _SPONSORED + '>kid-friendly activities &amp; tickets</a>.</p>'
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
    '<a href="' + _KLOOK_TDR + '" ' + _SPONSORED + '><strong>Check Tokyo Disney 1-Day tickets on Klook &rarr;</strong></a></p>'
    '<p style="font-size:.85rem;color:#6b7280">For under-5s, Disneyland generally has more rides with no height '
    'requirement; DisneySea suits families with a wider age range. We earn a small commission only on qualifying '
    'purchases, at no extra cost to you.</p>'
    '</section>'
)

_ITINERARY = """<section id="specific-picks" class="specific-picks" style="margin:1.6em 0;border:1px solid #ffe0ee;border-radius:14px;padding:4px 18px 8px;background:#fffafc">
<h2>Day-by-day: a kid-paced 10-day Tokyo&ndash;Kyoto&ndash;Osaka route</h2>
<p>The sections above cover logistics; here is the actual route, matched to the Tokyo (Days 1&ndash;4), Kyoto (Days 5&ndash;7) and Osaka (Days 8&ndash;10) split at the top. It is deliberately gentle &mdash; roughly one anchor activity per day, with an indoor rainy-day backup for each. Opening days, hours and prices change and some places sell out, so confirm on each official site before you go (as of 2026). <strong>Book well ahead:</strong> the <a href="https://www.ghibli-museum.jp/en/" rel="nofollow noopener">Ghibli Museum</a>, <a href="https://www.teamlab.art/e/planets/" rel="nofollow noopener">teamLab Planets</a>, <a href="https://www.tokyodisneyresort.jp/en/index.html" rel="nofollow noopener">Tokyo Disney Resort</a> and <a href="https://www.usj.co.jp/web/en/us" rel="nofollow noopener">Universal Studios Japan</a> commonly sell out, and walk-up tickets are often unavailable.</p>
<h3>Day 1 &mdash; Tokyo: Ueno (easy arrival day)</h3>
<p><strong>Morning:</strong> Ease into the trip at <a href="https://www.tokyo-zoo.net/en/ueno/index.html" rel="nofollow noopener">Ueno Zoo</a> (giant pandas and a small children's zoo), set inside leafy Ueno Park. <strong>Afternoon:</strong> Stroll the park's ponds and playgrounds; the science and nature museum in the park is a good low-energy option. <strong>Getting around:</strong> Ueno Station is a big JR and Metro hub, and almost everything today is walkable. <strong>Kid tip:</strong> Jet-lagged toddlers fade by mid-afternoon &mdash; keep day one short and flexible. <strong>Rainy day:</strong> Move indoors to the museums clustered in the park.</p>
<h3>Day 2 &mdash; Tokyo: Odaiba &amp; Toyosu (all-weather day)</h3>
<p><strong>Morning:</strong> <a href="https://www.teamlab.art/e/planets/" rel="nofollow noopener">teamLab Planets TOKYO</a> in Toyosu &mdash; a barefoot, walk-through digital art space kids love (book a timed entry in advance). <strong>Afternoon:</strong> Hands-on science at <a href="https://www.miraikan.jst.go.jp/en/" rel="nofollow noopener">Miraikan</a> on Odaiba. <strong>Getting around:</strong> The driverless Yurikamome line to Odaiba is a thrill in itself &mdash; sit at the very front. <strong>Kid tip:</strong> teamLab involves shallow water; bring or wear shorts that roll up. <strong>Rainy day:</strong> Both venues are fully indoors, so this is your rain-insurance day.</p>
<h3>Day 3 &mdash; Tokyo: Mitaka &amp; Asakusa</h3>
<p><strong>Morning:</strong> The <a href="https://www.ghibli-museum.jp/en/" rel="nofollow noopener">Ghibli Museum, Mitaka</a> &mdash; entry is by advance-only timed ticket (no same-day sales), so lock this in first; the adjacent Inokashira Park has space to run. <strong>Afternoon:</strong> The old-Tokyo streets and historic temple of the Asakusa district. <strong>Getting around:</strong> Chuo line to Mitaka, then Metro across to Asakusa. <strong>Kid tip:</strong> The name on the Ghibli ticket must match the passport. <strong>Rainy day:</strong> Swap Asakusa for the indoor <a href="https://en.sumida-aquarium.com/" rel="nofollow noopener">Sumida Aquarium</a> at Tokyo Skytree.</p>
<h3>Day 4 &mdash; Tokyo: a Disney park</h3>
<p><strong>Morning &amp; afternoon:</strong> A full day at <a href="https://www.tokyodisneyresort.jp/en/index.html" rel="nofollow noopener">Tokyo Disney Resort</a>. With young children, Tokyo Disneyland's fantasy areas tend to suit better than DisneySea's bigger rides &mdash; pick one park and take it slow. <strong>Getting around:</strong> Take the JR line to Maihama, then the resort monorail. <strong>Kid tip:</strong> Buy dated tickets ahead and plan an afternoon break back near the gate for naps. <strong>Rainy day:</strong> The parks run rain or shine and have many indoor attractions; pack light ponchos.</p>
<h3>Day 5 &mdash; Tokyo to Kyoto (travel day)</h3>
<p><strong>Morning:</strong> Ride the Tokaido Shinkansen from Tokyo to Kyoto (about 2 hours 20 minutes). If you are travelling with the largest suitcases, reserve an oversized-baggage seat in advance at no extra charge. <strong>Afternoon:</strong> About a 20-minute walk (or short bus ride) from Kyoto Station, the <a href="https://www.kyotorailwaymuseum.jp/en/" rel="nofollow noopener">Kyoto Railway Museum</a> is a perfect post-train wind-down, with real locomotives and a hands-on play area. <strong>Getting around:</strong> Store bags in station lockers or send them ahead to your hotel by luggage courier. <strong>Kid tip:</strong> Book seats together early on busy travel dates. <strong>Rainy day:</strong> The museum is largely indoors.</p>
<h3>Day 6 &mdash; Kyoto: Umekoji</h3>
<p><strong>Morning:</strong> <a href="https://en.kyoto-aquarium.com/" rel="nofollow noopener">Kyoto Aquarium</a> (penguins and a big sea-life hall) sits inside Umekoji Park, so you can pair tanks with lawns and a playground. <strong>Afternoon:</strong> If energy allows, the Arashiyama bamboo area is a scenic, mostly-flat walk. <strong>Getting around:</strong> Umekoji is a short walk or bus from Kyoto Station; Arashiyama is an easy train ride west. <strong>Kid tip:</strong> Kyoto's buses get crowded &mdash; a stroller-friendly train route is calmer. <strong>Rainy day:</strong> Stay put at the indoor aquarium.</p>
<h3>Day 7 &mdash; Day trip to Nara</h3>
<p><strong>Morning:</strong> <a href="https://www.visitnara.jp/" rel="nofollow noopener">Nara Park</a>, where friendly wild deer roam and you can buy special crackers to feed them. <strong>Afternoon:</strong> The Great Buddha hall at <a href="https://www.todaiji.or.jp/en/" rel="nofollow noopener">Todaiji Temple</a>, a short walk across the park. <strong>Getting around:</strong> Nara is about 45 minutes from Kyoto by JR or Kintetsu train. <strong>Kid tip:</strong> Hold snacks tight &mdash; the deer are bold; teach little ones to keep hands flat. <strong>Rainy day:</strong> The temple halls are covered and the deer are out in any weather.</p>
<h3>Day 8 &mdash; Osaka: the bay</h3>
<p><strong>Morning:</strong> <a href="https://www.kaiyukan.com/" rel="nofollow noopener">Osaka Aquarium Kaiyukan</a>, one of Japan's best, built around a huge central tank with a whale shark. <strong>Afternoon:</strong> The Tempozan Harbor Village next door has a big Ferris wheel and a market for an easy lunch. <strong>Getting around:</strong> Osakako Station on the Chuo subway line is right there. <strong>Kid tip:</strong> Go early; the spiral ramp down through the tanks gets busy by midday. <strong>Rainy day:</strong> The aquarium is entirely indoors.</p>
<h3>Day 9 &mdash; Osaka: theme park or tower</h3>
<p><strong>All day:</strong> <a href="https://www.usj.co.jp/web/en/us" rel="nofollow noopener">Universal Studios Japan</a>, with Super Nintendo World and gentler areas for younger kids (buy dated tickets in advance). <strong>Toddler alternative:</strong> A calmer day at the <a href="https://www.abenoharukas-300.jp/en/" rel="nofollow noopener">Abeno Harukas</a> 300 observatory plus the wide lawns of the adjacent Tennoji Park. <strong>Getting around:</strong> USJ has its own JR station (Universal City); Abeno Harukas sits above Tennoji Station. <strong>Kid tip:</strong> Height limits apply on big USJ rides &mdash; check them before you queue. <strong>Rainy day:</strong> USJ runs in the rain; the observatory is indoors.</p>
<h3>Day 10 &mdash; Osaka: castle &amp; departure</h3>
<p><strong>Morning:</strong> <a href="https://www.osakacastle.net/" rel="nofollow noopener">Osaka Castle</a> and its large park &mdash; ninja and samurai displays inside, plenty of open space outside. <strong>Afternoon:</strong> Head to Kansai (KIX) or Itami airport with time to spare. <strong>Getting around:</strong> Osakajokoen Station rings the park; airport express trains and limousine buses leave from central Osaka. <strong>Kid tip:</strong> Leave a generous buffer for security with a stroller and bags. <strong>Rainy day:</strong> The castle keep is an indoor museum with lifts.</p>
<p class="disc" style="font-size:.85rem;color:#6b7280">The day-by-day links above go to official sites so you can confirm current prices, hours and closed days. Unlike some booking links elsewhere on this site, these official links are not affiliate links.</p>
</section>"""


_MONEY_INJECT = {
    # "best-family-hotels-tokyo-connecting-rooms": 2026-09-05 から assets/pages の手組みページに置換（_HOTELS_PICKS は不要）
    "japan-esim-for-families-compared": _ESIM_PICKS,
    "tokyo-disneyland-vs-disneysea-young-kids": _DISNEY_PICKS,
    "japan-family-itinerary-tokyo-kyoto-osaka-with-young-children": _ITINERARY,
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
        if 'id="specific-picks"' in html:  # 既存あり → 現行ブロックへ置換（更新）
            new = re.sub(r'<section id="specific-picks".*?</section>',
                         lambda _m: block, html, count=1, flags=re.S)
            if new != html:
                path.write_text(new, encoding="utf-8")
                done += 1
                log.info("quality_fixups: 固有名詞ピック更新 %s", slug)
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
        'Fill in your child&rsquo;s allergens on screen, add key phrases, then print or save.">'
        '<link rel="canonical" href="https://littletabi.com/' + ALLERGY_TOOL_REL + '">'
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebApplication","name":"Printable Japanese allergy card for kids","url":"https://littletabi.com/tools/allergy-card.html","applicationCategory":"TravelApplication","operatingSystem":"Any (web browser)","description":"A free printable card that states a child food allergy in Japanese, asks for cross-contamination to be avoided, and warns about dashi stock. Fill it in on screen and print or save as PDF.","inLanguage":["en","ja"],"isAccessibleForFree":true,"offers":{"@type":"Offer","price":"0","priceCurrency":"JPY"},"publisher":{"@type":"Organization","name":"littletabi","url":"https://littletabi.com/"}}</script>'
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
        '.fill{display:inline-block;min-width:150px;border-bottom:1.5px solid var(--ink);'
        'min-height:1.3em;padding:0 4px;outline:none}'
        '.fill:focus{background:var(--soft)}'
        '.btn{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:10px;'
        'padding:11px 20px;font-weight:700;cursor:pointer;text-decoration:none;font-size:1rem}'
        '.note{font-size:.82rem;color:var(--muted)}'
        '.dashi{background:var(--soft);border-radius:8px;padding:.5em .7em}'
        '.epipen-ctl{margin-top:.5em}'
        '.epipen-line{display:none;margin-top:.35em}'
        '#epipen:checked ~ .epipen-line{display:block}'
        '.brand{font-weight:800;color:var(--ink);text-decoration:none}.brand b{color:var(--accent)}'
        '@media print{.noprint{display:none}body{background:#fff}.card{box-shadow:none}'
        '.epipen-ctl input{display:none}}'
        '</style></head><body><div class="wrap">'
        '<p class="noprint"><a class="brand" href="/index.html">little<b>tabi</b></a></p>'
        '<h1>Printable Japanese allergy card for kids</h1>'
        '<p class="noprint">Type your child&rsquo;s details into the blanks below, tick the EpiPen box only if '
        'they carry one, then <button class="btn" onclick="window.print()">Print / Save as PDF</button>. '
        'Show this to restaurant staff in Japan.</p>'
        '<div class="card">'
        '<h2>アレルギーカード &middot; Allergy Card</h2>'
        '<div class="row"><div class="ja">この子は次の食物アレルギーがあります。</div>'
        '<div class="en">This child is allergic to the following foods:</div>'
        '<div style="margin:.4em 0"><span class="fill" contenteditable="true" role="textbox" '
        'aria-label="allergens"></span> <span class="fill" contenteditable="true"></span> '
        '<span class="fill" contenteditable="true"></span></div></div>'
        '<div class="row"><div class="ja">重いアレルギーです。少しでも入ると危険です。</div>'
        '<div class="en">It is a severe allergy. Even a trace is dangerous.</div></div>'
        '<div class="row"><div class="ja">上記の食材を使わずに調理してもらえますか？接触（コンタミ）にも注意してください。</div>'
        '<div class="en">Could you prepare food without these, and avoid cross-contamination?</div></div>'
        '<div class="row dashi"><div class="ja">※魚・甲殻類アレルギーの場合は、だし（出汁）・魚介エキスにもご注意ください。'
        '多くの和食はかつおだし（魚）を使っています。</div>'
        '<div class="en">If your child is allergic to fish or shellfish: note that dashi (Japanese soup stock) '
        'and seafood extracts are used very widely &mdash; most Japanese dishes contain bonito-fish dashi.</div></div>'
        '<div class="row"><div class="ja">緊急時は119番（救急車）に電話してください。</div>'
        '<div class="en">In an emergency, please call 119 (ambulance).</div>'
        '<div class="epipen-ctl"><input type="checkbox" id="epipen">'
        '<label for="epipen" class="noprint en"> Tick only if your child carries an EpiPen (adrenaline '
        'auto-injector) &mdash; エピペン携帯時のみチェック</label>'
        '<div class="epipen-line"><div class="ja">この子はエピペン（アドレナリン自己注射薬）を携帯しています。</div>'
        '<div class="en">This child carries an EpiPen (adrenaline auto-injector).</div></div></div></div>'
        '<div class="row"><div class="en"><strong>Child&rsquo;s name / age:</strong> '
        '<span class="fill" contenteditable="true"></span> &nbsp; '
        '<strong>Carer&rsquo;s phone:</strong> <span class="fill" contenteditable="true"></span></div></div>'
        '</div>'
        '<p class="note"><strong>Allergen words to copy in</strong> (EN &rarr; JA): '
        'egg 卵 · milk 乳（牛乳・チーズ・バター・乳製品すべて） · wheat 小麦 · buckwheat そば · '
        'peanut 落花生 · shrimp えび · crab かに · walnut くるみ · '
        'soy 大豆 · sesame ごま · fish 魚 · cashew カシューナッツ · '
        'kiwi キウイ · peach もも · apple りんご · gelatin ゼラチン.</p>'
        '<p class="note">Provided for communication only; not medical advice. Japan&rsquo;s mandatory allergen list '
        'changes &mdash; confirm the current list on the Consumer Affairs Agency site and always confirm with staff. '
        'From <a href="/' + ALLERGY_SLUG + '.html">littletabi.com</a>.</p>'
        '<p class="noprint"><a href="/' + ALLERGY_SLUG + '.html">&larr; Back to the food-allergy guide</a></p>'
        '<div class="card"><p style="margin:0"><b><a href="/eating-out-in-japan-with-food-allergies.html">How families actually manage food allergies in Japanese restaurants &rarr;</a></b></p></div><div class="widget" id="lead-form-widget" style="background:#fff0f6;border-color:#ffe0ee"><h4>Free: Japan-with-kids checklist</h4><p style="color:#6b7280;font-size:.9rem;margin:.2em 0 .7em">A pre-departure checklist + a 7-day Tokyo itinerary (PDF). No spam — unsubscribe anytime.</p><form action="https://app.kit.com/forms/9651205/subscriptions" method="post" class="seva-form formkit-form" data-sv-form="9651205" data-uid="f5350a8d30" data-format="inline" data-version="5" style="display:flex;flex-direction:column;gap:8px"><input type="email" name="email_address" required="" placeholder="Your email" style="width:100%;border:1px solid #ececf1;border-radius:10px;padding:9px 11px;font:inherit;margin:0"><button type="submit" data-element="submit" style="background:#b8005a;color:#fff;border:0;border-radius:10px;padding:9px 12px;font-weight:700;cursor:pointer">Send me the checklist</button></form></div><script async="" src="https://f.convertkit.com/ckjs/ck.5.js"></script>'
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


# ============================================================
# #4 独自図(dataviz)を前面へ＋冒頭に正直な透明性ストリップ
# ============================================================
# 監査#4: ストック写真クレジットが冒頭・独自図が下＝「行った人」感が無く信頼に天井。
# 対処: ①datavizの独自図を byline 直後（写真より前）へ前出し ②byline直後に正直な透明性ノート。
# 架空の人間著者は作らない方針は維持し、"AI生成・公式照合・未訪問"を正直に明記する。
_TRUST_STRIP_RE = re.compile(r'<p id="trust-strip".*?</p>', re.S)


def _trust_strip_html(stay: bool) -> str:
    extra = (' We don&rsquo;t take paid or sponsored stays &mdash; we recommend places on merit.'
             if stay else '')
    return ('<p id="trust-strip" class="trust-strip" style="margin:.4em 0 1.1em;padding:.55em .85em;'
            'background:#fff0f6;border:1px solid #ffe0ee;border-radius:10px;font-size:.86rem;color:#6b7280">'
            'AI-generated guide, checked with an automated quality process. '
            'Details are linked to official sources where possible &mdash; always confirm before you travel.'
            + extra +
            ' <a href="/how-we-make-guides.html">How we make these guides &rarr;</a></p>')

_BYLINE_RE = re.compile(r'<p[^>]*class="byline"[^>]*>.*?</p>', re.S)
_DV_FIG_RE = re.compile(r'<figure[^>]*class="[^"]*dataviz[^"]*"[^>]*>.*?</figure>', re.S)
_DV_FIG_SVG_RE = re.compile(r'<figure[^>]*>(?:(?!</figure>).)*?<svg.*?</figure>', re.S)
_PHOTO_FIG_RE = re.compile(r'<figure[^>]*>(?:(?!</figure>).)*?Pexels.*?</figure>', re.S)


def _hoist_dataviz(html: str):
    """独自図(dataviz)をストック写真より前（byline直後）へ移動。冪等（既に前なら何もしない）。"""
    mb = _BYLINE_RE.search(html)
    if not mb:
        return html, False
    mdv = _DV_FIG_RE.search(html) or _DV_FIG_SVG_RE.search(html)
    mph = _PHOTO_FIG_RE.search(html)
    if not mdv or not mph:
        return html, False
    if mdv.start() < mph.start():  # 既に写真より前＝冪等
        return html, False
    fig = mdv.group(0)
    html = html[:mdv.start()] + html[mdv.end():]   # 元位置から除去
    at = mb.end()                                   # byline直後へ挿入（bylineは両者より前なので位置不変）
    return html[:at] + fig + html[at:], True


def _inject_trust_strip(html: str):
    """byline直後に正直な透明性ストリップを挿入/更新。冪等（既存も新文言へ置換）。"""
    stay = any(k in html for k in ("best-family-hotels", "connecting-rooms",
                                   "kitchenettes", "family-hotels", "where-to-stay"))
    strip = _trust_strip_html(stay)
    if 'id="trust-strip"' in html:
        new = _TRUST_STRIP_RE.sub(lambda _m: strip, html, count=1)
        return new, (new != html)
    mb = _BYLINE_RE.search(html)
    if not mb:
        return html, False
    at = mb.end()
    return html[:at] + strip + html[at:], True

def _front_trust_and_dataviz() -> dict:
    hoisted = 0
    stripped = 0
    for path in SITE_DIR.glob("*.html"):
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        orig = html
        html, h = _hoist_dataviz(html)
        html, s = _inject_trust_strip(html)
        if html != orig:
            path.write_text(html, encoding="utf-8")
            hoisted += 1 if h else 0
            stripped += 1 if s else 0
            log.info("quality_fixups: #4 %s (dataviz前面=%s 透明性=%s)", path.stem, h, s)
    return {"dataviz_hoisted": hoisted, "trust_strip": stripped}


# ============================================================
# #2 難所の手前で止まらない：新幹線の家族予約を手順化
# ============================================================
# 監査#2: 「Travel to Kyoto via the Shinkansen…about 2 hours」で終わり、予約方法・大型荷物・
# ベビーカー・家族の概算費用が空白。子連れ最大のロジを手順で埋める。
# 事実は2026-06に裏取り済（smartEX/EKINET予約、大型荷物160-250cmは事前予約無料・未予約¥1,000で
# 最後列後ろに収納、6歳未満は膝上で2名まで無料・6-11歳は半額）。価格は概算＋「公式で確認」。
_SHINKANSEN_STEPS = (
    '<section id="shinkansen-steps" class="howto" style="margin:1.8em 0;border:1px solid #ffe0ee;'
    'border-radius:14px;padding:6px 18px 10px;background:#fffafc">'
    '<h2>Booking the Shinkansen with a family: a step-by-step</h2>'
    '<p>&ldquo;Take the bullet train&rdquo; is the easy part. Here is how families actually book it with little kids, '
    'big suitcases and a stroller. Fares and rules change &mdash; confirm on the official sites before you travel '
    '(as of 2026).</p>'
    '<ol>'
    '<li><strong>Reserve seats &mdash; don&rsquo;t wing it with kids.</strong> Book reserved seats in English on the '
    'official apps: <a href="https://smart-ex.jp/en/" rel="nofollow noopener" target="_blank">smartEX</a> for the '
    'Tokaido/Sanyo/Kyushu Shinkansen (Tokyo&ndash;Kyoto&ndash;Osaka&ndash;Hiroshima) or '
    '<a href="https://www.eki-net.com/en/" rel="nofollow noopener" target="_blank">EKINET</a> for JR East. You can '
    'also book at a JR ticket office (Midori-no-madoguchi) or a green ticket machine. Reserve a few days ahead in '
    'peak seasons.</li>'
    '<li><strong>Book the oversized-baggage seats for big suitcases.</strong> On the Tokaido/Sanyo/Kyushu Shinkansen, '
    'a bag whose height&nbsp;+&nbsp;width&nbsp;+&nbsp;depth totals 160&ndash;250&nbsp;cm needs a free '
    '&ldquo;oversized baggage&rdquo; seat reservation &mdash; the last-row seats, with a storage area behind them. '
    'Reserving it costs nothing extra; turning up without one is a &yen;1,000 surcharge on board. Bags over '
    '250&nbsp;cm aren&rsquo;t allowed.</li>'
    '<li><strong>Strollers: book the last row.</strong> Fold the stroller and store it in the space behind the rear '
    'seats, so reserve the last row of the car. A folded stroller doesn&rsquo;t need its own reservation.</li>'
    '<li><strong>Know the kids&rsquo; fares.</strong> Up to two children under 6 ride free per paying adult if they '
    'sit on your lap; if a young child takes their own seat, you pay a child fare. Children aged 6&ndash;11 pay half '
    'the adult fare with their own reserved seat.</li>'
    '<li><strong>Budget roughly.</strong> A Tokyo&ndash;Kyoto reserved seat is around &yen;14,000 per adult one way, '
    'so two adults + one 6&ndash;11 child is roughly &yen;35,000 one way &mdash; confirm exact fares for your dates '
    'on the official site. A Japan Rail Pass can be cheaper if you take several long trips.</li>'
    '<li><strong>On the day.</strong> Arrive 20&ndash;30 minutes early, use station elevators (most are '
    'stroller-accessible), and grab ekiben (station bento boxes) so hungry kids are sorted for the ride.</li>'
    '</ol>'
    '</section>'
)

# 旅程/交通系の記事だけを対象（slug判定）＋本文にShinkansen言及があるもの。
_SHINKANSEN_SLUG_HINT = ("itinerary", "transport", "getting-around", "shinkansen", "public-transport")


def _inject_shinkansen_steps() -> int:
    done = 0
    for path in SITE_DIR.glob("*.html"):
        slug = path.stem
        if not any(k in slug for k in _SHINKANSEN_SLUG_HINT):
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'id="shinkansen-steps"' in html or "Shinkansen" not in html:  # 冪等＋無関係skip
            continue
        if "<h2>FAQ" in html:
            new = html.replace("<h2>FAQ", _SHINKANSEN_STEPS + "<h2>FAQ", 1)
        elif '<section class="related"' in html:
            new = html.replace('<section class="related"', _SHINKANSEN_STEPS + '<section class="related"', 1)
        elif "</article>" in html:
            new = html.replace("</article>", _SHINKANSEN_STEPS + "</article>", 1)
        else:
            continue
        if new != html:
            path.write_text(new, encoding="utf-8")
            done += 1
            log.info("quality_fixups: #2 新幹線家族予約手順 注入 %s", slug)
    return done


# ============================================================
# #7 年齢帯（0-2/3-5/6-12）で要点を分岐
# ============================================================
# 監査#7: 「young children」で一括り。2歳と8歳で必要なものは激変するのに分岐が無い。
# 旅程系の記事に、ペース配分と取捨選択を年齢帯で示す早見表を注入（一般的な育児ガイド・捏造なし）。
_AGE_BANDS = (
    '<section id="age-bands" class="age-bands" style="margin:1.8em 0;border:1px solid #ffe0ee;'
    'border-radius:14px;padding:6px 18px 10px;background:#fffafc">'
    '<h2>Same trip, very different kids: tailoring by age</h2>'
    '<p>&ldquo;Young children&rdquo; covers a lot of ground. Here is how to adjust the pace and the picks by age '
    '&mdash; every child is different, so treat this as a starting point.</p>'
    '<table><thead><tr><th>Age</th><th>Pace &amp; logistics</th><th>What tends to land</th></tr></thead><tbody>'
    '<tr><td><strong>0&ndash;2 (babies &amp; toddlers)</strong></td>'
    '<td>Plan around naps &mdash; one main outing a day, then back for a midday rest. Bring or rent a stroller and '
    'use the nursing/diaper rooms in department stores and big stations. Under-6s ride trains free on a lap.</td>'
    '<td>Parks and gardens, gentle animal encounters, sensory spots and short boat rides. Keep it low-key.</td></tr>'
    '<tr><td><strong>3&ndash;5 (preschoolers)</strong></td>'
    '<td>Many still need a rest or a quiet hour. Short attention spans &mdash; build in downtime, keep snacks handy, '
    'and a stroller still helps on long days.</td>'
    '<td>Character parks (Tokyo Disneyland over the bigger-ride DisneySea), aquariums, hands-on museums, '
    'train-spotting.</td></tr>'
    '<tr><td><strong>6&ndash;12 (school age)</strong></td>'
    '<td>Can handle fuller days with breaks and more walking. They pay a child fare (about half) on trains and many '
    'attractions &mdash; and love being involved in choosing the day&rsquo;s plan.</td>'
    '<td>teamLab, theme parks with bigger rides, interactive and science museums, ramen- or food-making, a day trip '
    'by Shinkansen.</td></tr>'
    '</tbody></table>'
    '<p style="font-size:.85rem;color:#6b7280">Mixed ages? Anchor the day on the youngest child&rsquo;s nap and '
    'energy, then add one &ldquo;big-kid&rdquo; activity the older ones will love.</p>'
    '</section>'
)

# 旅程系のみに限定（過剰注入の防止。アドバイザー指摘: food-allergies等に出ていた）。
_AGE_SLUG_HINT = ("itinerary", "things-to-do", "days-in")
_AGE_BANDS_RE = re.compile(r'<section id="age-bands".*?</section>', re.S)


def _inject_age_bands() -> int:
    done = 0
    for path in SITE_DIR.glob("*.html"):
        slug = path.stem
        target = any(k in slug for k in _AGE_SLUG_HINT)
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        has = 'id="age-bands"' in html
        if target:
            if has:  # 冪等
                continue
            if "<h2>FAQ" in html:
                new = html.replace("<h2>FAQ", _AGE_BANDS + "<h2>FAQ", 1)
            elif '<section class="related"' in html:
                new = html.replace('<section class="related"', _AGE_BANDS + '<section class="related"', 1)
            elif "</article>" in html:
                new = html.replace("</article>", _AGE_BANDS + "</article>", 1)
            else:
                continue
            if new != html:
                path.write_text(new, encoding="utf-8")
                done += 1
                log.info("quality_fixups: #7 年齢帯分岐 注入 %s", slug)
        elif has:  # 非対象ページに混入していたら除去（過剰注入の是正・自己修正）
            new = _AGE_BANDS_RE.sub("", html)
            if new != html:
                path.write_text(new, encoding="utf-8")
                log.info("quality_fixups: #7 年齢帯分岐 除去（非対象） %s", slug)
    return done


# ============================================================
# 流入B 被引用資産：埋め込みウィジェット＋Dataset schema
# ============================================================
# 他サイトがiframeで貼れる小型ウィジェット（貼られる＝自然な被リンク）と、
# AI/Google Dataset Searchが拾える schema.org/Dataset を用意する。
# 素材は#3で作った実在の独自データ（日本語アレルギーフレーズ）を再利用。
EMBED_CARD_REL = "embed/allergy-card.html"
EMBEDS_PAGE_REL = "tools/embeds.html"


def _base_url() -> str:
    try:
        b = (load_settings().get("site", {}) or {}).get("base_url") or "https://littletabi.com"
    except Exception:
        b = "https://littletabi.com"
    return b.rstrip("/")


def _embed_card_html(base: str) -> str:
    # iframe埋め込み専用の小型カード。サイトchrome無し・noindex・末尾に出典リンク（=被リンク）。
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex">'
        '<title>Japanese Allergy Card (embed) | littletabi</title>'
        '<style>'
        'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;'
        'color:#1f2937;margin:0;background:#fff}'
        '.w{max-width:520px;margin:0 auto;padding:12px 14px}'
        'h2{font-size:1.05rem;margin:.2em 0 .5em;color:#b8005a}'
        'table{width:100%;border-collapse:collapse;font-size:.92rem}'
        'td{border-bottom:1px solid #f0e6ec;padding:5px 4px;vertical-align:top}'
        '.ja{font-weight:600}.src{font-size:.78rem;color:#6b7280;margin-top:8px}'
        '.src a{color:#b8005a}'
        '</style></head><body><div class="w">'
        '<h2>Japanese allergy phrases for kids</h2>'
        '<table><tbody>'
        '<tr><td>My child has food allergies.</td><td class="ja" lang="ja">この子は食物アレルギーがあります。</td></tr>'
        '<tr><td>It is severe — even a small amount is dangerous.</td><td class="ja" lang="ja">重いアレルギーです。少しでも入ると危険です。</td></tr>'
        '<tr><td>Does this contain ___ ?</td><td class="ja" lang="ja">これに ___ は入っていますか？</td></tr>'
        '<tr><td>Could you make it without ___ ?</td><td class="ja" lang="ja">___ を抜いてもらえますか？</td></tr>'
        '<tr><td>Emergency — call an ambulance (119).</td><td class="ja" lang="ja">緊急です。119番に電話してください。</td></tr>'
        '</tbody></table>'
        '<p class="src">Free widget &middot; data by <a href="' + base + '" target="_blank" rel="noopener">littletabi</a> '
        '&middot; <a href="' + base + '/' + ALLERGY_TOOL_REL + '" target="_blank" rel="noopener">full printable card</a></p>'
        '</div></body></html>'
    )


def _embeds_page_html(base: str) -> str:
    iframe_src = base + "/" + EMBED_CARD_REL
    snippet = (
        '&lt;iframe src="' + iframe_src + '" width="100%" height="430" loading="lazy" '
        'style="border:1px solid #eee;border-radius:12px" title="Japanese allergy card for kids"&gt;&lt;/iframe&gt;\n'
        '&lt;p&gt;Widget by &lt;a href="' + base + '"&gt;littletabi&lt;/a&gt;&lt;/p&gt;'
    )
    dataset = (
        '{"@context":"https://schema.org","@type":"Dataset",'
        '"name":"Japanese food-allergy communication phrases for family travellers",'
        '"description":"A curated English to Japanese set of phrases and allergen terms for communicating '
        'children\'s food allergies at restaurants in Japan.",'
        '"creator":{"@type":"Organization","name":"littletabi","url":"' + base + '"},'
        '"license":"https://creativecommons.org/licenses/by/4.0/",'
        '"url":"' + base + '/' + EMBEDS_PAGE_REL + '",'
        '"isAccessibleForFree":true,'
        '"distribution":[{"@type":"DataDownload","encodingFormat":"text/html",'
        '"contentUrl":"' + base + '/' + EMBED_CARD_REL + '"}]}'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Free embeddable widgets for family-travel sites | littletabi</title>'
        '<meta name="description" content="Free, embeddable widgets and open data for family-travel sites: '
        'a Japanese allergy phrase card you can drop into any page with one line of HTML.">'
        '<link rel="canonical" href="' + base + '/' + EMBEDS_PAGE_REL + '">'
        '<script type="application/ld+json">' + dataset + '</script>'
        '<style>'
        ':root{--ink:#1f2937;--muted:#6b7280;--accent:#b8005a;--line:#ececf1}'
        'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;'
        'color:var(--ink);background:#fffdfb;margin:0;line-height:1.6}'
        '.wrap{max-width:760px;margin:0 auto;padding:24px 18px}a{color:var(--accent)}'
        '.brand{font-weight:800;color:var(--ink);text-decoration:none}.brand b{color:var(--accent)}'
        'h1{font-size:1.5rem}.card{border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin:18px 0;background:#fff}'
        'pre{background:#0f172a;color:#e2e8f0;padding:12px 14px;border-radius:10px;overflow:auto;font-size:.82rem;white-space:pre-wrap}'
        '.note{font-size:.85rem;color:var(--muted)}'
        '</style></head><body><div class="wrap">'
        '<p><a class="brand" href="/index.html">little<b>tabi</b></a></p>'
        '<h1>Free embeddable widgets &amp; open data</h1>'
        '<p>Run a family-travel blog or resource site? You are welcome to embed our widgets for free. '
        'They are lightweight, mobile-friendly, and released under a <a '
        'href="https://creativecommons.org/licenses/by/4.0/" rel="nofollow noopener" target="_blank">CC BY 4.0</a> '
        'licence &mdash; just keep the small attribution link.</p>'
        '<div class="card">'
        '<h2>Japanese allergy phrase card</h2>'
        '<p>English &rarr; Japanese phrases to communicate a child&rsquo;s food allergies at restaurants. '
        'Live preview:</p>'
        '<iframe src="' + iframe_src + '" width="100%" height="430" loading="lazy" '
        'style="border:1px solid #eee;border-radius:12px" title="Japanese allergy card for kids"></iframe>'
        '<p>Paste this one line where you want it to appear:</p>'
        '<pre>' + snippet + '</pre>'
        '<p class="note">The phrases are for communication only, not medical advice. Japan&rsquo;s mandatory '
        'allergen list changes &mdash; confirm current details on the Consumer Affairs Agency site.</p>'
        '</div>'
        '<p class="note">More widgets (a family-trip cost estimator and a station accessibility lookup) are on the '
        'way. Want one for your site? <a href="/' + THANKS_OR_CONTACT + '">Get in touch</a>.</p>'
        '<p><a href="/index.html">&larr; Back to all guides</a></p>'
        '</div></body></html>'
    )


# 連絡導線（存在する索引/トップに寄せる。無ければトップ）。
THANKS_OR_CONTACT = "contact.html"


def _build_embeds() -> int:
    base = _base_url()
    done = 0
    targets = {
        EMBED_CARD_REL: _embed_card_html(base),
        EMBEDS_PAGE_REL: _embeds_page_html(base),
    }
    for rel, html in targets.items():
        path = SITE_DIR / rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_text(encoding="utf-8") == html:  # 冪等
                continue
            path.write_text(html, encoding="utf-8")
            done += 1
            log.info("quality_fixups: 流入B 埋め込み資産生成 %s", rel)
        except Exception as e:
            log.error("quality_fixups: embed生成失敗 %s: %s", rel, e)
    # embedsページ（被引用用・indexable）をsitemapに収録（embedカード自体はnoindexなので入れない）
    _add_to_sitemap(f"{base}/{EMBEDS_PAGE_REL}")
    return done


def _add_to_sitemap(loc: str) -> None:
    sm = SITE_DIR / "sitemap.xml"
    if not sm.exists():
        return
    try:
        xml = sm.read_text(encoding="utf-8")
    except Exception:
        return
    if loc in xml or "</urlset>" not in xml:
        return
    today = datetime.date.today().isoformat()
    block = (f"<url>\n<loc>{loc}</loc>\n<lastmod>{today}</lastmod>\n"
             "<changefreq>monthly</changefreq>\n<priority>0.6</priority>\n</url>\n")
    sm.write_text(xml.replace("</urlset>", block + "</urlset>", 1), encoding="utf-8")
    log.info("quality_fixups: sitemapにembedsページ追加")


# ============================================================
# #18 重複記事のカニバリ是正：近似重複クラスタを代表1本にcanonical集約（冪等・可逆）
# ============================================================
# autopilotが量産した同一トピックの近似重複を、確認済みの明示マップで代表ページへcanonical集約。
# site.pyが毎回self-canonicalを再生成→本処理が後段で上書きするため、マップを消せば原状復帰（可逆）。
# 自動判定はしない（誤集約でのインデックス落ち防止）。
_CANONICAL_OVERRIDE = {
    "navigating-japan-s-public-transport-with-kids-2026":
        "japan-public-transport-with-kids-fares-strollers-facilities",
    "buying-baby-diapers-wipes-and-formula-in-japan-2026":
        "diapers-formula-baby-gear-in-japan-what-to-pack-buy",
    "diapers-formula-in-japan-brands-sizes-where-to-buy":
        "diapers-formula-baby-gear-in-japan-what-to-pack-buy",
}


def _apply_canonical_overrides() -> int:
    done = 0
    for dup, primary in _CANONICAL_OVERRIDE.items():
        path = SITE_DIR / f"{dup}.html"
        if not path.exists():
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        old = '<link rel="canonical" href="https://littletabi.com/' + dup + '.html">'
        want = '<link rel="canonical" href="https://littletabi.com/' + primary + '.html">'
        if want in html:
            continue
        if old in html:
            path.write_text(html.replace(old, want, 1), encoding="utf-8")
            done += 1
            log.info("quality_fixups: canonical override %s -> %s", dup, primary)
    return done


# ============================================================
# 1-2 ハルシネーション/事実誤認の除去（冪等スクラブ）
# 実在確認できない固有名詞・訪日客向け直販eSIMという虚偽前提・捏造価格・虚偽購入方法を
# 後段で除去/修正する。正しい代替が確認できたものだけ書き換え、それ以外は削除（削除がデフォルト）。
# ============================================================
_SCRUB = {
    "best-family-hotels-tokyo-connecting-rooms": [
        # 旧filler宿 Granbell の例示文（Shinjuku Gyoen 近接主張）を削除（中間レビュー #4）。
        (" For instance, the <strong>Shinjuku Granbell Hotel</strong> not only offers connecting rooms but also has easy access to Shinjuku Gyoen, a large city park with playgrounds, making it ideal for family outings.", ""),
        # 参照先テーブルを削除済みなのに残った導入文（2026-07-19 レビュー #4）。
        ("The table above compares <em>types</em> of stay. ", ""),
    ],
    "tokyo-disneyland-vs-disneysea-young-kids": [
        # 実在疑義: ミッキー型グローブに豚カツ の記述を削除（2026-07-10 中間レビュー #9）。
        ("and cute Mickey-shaped gloves filled with pork cutlets ", ""),
    ],
    "japan-esim-for-families-compared": [
        ("<li><strong>Suzuki's Fun Train:</strong> An interactive way for kids to learn about Japanese culture.</li>", ""),
        ("<li><strong>Suzuki&rsquo;s Fun Train:</strong> An interactive way for kids to learn about Japanese culture.</li>", ""),
        ("Tokyo's Shinkansen (bullet trains) offer excellent Wi-Fi",
         "Japan's Shinkansen (bullet trains) offer free Wi-Fi on many lines"),
        ("Tokyo&rsquo;s Shinkansen (bullet trains) offer excellent Wi-Fi",
         "Japan&rsquo;s Shinkansen (bullet trains) offer free Wi-Fi on many lines"),
        ("the best eSIM options are the Softbank 5G and DOCOMO 4G LTE plans, providing reliable internet access for navigating, entertainment, and family communication.",
         "the easiest way to stay online is a travel eSIM that runs on Japan's major networks (SoftBank or NTT DOCOMO), giving you reliable data for navigating, entertainment, and family communication."),
        ("For instance, a 5GB plan from Softbank costs around 4,500 yen (as of 2026; confirm on the official site). ", ""),
        ("Plans typically range from 3,000 to 10,000 yen (as of 2026; confirm on the official site)",
         "Prices vary by data amount and trip length &mdash; always confirm the current price before you buy"),
    ],
}
_SCRUB_RE = {
    "best-family-hotels-tokyo-connecting-rooms": [
        # 旧fillerテーブル2つ（Park/Granbell/Gracery, Citadines/Oakwood）を削除し
        # 「Our specific picks」9軒テーブルへ一本化（2026-07-10 中間レビュー #4）。
        (re.compile(r"<h2>Top Family Hotels with Connecting Rooms</h2>.*?</table>", re.S), ""),
        (re.compile(r"<h2>Hotels with Kitchenettes</h2>.*?</table>\s*<p>.*?</p>", re.S), ""),
        # 旧filler宿(Park/Granbell/Gracery)の解説段落を削除（中間レビュー #4）。
        (re.compile(r"<p><strong>The Park Hotel Tokyo</strong>.*?</p>", re.S), ""),
    ],
    "japan-esim-for-families-compared": [
        (re.compile(r"<table><tr><th>eSIM Provider</th>.*?</table>", re.S), ""),
    ],
    "japan-family-itinerary-tokyo-kyoto-osaka-with-young-children": [
        (re.compile(r"Consider using the <a [^>]*>Disney Premier Access</a> for shorter wait times at popular attractions\."),
         "Disney Premier Access (paid ride reservations) is sold only in the official Tokyo Disney Resort app, not on third-party sites."),
    ],
}


def _scrub_hallucinations() -> int:
    fixed = 0
    slugs = set(_SCRUB) | set(_SCRUB_RE)
    for slug in slugs:
        path = SITE_DIR / f"{slug}.html"
        if not path.exists():
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        orig = html
        for a, b in _SCRUB.get(slug, []):
            html = html.replace(a, b)
        for rx, b in _SCRUB_RE.get(slug, []):
            html = rx.sub(lambda _m: b, html)
        if html != orig:
            path.write_text(html, encoding="utf-8")
            fixed += 1
            log.info("quality_fixups: 1-2 ハルシネーション除去 %s", slug)
    return fixed


# ============================================================
# 1-6 「(as of 2026 …)」の多用を抑制（1記事2回まで。超過分を除去）
# 機械的な連発は読者体験と信頼性を損なうため、後段で冪等に上限を適用する。
# ============================================================
_ASOF_RE = re.compile(
    r"\s*\(as of 2026[^)]*\)"
    r"|,?\s*as of 2026, confirm on the official site"
)


def _limit_asof(max_keep: int = 2) -> int:
    fixed = 0
    for path in SITE_DIR.glob("*.html"):
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        seen = [0]
        def repl(m):
            seen[0] += 1
            return m.group(0) if seen[0] <= max_keep else ""
        new = _ASOF_RE.sub(repl, html)
        if new != html:
            path.write_text(new, encoding="utf-8")
            fixed += 1
            log.info("quality_fixups: (as of 2026)を%d回に制限 %s", max_keep, path.stem)
    return fixed


# ============================================================
# 復旧スプリントC #C-1 手作業ページの恒久化（再生成で二度と消さない）
# ============================================================
# 2026-08 の履歴巻き戻し事故で、docs/ に直接コミットしていた3ページ（新幹線・子連れ料金
# 計算機と、そのコンパニオン記事2本）が消滅した。原因は「docs/ にしか実体が無い」こと。
# そこで実体を assets/pages/ に置き、毎runここから docs/ へ冪等に再生成する。
# アレルギーカード (_build_allergy_tool) と同じ設計思想＝「生成物はsrc側が持つ」。
# 本文は git 履歴（PR #32/#33/#34/#35）から取り出したものをそのまま保持しており、
# 内容の書き換え・再生成は一切行わない（捏造防止）。
STATIC_PAGES_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "pages"
STATIC_PAGES = (
    "shinkansen-family-fare-calculator.html",   # PR #32/#33（Kitフォーム9651205・±10円注記）+ #35（WebApplication）
    "shinkansen-cost-for-families.html",        # PR #35（FAQ構造化データ付きコンパニオン記事）
    "eating-out-in-japan-with-food-allergies.html",  # PR #35（同上）
    # 2026-09-05: ホテル比較ページを手組み（公式サイト確認済み15軒）に置換。
    # GSC実測で唯一検索需要のあるページ（"tokyo hotel with kitchenette" 群）のため本文ごと作り直した。
    "best-family-hotels-tokyo-connecting-rooms.html",
    # 2026-09-05: 京阪神のキッチン付きファミリーホテル比較（東京版と同じ手法・公式サイト確認済み14軒）。
    "kyoto-osaka-family-hotels-with-kitchens.html",
    # 2026-09-06: 東京ディズニーリゾート提携ホテル16軒（ディズニー6・オフィシャル6・パートナー4）。
    "tokyo-disney-resort-hotels-for-families.html",
)


def _with_site_head(html: str) -> str:
    """静的ページにもサイト共通の計測/収益スクリプト（GA4・Travelpayouts）を冪等に入れる。

    site.rebuild_index のバックフィルは、この種の手組みページをテンプレートで
    上書きして計算機UIごと壊してしまう（2026-08の実測で確認）。そのため本関数で
    復元したうえで、head に必要なタグだけを後から足す。
    """
    from . import site as _site
    head = ""
    if "googletagmanager.com/gtag" not in html:
        head += _site._ga_snippet()
    if "tpembars.com" not in html:
        head += _site._tpdrive_snippet()
    if not head:
        return html
    marker = '<meta name="viewport"'
    i = html.find(marker)
    if i < 0:
        i = html.find("<head>")
        return html[:i + 6] + "\n" + head + html[i + 6:] if i >= 0 else html
    j = html.find(">", i)
    return html[:j + 1] + "\n" + head + html[j + 1:]


def _build_static_pages() -> int:
    """assets/pages/ の実体を docs/ へ冪等にコピーする（既に同一なら書かない）。"""
    n = 0
    for name in STATIC_PAGES:
        src = STATIC_PAGES_DIR / name
        if not src.exists():
            log.error("quality_fixups: 静的ページの実体が見つからない %s", src)
            continue
        try:
            html = _with_site_head(src.read_text(encoding="utf-8"))
            dst = SITE_DIR / name
            if dst.exists() and dst.read_text(encoding="utf-8") == html:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(html, encoding="utf-8")
            log.info("quality_fixups: 静的ページ再生成 %s", name)
            n += 1
        except Exception as e:
            log.error("quality_fixups: 静的ページ生成失敗 %s: %s", name, e)
    return n


# ============================================================
# Pinterest 用「Pin this guide」図の注入（2026-09-05）
# ============================================================
# Pinterest の「URLから保存」はページ内の縦長(2:3〜1:1)画像しか拾わない。記事画像は全て横長なので、
# docs/img/pins/pin-<slug>.jpg（1000×1500）が存在するページにだけ、関連ガイドの手前へ
# 保存ボタン付きの図を冪等に差し込む。画像が無いページには何もしない。
PINS_DIR = SITE_DIR / "img" / "pins"
_PIN_FIG_RE = re.compile(r'<figure class="pin-this".*?</figure>', re.S)


def _pin_figure_html(slug: str, img_name: str, title: str) -> str:
    from urllib.parse import quote
    base = _base_url()
    url = f"{base}/{slug}.html"
    media = f"{base}/img/pins/{img_name}"
    share = ("https://www.pinterest.com/pin/create/button/?url=" + quote(url, safe="")
             + "&media=" + quote(media, safe="") + "&description=" + quote(title, safe=""))
    return (
        '<figure class="pin-this" style="margin:1.6em auto;max-width:360px;text-align:center">'
        f'<a href="{share}" rel="nofollow noopener" target="_blank">'
        f'<img src="/img/pins/{img_name}" alt="Pin: {title}" width="1000" height="1500" loading="lazy" '
        'style="width:100%;height:auto;border-radius:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)"></a>'
        '<figcaption style="font-size:.8rem;color:#6b7280;margin-top:6px">Save this guide on Pinterest</figcaption>'
        '</figure>'
    )


def _inject_pin_figures() -> int:
    n = 0
    if not PINS_DIR.exists():
        return 0
    for img in sorted(PINS_DIR.glob("pin-*.jpg")):
        slug = img.stem[4:]
        path = SITE_DIR / f"{slug}.html"
        if not path.exists():
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        title = re.sub(r"\s*\|.*$", "", (m.group(1) if m else slug)).strip()
        title = title.replace("&amp;", "&")
        block = _pin_figure_html(slug, img.name, title)
        if 'class="pin-this"' in html:
            new = _PIN_FIG_RE.sub(lambda _m: block, html, count=1)
        else:
            # 関連ガイド（手組みページは <h2 class="rel">、生成記事は <section class="related">）の直前。
            # どちらも無ければ </main> の直前。
            for marker in ('<h2 class="rel">', '<section class="related">', '</main>'):
                at = html.find(marker)
                if at >= 0:
                    new = html[:at] + block + "\n" + html[at:]
                    break
            else:
                continue
        if new != html:
            path.write_text(new, encoding="utf-8")
            n += 1
            log.info("quality_fixups: Pin図注入 %s", slug)
    return n


# ============================================================
# 404ページ（soft-404の解消）
# ============================================================
# 2026-08-22 実測: docs/404.html が存在せず、存在しないURLがすべて HTTP 200 で
# トップページを返していた（/this-page-does-not-exist も /404.html も 200）。
# つまりタイプミスや古いURLの数だけ「トップページの複製」が200で生成される状態で、
# 重複コンテンツ・クロール予算の浪費・削除済みURLが消えない、の三重に効く。
# 7月には存在したファイルが履歴の差し替えで消え、site.py は生成しないため復活しなかった。
# Cloudflare Pages は出力直下に 404.html があれば未一致URLにそれを 404 で返す。
def _404_html() -> str:
    from . import site as _site
    head = (
        '<meta name="robots" content="noindex,follow">\n'
        '<meta name="description" content="This page was not found. Browse our Japan-with-kids guides instead.">\n'
        '<meta property="og:description" content="This page was not found. Browse our Japan-with-kids guides instead.">\n'
    )
    body = (
        '<main class="wrap">'
        '<h1>This page doesn&rsquo;t exist</h1>'
        '<p class="lead">The link may be out of date, or the address may have a typo. '
        'Here is where most families go next.</p>'
        '<ul>'
        '<li><a href="/">All Japan-with-kids guides</a></li>'
        '<li><a href="/plan.html">Free trip planner</a> &mdash; a day-by-day family plan in seconds</li>'
        '<li><a href="/shinkansen-family-fare-calculator.html">Shinkansen family fare calculator</a> '
        '&mdash; estimate the total with kids&rsquo; fare rules</li>'
        '<li><a href="/tools/allergy-card.html">Printable Japanese allergy card</a></li>'
        '<li><a href="/get-the-japan-checklist.html">Free pre-departure checklist (PDF)</a></li>'
        '</ul>'
        '<p><a href="/japan-with-kids-transport.html">Transport</a> &middot; '
        '<a href="/japan-with-kids-accommodation.html">Accommodation</a> &middot; '
        '<a href="/japan-with-kids-food.html">Food</a> &middot; '
        '<a href="/japan-with-kids-attractions.html">Attractions</a> &middot; '
        '<a href="/japan-with-kids-baby.html">Babies &amp; toddlers</a> &middot; '
        '<a href="/japan-with-kids-practical.html">Practical</a></p>'
        '</main>'
    )
    cfg = load_settings()
    return _site._document("en", "Page not found | " + cfg["site"]["site_name"], head, body)


def _build_404() -> int:
    path = SITE_DIR / "404.html"
    try:
        html = _404_html()
        if path.exists() and path.read_text(encoding="utf-8") == html:
            return 0
        path.write_text(html, encoding="utf-8")
        log.info("quality_fixups: 404ページ生成")
        return 1
    except Exception as e:
        log.error("quality_fixups: 404ページ生成失敗: %s", e)
        return 0


def run() -> dict:
    sp = _build_static_pages()
    m = _inject_money_picks()
    pins = _inject_pin_figures()
    hx = _scrub_hallucinations()
    c = _apply_canonical_overrides()
    t = _build_allergy_tool()
    a = _inject_allergy_inline()
    b = _strip_offtopic_bullets()
    s = _ensure_sitemap_tool()
    f = _front_trust_and_dataviz()
    k = _inject_shinkansen_steps()
    g = _inject_age_bands()
    e = _build_embeds()
    q = _limit_asof()
    nf = _build_404()   # 他のfixupに触られないよう最後に生成する
    log.info("quality_fixups完了: 静的ページ=%d, 固有名詞=%d, allergyツール=%d, allergy注入=%d, バレット除去=%d, sitemap=%d, dataviz前面=%d, 透明性=%d, 新幹線手順=%d, 年齢帯=%d, 埋め込み=%d, 404=%d",
             sp, m, t, a, b, s, f["dataviz_hoisted"], f["trust_strip"], k, g, e, nf)
    return {"static_pages": sp, "money_picks": m, "scrub": hx, "canonical_dedup": c, "allergy_tool": t, "allergy_inline": a, "bullets": b, "sitemap": s,
            "dataviz_hoisted": f["dataviz_hoisted"], "trust_strip": f["trust_strip"],
            "shinkansen_steps": k, "age_bands": g, "embeds": e, "asof": q, "notfound": nf}




def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("quality_fixups失敗: %s", e)


if __name__ == "__main__":
    main()
