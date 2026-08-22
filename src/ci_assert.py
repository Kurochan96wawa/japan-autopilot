"""ビルド後アサーション（復旧スプリントC C-5・fail-closed）。

2026年8月の事故は「生成は成功したのに、ユーザーに見える資産が静かに消えた」形で起きた。
ビルドが緑でも中身が壊れていることがある以上、ワークフローの最後に
「これが無ければ失敗にする」という明示的な検査を置く。1つでも欠けたら exit 1。

実行: `python -m src.ci_assert`（daily.yml / weekly-improve.yml の最終ステップ）
"""
from __future__ import annotations
import re
import sys

from . import linker
from .util import SITE_DIR

MONEY_PAGE = "best-family-hotels-tokyo-connecting-rooms.html"
MUST_EXIST = (
    "index.html",
    "plan.html",
    "sitemap.xml",
    "_redirects",
    "tools/allergy-card.html",
    "shinkansen-family-fare-calculator.html",
    "shinkansen-cost-for-families.html",
    "eating-out-in-japan-with-food-allergies.html",
)


def _read(rel: str) -> str:
    p = SITE_DIR / rel
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def run() -> list:
    fails = []

    # ① 重要ページの実体があること（2026-08: 計算機と記事2本が丸ごと消えた）
    for rel in MUST_EXIST:
        if not (SITE_DIR / rel).exists():
            fails.append("必須ページが存在しない: docs/" + rel)

    # ② 計算機ページが「計算機のまま」であること
    #    site.rebuild_index のバックフィルがテンプレートで上書きするとUIが消える。
    calc = _read("shinkansen-family-fare-calculator.html")
    if calc:
        if len(re.findall(r"<input", calc)) < 5:
            fails.append("計算機ページの入力フォームが失われている（<input が5未満）")
        if "function calc(" not in calc:
            fails.append("計算機ページの計算スクリプト（function calc）が失われている")

    # ③ マネーページの収益CTAが生きていること（Bookingは未承認＝収益ゼロなので数えない）
    money = _read(MONEY_PAGE)
    if money:
        n = len(re.findall(r"https://tp\.media/r\?", money)) + \
            len(re.findall(r"https://affiliate\.klook\.com/", money))
        if n < 3:
            fails.append("マネーページの稼働CTAが%d本しかない（3本以上必要）: %s" % (n, MONEY_PAGE))

    # ④ plan.html のTravelpayouts埋め込み（これが無いとbookingリンクが無収益になる）
    plan = _read("plan.html")
    if plan and "tpembars.com" not in plan:
        fails.append("plan.html に Travelpayouts の埋め込みスクリプトが無い")

    # ⑤ sitemap に主要ツールが載っていること
    sm = _read("sitemap.xml")
    for rel in ("shinkansen-family-fare-calculator.html", "tools/allergy-card.html"):
        if rel not in sm:
            fails.append("sitemapに載っていない: " + rel)

    # ⑥ 301統合の整合（_redirects が全slugを網羅し、統合済みslugが再露出していないこと）
    red = _read("_redirects")
    idx = _read("index.html")
    idx_links = set(re.findall(r'href="/([a-z0-9\-.]+\.html)"', idx))
    sm_urls = set(re.findall(r"<loc>[^<]*?littletabi\.com/([^<]*)</loc>", sm))
    for slug in sorted(linker.REDIRECT_MAP):
        if ("/" + slug + ".html") not in red:
            fails.append("_redirects に301行が無い: " + slug)
        if (slug + ".html") in idx_links:
            fails.append("301統合済みslugがトップページに再露出: " + slug)
        if (slug + ".html") in sm_urls or ("stories/" + slug + ".html") in sm_urls:
            fails.append("301統合済みslugがsitemapに再露出: " + slug)

    return fails


def main() -> int:
    fails = run()
    for f in fails:
        print("CI-ASSERT FAIL: " + f)
    if fails:
        print("ci_assert: %d 件のリグレッションを検出。デプロイをブロックします。" % len(fails))
        return 1
    print("ci_assert: すべてのアサーションに合格")
    return 0


if __name__ == "__main__":
    sys.exit(main())
