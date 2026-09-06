# -*- coding: utf-8 -*-
"""ホテル系アフィリエイトリンクの唯一の組み立て場所（2026-09-06）。

背景: ホテルページの「See rates」は長らく Booking.com の検索URLで、Travelpayouts の
ページ内スクリプト頼みの未収益リンクだった。2026-09-05 に Trip.com アフィリエイトが
有効化されたので、ホテルの deep link をここ1か所で組み立てる。ページ側やfixup側に
URLを散らかさない（散らかると、次にプログラムが変わったとき全ページを手で直す羽目になる）。

ID は絶対に推測しない。`TRIP_HOTELS` の各IDは Trip.com のアフィリエイトリンクツールが
発行した実物で、手組みページから採取したもの。新しいホテルを足すときも、ツールが出した
リンクからIDとURLスラッグを写すこと（CLAUDE.md「捏造しない」）。

実行: `python -m src.affiliates --selftest`
"""
from __future__ import annotations
import re

ALLIANCE_ID = "10447753"
SID = "330435547"
SUB3 = "D19699311"
DEFAULT_SUB1 = "hotels-tokyo"

# ページ上の呼び名（キー）-> Trip.com の詳細ページパス "<city>-hotel-detail-<id>/<slug>"。
# パスは Trip.com のアフィリエイトリンクツールが出した値をそのまま持つ。末尾スラッグを
# 正規化してはいけない: Trip.com 側が旧名のままの物件がある（例: 二条城は horikawarokkaku、
# First Resort は sunroute-plaza-tokyo）ほか、綴りが崩れたまま運用されているものもある。
# city は tokyo / kyoto / osaka / urayasu。
TRIP_HOTELS = {
    # ── 東京（best-family-hotels-tokyo-connecting-rooms / 6人以上ページ）──
    "mimaru-suites-tokyo-asakusa": "tokyo-hotel-detail-100383864/mimaru-suites-tokyo-asakusa",
    "mimaru-suites-tokyo-nihombashi": "tokyo-hotel-detail-99803618/mimaru-suites-tokyo-nihombashi",
    "mimaru-tokyo-station-east": "tokyo-hotel-detail-92435119/mimaru-tokyo-station-east",
    "mimaru-tokyo-ikebukuro": "tokyo-hotel-detail-99965689/mimaru-tokyo-ikebukuro",
    "mimaru-tokyo-ueno-east": "tokyo-hotel-detail-21864150/mimaru-tokyo-ueno-east",
    "mimaru-tokyo-ueno-north": "tokyo-hotel-detail-13671810/mimaru-tokyo-ueno-north",
    "mimaru-tokyo-ueno-inaricho": "tokyo-hotel-detail-21862382/mimaru-tokyo-ueno-inaricho",
    "mimaru-tokyo-ueno-okachimachi": "tokyo-hotel-detail-48708872/mimaru-tokyo-ueno-okachimachi",
    "mimaru-tokyo-asakusa-station": "tokyo-hotel-detail-72683080/mimaru-tokyo-asakusa-station",
    "mimaru-tokyo-nihombashi-suitengumae": "tokyo-hotel-detail-15835393/mimaru-tokyo-nihombashi-suitengumae",
    "mimaru-tokyo-hatchobori": "tokyo-hotel-detail-25195209/mimaru-tokyo-hatchobori",
    "mimaru-tokyo-akasaka": "tokyo-hotel-detail-14201935/mimaru-tokyo-akasaka",
    "mimaru-tokyo-kinshicho": "tokyo-hotel-detail-92027017/mimaru-tokyo-kinshicho",
    "mimaru-tokyo-ginza-east": "tokyo-hotel-detail-47990998/mimaru-tokyo-ginza-east",
    "mimaru-tokyo-shinjuku-west": "tokyo-hotel-detail-54552657/mimaru-tokyo-shinjuku-west",
    "tokyu-stay-shinjuku": "tokyo-hotel-detail-2509720/tokyu-stay-shinjuku",
    "citadines-shinjuku-tokyo": "tokyo-hotel-detail-1683450/citadines-shinjuku-tokyo",
    "oakwood-premier-tokyo": "tokyo-hotel-detail-4641981/oakwood-premier-tokyo",
    "ascott-marunouchi-tokyo": "tokyo-hotel-detail-7358772/ascott-marunouchi-tokyo",
    "keio-plaza-hotel-tokyo": "tokyo-hotel-detail-994639/keio-plaza-hotel-tokyo",

    # ── 京都・大阪（kyoto-osaka-family-hotels-with-kitchens）──
    "mimaru-suites-kyoto-central": "kyoto-hotel-detail-80625249/mimaru-suites-kyoto-central",
    # Trip.com側のスラッグが崩れているが、実際に発行されたリンクなのでそのまま使う
    "mimaru-suites-kyoto-shijo": "kyoto-hotel-detail-78123223/imaru-uites-yoto-hijo",
    "mimaru-kyoto-station": "kyoto-hotel-detail-40694354/mimaru-kyoto-station",
    # Trip.com側は旧名（堀川六角）のまま
    "mimaru-kyoto-nijo-castle": "kyoto-hotel-detail-15837901/mimaru-kyoto-horikawarokkaku",
    "mimaru-kyoto-kawaramachi-gojo": "kyoto-hotel-detail-48033361/mimaru-kyoto-kawaramachi-gojo",
    "oakwood-hotel-oike-kyoto": "kyoto-hotel-detail-76039598/oakwood-hotel-oike-kyoto",
    "tokyu-stay-kyoto-sakaiza": "kyoto-hotel-detail-22942355/tokyu-stay-kyoto-shinkyogokudori",
    "mimaru-osaka-shinsaibashi-central": "osaka-hotel-detail-132951595/mimaru-osaka-shinsaibashi-central",
    "mimaru-osaka-shinsaibashi-west": "osaka-hotel-detail-56996772/mimaru-osaka-shinsaibashi-west",
    "mimaru-osaka-shinsaibashi-east": "osaka-hotel-detail-100367501/mimaru-osaka-shinsaibashi-east",
    "mimaru-osaka-namba-station": "osaka-hotel-detail-94176886/mimaru-osaka-namba-station",
    "mimaru-osaka-namba-north": "osaka-hotel-detail-69272905/mimaru-osaka-namba-north",
    "citadines-namba-osaka": "osaka-hotel-detail-52647143/citadines-namba-osaka",
    "hotel-universal-port": "osaka-hotel-detail-688230/hotel-universal-port",

    # ── 東京ディズニーリゾート周辺（tokyo-disney-resort-hotels-for-families）──
    # ディズニー直営6ホテルはTrip.com未掲載。公式サイトのリンクのままにする。
    "hilton-tokyo-bay": "tokyo-hotel-detail-926340/hilton-tokyo-bay",
    "grand-nikko-tokyo-bay-maihama": "tokyo-hotel-detail-60644549/grand-nikko-tokyo-bay-maihama",
    "sheraton-grande-tokyo-bay-hotel": "urayasu-hotel-detail-688630/sheraton-grande-tokyo-bay-hotel",
    "hotel-okura-tokyo-bay": "urayasu-hotel-detail-3776533/hotel-okura-tokyo-bay",
    "maihama-view-hotel": "urayasu-hotel-detail-1497303/maihama-view-hotel-by-hulic",
    # Trip.com側は旧名（Sunroute Plaza Tokyo）のまま
    "tokyo-bay-maihama-hotel-first-resort": "urayasu-hotel-detail-688260/sunroute-plaza-tokyo",
    "hotel-emion-tokyo-bay": "urayasu-hotel-detail-1497512/hotel-emion-tokyo-bay",
    "urayasu-brighton-hotel-tokyo-bay": "urayasu-hotel-detail-1678833/urayasu-brighton-hotel-tokyo-bay",
    "mitsui-garden-hotel-prana-tokyo-bay": "urayasu-hotel-detail-704032/mitsui-garden-hotel-prana-tokyo-bay",
    "oriental-hotel-tokyo-bay": "urayasu-hotel-detail-1497509/oriental-hotel-tokyo-bay",
}


def trip_hotel_url(hotel_slug: str, sub1: str = DEFAULT_SUB1) -> str:
    """TRIP_HOTELS に登録済みホテルの Trip.com deep link を返す。

    パスは TRIP_HOTELS が丸ごと持つので、都市（tokyo/kyoto/osaka/urayasu）も
    Trip.com 側の物件スラッグもここで自動的に正しくなる。
    """
    if hotel_slug not in TRIP_HOTELS:
        raise KeyError(
            "Trip.com のホテルIDが未登録: %s（IDは推測せず、アフィリエイトリンクツールの発行値を使う）"
            % hotel_slug)
    return ("https://www.trip.com/hotels/%s/?Allianceid=%s&SID=%s&trip_sub1=%s&trip_sub3=%s"
            % (TRIP_HOTELS[hotel_slug], ALLIANCE_ID, SID, sub1, SUB3))


def rates_link(hotel_slug: str, label: str = "See rates", sub1: str = DEFAULT_SUB1) -> str:
    """「See rates」用の <a>。rel は sponsored nofollow noopener を必ず付ける。"""
    return ('<a href="%s" rel="sponsored nofollow noopener" target="_blank">%s</a>'
            % (trip_hotel_url(hotel_slug, sub1).replace("&", "&amp;"), label))


def _selftest() -> int:
    """外部依存なしの回帰テスト。パス形式と、既存13軒のURL不変を検査する。"""
    fails = []

    # ① パス形式（都市 + 数値ID + スラッグ）。IDの取り違え・書き写しミスをここで落とす。
    shape = re.compile(r"^(tokyo|kyoto|osaka|urayasu)-hotel-detail-\d+/[A-Za-z0-9-]+$")
    for key, path in TRIP_HOTELS.items():
        if not shape.match(path):
            fails.append("パス形式が不正: %s -> %s" % (key, path))
    ids = {}
    for key, path in TRIP_HOTELS.items():
        hid = path.split("-hotel-detail-")[1].split("/")[0]
        if hid in ids:
            fails.append("ホテルIDの重複: %s と %s が同じID %s" % (ids[hid], key, hid))
        ids[hid] = key

    # ② 2026-09-05に公開済みの東京13軒はURLが変わってはいけない（値の持ち方をリファクタ
    #    したときに、生きているリンクが静かに変わる事故を防ぐ）。
    frozen = {
        "mimaru-suites-tokyo-asakusa": "tokyo-hotel-detail-100383864/mimaru-suites-tokyo-asakusa",
        "mimaru-tokyo-station-east": "tokyo-hotel-detail-92435119/mimaru-tokyo-station-east",
        "mimaru-tokyo-ikebukuro": "tokyo-hotel-detail-99965689/mimaru-tokyo-ikebukuro",
        "mimaru-tokyo-ueno-east": "tokyo-hotel-detail-21864150/mimaru-tokyo-ueno-east",
        "mimaru-tokyo-ginza-east": "tokyo-hotel-detail-47990998/mimaru-tokyo-ginza-east",
        "mimaru-tokyo-shinjuku-west": "tokyo-hotel-detail-54552657/mimaru-tokyo-shinjuku-west",
        "tokyu-stay-shinjuku": "tokyo-hotel-detail-2509720/tokyu-stay-shinjuku",
        "citadines-shinjuku-tokyo": "tokyo-hotel-detail-1683450/citadines-shinjuku-tokyo",
        "oakwood-premier-tokyo": "tokyo-hotel-detail-4641981/oakwood-premier-tokyo",
        "ascott-marunouchi-tokyo": "tokyo-hotel-detail-7358772/ascott-marunouchi-tokyo",
        "keio-plaza-hotel-tokyo": "tokyo-hotel-detail-994639/keio-plaza-hotel-tokyo",
        "hilton-tokyo-bay": "tokyo-hotel-detail-926340/hilton-tokyo-bay",
        "grand-nikko-tokyo-bay-maihama": "tokyo-hotel-detail-60644549/grand-nikko-tokyo-bay-maihama",
    }
    for key, path in frozen.items():
        if TRIP_HOTELS.get(key) != path:
            fails.append("公開済みリンクが変わっている: %s -> %s (期待 %s)"
                         % (key, TRIP_HOTELS.get(key), path))

    expected = ("https://www.trip.com/hotels/tokyo-hotel-detail-100383864/mimaru-suites-tokyo-asakusa/"
                "?Allianceid=10447753&SID=330435547&trip_sub1=hotels-tokyo&trip_sub3=D19699311")
    got = trip_hotel_url("mimaru-suites-tokyo-asakusa")
    if got != expected:
        fails.append("URL組み立てが実ページと一致しない:\n  expected %s\n  got      %s" % (expected, got))

    # ③ <a> の体裁
    a = rates_link("hilton-tokyo-bay")
    for needed in ('rel="sponsored nofollow noopener"', "Allianceid=10447753", "&amp;"):
        if needed not in a:
            fails.append("rates_link に %s が無い" % needed)

    # ④ 未登録スラッグは例外（IDを推測させない）
    try:
        trip_hotel_url("not-a-registered-hotel")
        fails.append("未登録スラッグで例外が出ない（IDを推測される事故のもと）")
    except KeyError:
        pass

    for line in fails:
        print("selftest FAIL:", line)
    if fails:
        print("affiliates selftest: %d 件失敗" % len(fails))
        return 1
    print("affiliates selftest: Trip.com %d軒 / 公開済み13軒のURL不変 / パス形式 OK"
          % len(TRIP_HOTELS))
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_selftest() if "--selftest" in _sys.argv else 0)
