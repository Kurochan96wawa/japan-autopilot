# -*- coding: utf-8 -*-
"""施策3-2: 収益リンクのリンター（CI必須チェック・fail-closed）。

docs/ を走査し、収益に直結する壊れ方を検出する。重大(FAIL)が1件でもあれば
非ゼロ終了し、daily.yml のこのステップでワークフローを止める＝未収益化リンクを
デプロイさせない（既存の fail-safe 方針の"例外"。指示書§3-2）。

設計メモ:
* Booking は aid= ではなく Travelpayouts のページ内スクリプト(marker 544191)で
  自動アフィリ化される（config/affiliates.yaml, site._tpdrive_snippet）。よって
  「booking.com リンクがあるのに TP スクリプトが無いページ」を FAIL とする。
* Klook アフィリリンクは aid=125283 を必須にする（欠落は FAIL）。
* アフィリリンクの rel="sponsored nofollow" 欠落は WARN、301統合先への内部リンクは FAIL。
* 標準ライブラリのみ（追加依存なし）。

実行: `python -m src.link_linter`（daily.yml の fixups 後・commit 前に配置）。
"""
from __future__ import annotations
import glob
import os
import re
import sys

DOCS = "docs"
TP_MARKER = "544191"            # Travelpayouts marker（site._tpdrive_snippet が全ページに出力）
KLOOK_HOST = "affiliate.klook.com"
KLOOK_AID = "aid=125283"

# 301統合済みで内部リンクを禁止したい旧slug（現状は canonical のみ。301化後に追記）。
REDIRECTED_SLUGS = {
    "buying-baby-diapers-wipes-and-formula-in-japan-2026",
    "diapers-formula-in-japan-brands-sizes-where-to-buy",
    "tokyo-disney-vs-disneysea-for-kids",
    "navigating-japan-s-public-transport-with-kids-2026",
    "tokyo-family-hotels-connecting-rooms-kitchenettes",
}

_A_HREF = re.compile(r"""<a\b[^>]*?href=["']([^"']*)["'][^>]*>""", re.I)
_A_FULL = re.compile(r"""<a\b([^>]*?)href=["']([^"']*)["']([^>]*)>""", re.I)


def _pages():
    for f in sorted(glob.glob(os.path.join(DOCS, "**", "*.html"), recursive=True)):
        yield f


def _booking_unmonetised(html: str) -> bool:
    """booking.com リンク（<a> でも JS 変数内でも）があるのに TP スクリプトが無い＝未収益化。
    plan.html は AFF.hotels の JS 変数内に素の booking リンクを持つため、<a href> だけを
    見る旧実装ではすり抜けた（2026-07-10 中間レビュー #1/#構造）。ページ本文全体で判定する。"""
    return ("booking.com" in html) and (TP_MARKER not in html)


def lint():
    """(fails, warns) を返す。fails が1件でもあれば CI を止める。"""
    fails, warns = [], []
    for path in _pages():
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
        except Exception:
            continue

        hrefs = _A_HREF.findall(html)

        # 1) booking.com リンクがあるのに TP スクリプトが無い＝未収益化（FAIL）
        if _booking_unmonetised(html):
            fails.append(name + ": booking.com link present but no Travelpayouts script "
                         "(marker " + TP_MARKER + ") -> not monetised")

        # 2) Klook アフィリリンクに aid= が無い（FAIL）
        for h in hrefs:
            if KLOOK_HOST in h and KLOOK_AID not in h:
                fails.append(name + ": Klook affiliate link missing " + KLOOK_AID + ": " + h[:80])

        # 3) アフィリリンクに rel="sponsored nofollow" が不足（WARN）
        for m in _A_FULL.finditer(html):
            attrs = (m.group(1) or "") + (m.group(3) or "")
            href = m.group(2) or ""
            if ("booking.com" in href) or (KLOOK_HOST in href):
                rel = ""
                rm = re.search(r"""rel=["']([^"']*)["']""", attrs)
                if rm:
                    rel = rm.group(1)
                if "sponsored" not in rel or "nofollow" not in rel:
                    warns.append(name + ": affiliate link missing rel=\"sponsored nofollow\": " + href[:70])

        # 4) 301統合済み旧ページへの内部リンク（301化後に有効・FAIL）
        for slug in REDIRECTED_SLUGS:
            if re.search(r"""href=["']/?""" + re.escape(slug) + r"""\.html["']""", html):
                fails.append(name + ": internal link to redirected page " + slug + ".html")

    return fails, warns


def _selftest() -> int:
    """回帰テスト: plan.html 型のすり抜け（JS変数内 booking リンク＋TPスクリプト無し）を
    リンターが未収益化として検出できることを確認。2026-07-10 中間レビュー #1/#構造 再発防止。"""
    plan_broken = (
        '<head><title>Planner</title></head><body>\n'
        '<script>var AFF={hotels:"https://www.booking.com/searchresults.html?ss=Japan"};\n'
        '</script></body>'
    )
    plan_fixed = plan_broken.replace(
        "</head>",
        '<script>s.src="//tpembars.com/NTQ0MTkx.js?t=' + TP_MARKER + '"</script></head>')
    cases = [
        ("plan.html 未修正(素のbookingのみ)", plan_broken, True),
        ("plan.html 修正後(TPスクリプト有り)", plan_fixed, False),
    ]
    bad = 0
    for name, html, want_unmonetised in cases:
        got = _booking_unmonetised(html)
        ok = (got == want_unmonetised)
        if not ok:
            bad += 1
        print("selftest[%s]: expect_unmonetised=%s got=%s -> %s" % (
            name, want_unmonetised, got, "OK" if ok else "MISMATCH"))
    if bad:
        print("link_linter selftest FAILED: %d case(s)" % bad)
        return 1
    print("link_linter selftest: all cases pass")
    return 0


def main() -> int:
    fails, warns = lint()
    for w in warns:
        print("WARN:", w)
    for f in fails:
        print("FAIL:", f)
    print("link_linter: FAIL=%d WARN=%d" % (len(fails), len(warns)))
    if fails:
        print("Revenue-link violations found. Blocking deploy (fail-closed).")
        return 1
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
