"""ビルド後アサーション（復旧スプリントC C-5・fail-closed）。

2026年8月の事故は「生成は成功したのに、ユーザーに見える資産が静かに消えた」形で起きた。
ビルドが緑でも中身が壊れていることがある以上、ワークフローの最後に
「これが無ければ失敗にする」という明示的な検査を置く。1つでも欠けたら exit 1。

実行: `python -m src.ci_assert`（daily.yml / weekly-improve.yml の最終ステップ）
"""
from __future__ import annotations
import pathlib
import re
import sys

from . import linker
from .quality_fixups import STATIC_PAGES
from .util import SITE_DIR

MONEY_PAGE = "best-family-hotels-tokyo-connecting-rooms.html"
MUST_EXIST = (
    "index.html",
    "plan.html",
    "sitemap.xml",
    "_redirects",
    "404.html",
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

    # ③ マネーページの収益CTAが生きていること
    #    2026-09-06: Trip.comアフィリエイトが有効化され、ホテルの「See rates」が
    #    未収益のBooking検索URLからTrip.comのdeep linkに替わった。ホテルリンクも
    #    fail-closedの対象に含める（Allianceidが落ちたら収益ゼロで気づけないため）。
    money = _read(MONEY_PAGE)
    if money:
        trip = re.findall(r"https://www\.trip\.com/hotels/[^\"\s]*", money)
        trip_ok = [u for u in trip if "Allianceid=" in u]
        n = len(re.findall(r"https://tp\.media/r\?", money)) + \
            len(re.findall(r"https://affiliate\.klook\.com/", money)) + len(trip_ok)
        if n < 3:
            fails.append("マネーページの稼働CTAが%d本しかない（3本以上必要）: %s" % (n, MONEY_PAGE))
        if trip and len(trip_ok) != len(trip):
            fails.append("マネーページのTrip.comリンク%d本のうち%d本にAllianceidが無い（未収益）: %s"
                         % (len(trip), len(trip) - len(trip_ok), MONEY_PAGE))

    # ④ plan.html のTravelpayouts埋め込み（これが無いとbookingリンクが無収益になる）
    plan = _read("plan.html")
    if plan and "tpembars.com" not in plan:
        fails.append("plan.html に Travelpayouts の埋め込みスクリプトが無い")

    # ⑤ sitemap に主要ツールが載っていること
    sm = _read("sitemap.xml")
    for rel in ("shinkansen-family-fare-calculator", "tools/allergy-card"):
        # 2026-09-06: sitemapのlocは拡張子なし。`<loc>...</loc>` で完全一致を見る
        # （部分一致だと別slugの前方一致を拾って素通りする）
        if ("/" + rel + "</loc>") not in sm:
            fails.append("sitemapに載っていない: " + rel)

    # ⑥ 301統合の整合（_redirects が全slugを網羅し、統合済みslugが再露出していないこと）
    red = _read("_redirects")
    idx = _read("index.html")
    # 2026-09-06: 公開URLは拡張子なしに統一したので、内部リンク/ sitemap も拡張子なしで見る。
    idx_links = set(re.findall(r'href="/([a-z0-9\-./]*)"', idx))
    sm_urls = set(re.findall(r"<loc>[^<]*?littletabi\.com/([^<]*)</loc>", sm))
    for slug in sorted(linker.REDIRECT_MAP):
        # _redirects は「.html 付き / なし」の両方を残す（既にインデックスされた旧URLの救済）
        if ("/" + slug + ".html") not in red or ("/" + slug + " ") not in red:
            fails.append("_redirects に301行が無い（.htmlあり/なしの両方が必要）: " + slug)
        if slug in idx_links:
            fails.append("301統合済みslugがトップページに再露出: " + slug)
        if slug in sm_urls or ("stories/" + slug) in sm_urls:
            fails.append("301統合済みslugがsitemapに再露出: " + slug)

    # ⑦ 検索スニペットの整合（2026-08の実バグの再発防止）
    #    seo.py の正規表現ミスで <meta name="description"> だけが更新されず、
    #    og:description との食い違いが約2ヶ月放置された。Googleがスニペットに使うのは
    #    前者なので、SEO改善が丸ごと無効化されていた。以後は食い違いをビルド失敗にする。
    #    手組みページ（plan / assets/pages 由来）は文面を別管理しているため対象外。
    snippet_exempt = set(STATIC_PAGES) | {"plan.html"}
    for path in sorted(SITE_DIR.glob("*.html")):
        if path.name in snippet_exempt:
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        d = re.search(r'<meta name="description" content="([^"]*)"', html)
        o = re.search(r'<meta property="og:description" content="([^"]*)"', html)
        if d and o and d.group(1) != o.group(1):
            fails.append("description と og:description が食い違っている（検索スニペットが古いまま）: " + path.name)
        if d and not d.group(1).strip():
            fails.append("meta description が空: " + path.name)

    # ⑧ 404ページ（soft-404の再発防止）
    #    404.html が無いと Cloudflare Pages は未一致URLにトップページを 200 で返し、
    #    存在しないURLの数だけ重複コンテンツが生える（2026-08-22 に実測）。
    nf = _read("404.html")
    if nf and "noindex" not in nf:
        fails.append("404.html に noindex が無い（誤ってインデックスされる）")

    # ⑨ クラスタ設定の健全性（内部リンクがマネーページに流れなくなる事故の再発防止）
    #    2026-08-22 実測: clusters.yaml が統合前(301済み)のslugを pillar/member に持ったままで、
    #    related() がそれを除外していたため、統合先の本物のマネーページには内部リンクが
    #    1本も張られていなかった（ホテル1本・ディズニー0本・eSIM 0本）。
    #    実在41本のうち17本が未分類でもあった。設定と実体のズレをビルド失敗にする。
    try:
        import yaml
        cl = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent
                             / "config" / "clusters.yaml").read_text(encoding="utf-8")) or {}
    except Exception as e:
        fails.append("clusters.yaml を読めない: %s" % e)
        cl = {}
    assigned = set()
    for name, c in (cl or {}).items():
        entries = [c.get("pillar")] + list(c.get("members") or [])
        for slug in [e for e in entries if e]:
            assigned.add(slug)
            if slug in linker.REDIRECT_MAP:
                fails.append("clusters.yaml が301統合済みslugを指している（内部リンクが統合先に流れない）: "
                             "%s → %s" % (name, slug))
            elif not (SITE_DIR / (slug + ".html")).exists():
                fails.append("clusters.yaml が存在しないページを指している: %s → %s" % (name, slug))
    skip = {"404", "index", "about", "contact", "privacy", "disclosure",
            "how-we-make-guides", "plan", "get-the-japan-checklist"}
    for path in sorted(SITE_DIR.glob("*.html")):
        stem = path.stem
        if stem in skip or stem.startswith("japan-with-kids-") or stem in linker.REDIRECT_MAP:
            continue
        if stem not in assigned:
            fails.append("clusters.yaml に未分類の記事がある（関連リンクが張られない）: " + stem)

    # ⑩ meta description の重複（カテゴリハブが同じ説明文を共有する事故の再発防止）
    #    2026-08-22 実測: _static_page が全ページ TAGLINE 固定だったため、カテゴリハブ6本を
    #    含む12ページが同一の meta description を持っていた。カテゴリ系クエリで拾うべき
    #    ページの説明文が全部同じ、という状態。noindex のページは対象外。
    seen_desc = {}
    for path in sorted(SITE_DIR.glob("*.html")):
        html = _read(path.name)
        rb = re.search(r'<meta name="robots" content="([^"]*)"', html)
        if rb and "noindex" in rb.group(1):
            continue
        if path.stem in linker.REDIRECT_MAP:
            continue
        dm = re.search(r'<meta name="description" content="([^"]*)"', html)
        if not dm or not dm.group(1).strip():
            fails.append("meta description が無い: " + path.name)
            continue
        key = dm.group(1).strip()
        if key in seen_desc:
            fails.append("meta description が %s と重複している: %s" % (seen_desc[key], path.name))
        else:
            seen_desc[key] = path.name

    # ⑪ 拡張子なしURLの一貫性（2026-09-06 の移行の再発防止）
    #    Cloudflare Pages は /x.html を /x へ308で正規化する。canonical や内部リンクが
    #    .html のままだと「正規URLがリダイレクトされるURL」になり、内部リンクは1本ごとに
    #    無駄な1ホップを踏む。生成側を直しても、fixupの追記で1本混ざれば元の木阿弥なので
    #    ここで見張る。docs/ 配下の実ファイル名は .html のままで正しい（URLだけの話）。
    bad_links, bad_canon = [], []
    for path in sorted(SITE_DIR.rglob("*.html")):
        html = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'(?:href|src)="/[A-Za-z0-9\-_./]+\.html[""#?]', html):
            bad_links.append(path.name)
        if re.search(r'<link rel="canonical"[^>]*littletabi\.com/[^"]*\.html"', html):
            bad_canon.append(path.name)
        if re.search(r'<meta property="og:url"[^>]*littletabi\.com/[^"]*\.html"', html):
            bad_canon.append(path.name)
    if bad_links:
        fails.append("内部リンクに .html が残っている（308リダイレクトを毎回踏む）: %s%s"
                     % (", ".join(sorted(set(bad_links))[:5]),
                        " ほか%dページ" % (len(set(bad_links)) - 5) if len(set(bad_links)) > 5 else ""))
    if bad_canon:
        fails.append("canonical/og:url に .html が残っている（正規URLがリダイレクト先を指す）: %s%s"
                     % (", ".join(sorted(set(bad_canon))[:5]),
                        " ほか%dページ" % (len(set(bad_canon)) - 5) if len(set(bad_canon)) > 5 else ""))

    # 外部サービスへ渡すURL（Pinterest共有リンク等）に .html が混ざっていないこと。
    # これは canonical と一致しないと保存されたピンが毎回308を踏む。
    bad_share = []
    for path in sorted(SITE_DIR.rglob("*.html")):
        html = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"pinterest\.com/pin/create/button/\?url=[^\"']*\.html", html):
            bad_share.append(path.name)
        # JSON-LD が指す自サイトURL（contentUrl / url / mainEntityOfPage）も canonical と揃える
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            if re.search(r'https://littletabi\.com/[A-Za-z0-9\-_./]+\.html', m.group(1)):
                bad_share.append(path.name)
    if bad_share:
        fails.append("Pinterest共有URLに .html が残っている（canonicalと不一致）: %s"
                     % ", ".join(sorted(set(bad_share))[:5]))

    # sitemap の loc も拡張子なしであること
    sm_html = re.findall(r"<loc>[^<]*\.html</loc>", sm)
    if sm_html:
        fails.append("sitemapのlocに .html が %d件残っている（例: %s）" % (len(sm_html), sm_html[0]))

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
