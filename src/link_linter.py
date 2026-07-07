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
    for f in sorted(glob.glob(os.path.join(DOCS, "*.html"))):
        yield f


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
        if any("booking.com" in h for h in hrefs) and TP_MARKER not in html:
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
    sys.exit(main())
