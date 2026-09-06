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

ALLIANCE_ID = "10447753"
SID = "330435547"
SUB3 = "D19699311"
DEFAULT_SUB1 = "hotels-tokyo"

# URLスラッグ -> (Trip.comの都市スラッグ, ホテルID)
# 東京の13軒。Trip.com のリンクツールが発行した値をそのまま保持する。
TRIP_HOTELS = {
    "mimaru-suites-tokyo-asakusa": ("tokyo", "100383864"),
    "mimaru-tokyo-station-east":   ("tokyo", "92435119"),
    "mimaru-tokyo-ikebukuro":      ("tokyo", "99965689"),
    "mimaru-tokyo-ueno-east":      ("tokyo", "21864150"),
    "mimaru-tokyo-ginza-east":     ("tokyo", "47990998"),
    "mimaru-tokyo-shinjuku-west":  ("tokyo", "54552657"),
    "tokyu-stay-shinjuku":         ("tokyo", "2509720"),
    "citadines-shinjuku-tokyo":    ("tokyo", "1683450"),
    "oakwood-premier-tokyo":       ("tokyo", "4641981"),
    "ascott-marunouchi-tokyo":     ("tokyo", "7358772"),
    "keio-plaza-hotel-tokyo":      ("tokyo", "994639"),
    "hilton-tokyo-bay":            ("tokyo", "926340"),
    "grand-nikko-tokyo-bay-maihama": ("tokyo", "60644549"),
}


def trip_hotel_url(hotel_slug: str, sub1: str = DEFAULT_SUB1) -> str:
    """TRIP_HOTELS に登録済みホテルの Trip.com deep link を返す。

    京都・大阪のページを作るときは、そのホテルの都市スラッグ（kyoto / osaka）付きで
    TRIP_HOTELS に追加すれば、パスは自動でその都市になる。
    """
    if hotel_slug not in TRIP_HOTELS:
        raise KeyError(
            "Trip.com のホテルIDが未登録: %s（IDは推測せず、アフィリエイトリンクツールの発行値を使う）"
            % hotel_slug)
    city, hotel_id = TRIP_HOTELS[hotel_slug]
    return ("https://www.trip.com/hotels/%s-hotel-detail-%s/%s/"
            "?Allianceid=%s&SID=%s&trip_sub1=%s&trip_sub3=%s"
            % (city, hotel_id, hotel_slug, ALLIANCE_ID, SID, sub1, SUB3))


def rates_link(hotel_slug: str, label: str = "See rates", sub1: str = DEFAULT_SUB1) -> str:
    """「See rates」用の <a>。rel は sponsored nofollow noopener を必ず付ける。"""
    return ('<a href="%s" rel="sponsored nofollow noopener" target="_blank">%s</a>'
            % (trip_hotel_url(hotel_slug, sub1).replace("&", "&amp;"), label))


def _selftest() -> int:
    """外部依存なしの回帰テスト。手組みページに実在するURLと1件突き合わせる。"""
    fails = []
    if len(TRIP_HOTELS) != 13:
        fails.append("TRIP_HOTELS の件数が13ではない: %d" % len(TRIP_HOTELS))
    for slug, (city, hid) in TRIP_HOTELS.items():
        if not hid.isdigit():
            fails.append("ホテルIDが数値でない: %s -> %s" % (slug, hid))
        if not city.isalpha():
            fails.append("都市スラッグが不正: %s -> %s" % (slug, city))

    expected = ("https://www.trip.com/hotels/tokyo-hotel-detail-100383864/mimaru-suites-tokyo-asakusa/"
                "?Allianceid=10447753&SID=330435547&trip_sub1=hotels-tokyo&trip_sub3=D19699311")
    got = trip_hotel_url("mimaru-suites-tokyo-asakusa")
    if got != expected:
        fails.append("URL組み立てが実ページと一致しない:\n  expected %s\n  got      %s" % (expected, got))

    a = rates_link("hilton-tokyo-bay")
    for needed in ('rel="sponsored nofollow noopener"', "Allianceid=10447753", "&amp;"):
        if needed not in a:
            fails.append("rates_link に %s が無い" % needed)

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
    print("affiliates selftest: Trip.com %d軒のリンク組み立て OK" % len(TRIP_HOTELS))
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_selftest() if "--selftest" in _sys.argv else 0)
