# -*- coding: utf-8 -*-
"""Phase 2-3b: 既存記事の『場所違い』画像を、都市整合クエリで再取得して同名で上書きする軽量パス。

- LLM を一切呼ばない（本文は触らない。画像ファイルのみ上書き）。
- 対象は下の TARGETS に限定（レビューで場所違いが確認できた閲覧可能ページのみ）。
- images._rank_photos により、記事の都市と矛盾する写真(alt照合)は避けて選ぶ。
- 実行: extras の Generator に 'reimage' を指定（python -m src.reimage）。
"""
from __future__ import annotations
import re

from .util import SITE_DIR, log
from . import images

# 場所違いが確認された閲覧可能ページ（301で隠れる旧slugは対象外）。
TARGETS = [
    "best-family-hotels-tokyo-connecting-rooms",                     # body2=岡崎の桜(愛知) → 東京へ
    "japan-family-itinerary-tokyo-kyoto-osaka-with-young-children",  # body2=静岡駅 → Tokyo/Kyoto/Osaka へ
    "tokyo-disneyland-vs-disneysea-young-kids",                      # body2=道頓堀(大阪) → 東京へ
]

_IMG_RE = re.compile(r"/img/([A-Za-z0-9._-]+\.jpg)")


def _query_for(slug: str) -> str:
    cities = images._cities_in(slug)
    if cities:
        return " ".join(sorted(c.title() for c in cities)) + " Japan family with children"
    return "Japan family travel children"


def _alt_for(want) -> str:
    """差し替え画像の alt を都市整合の汎用文へ。元の場所名(例: Okazaki)が残らないように。"""
    if want:
        place = " and ".join(sorted(c.title() for c in want))
    else:
        place = "Japan"
    return "A family with young children enjoying time in " + place + ", Japan"


def _set_img_alt(html: str, fname: str, new_alt: str) -> str:
    """fname を参照する <img> の alt 属性だけを差し替える(本文は変えない)。"""
    def repl(m):
        tag = m.group(0)
        if 'alt="' in tag:
            return re.sub(r'alt="[^"]*"', 'alt="' + new_alt + '"', tag, count=1)
        return tag
    return re.sub(r'<img[^>]*' + re.escape(fname) + r'[^>]*>', repl, html, count=1)


def _set_img_credit(html: str, fname: str, photographer: str, url: str) -> str:
    """fname を含む <figure> の <figcaption> を、実際に採用した写真のクレジットへ更新する。

    画像だけ差し替えてクレジットを放置すると誤帰属になるため、alt と必ずセットで更新する。
    撮影者が取れない場合は名前を出さず「Photo from Pexels」に落とす（虚偽表示より無表示）。
    """
    if photographer and url:
        cap = ('<figcaption>Photo by <a href="' + url +
               '" rel="nofollow noopener">' + photographer + '</a> on Pexels</figcaption>')
    else:
        cap = "<figcaption>Photo from Pexels</figcaption>"

    # 貪欲マッチが隣の <figure> を巻き込むと別画像のクレジットを壊すため、</figure> を跨がせない。
    inner = r"(?:(?!</figure>).)*?"
    pat = re.compile(r"<figure[^>]*>" + inner + re.escape(fname) + inner + r"</figure>", re.S)

    def repl(m):
        fig = m.group(0)
        if "<figcaption" in fig:
            return re.sub(r"<figcaption>.*?</figcaption>", cap, fig, count=1, flags=re.S)
        return fig.replace("</figure>", cap + "</figure>")

    return pat.sub(repl, html, count=1)


def _take_photo(photos: list, used_ids: set):
    """サイト内でまだ使っていない写真を1枚取り出す（同一写真の使い回しを防ぐ）。"""
    for p in photos:
        pid = p.get("id") or p.get("url")
        if pid in used_ids:
            continue
        used_ids.add(pid)
        return p
    return None


def reimage_slug(slug: str, used_ids: set | None = None) -> int:
    used_ids = used_ids if used_ids is not None else set()
    path = SITE_DIR / (slug + ".html")
    if not path.exists():
        log.info("reimage: skip (no html) %s", slug)
        return 0
    html = path.read_text(encoding="utf-8")
    files = []
    for m in _IMG_RE.finditer(html):
        f = m.group(1)
        # 対象記事自身の画像のみ（他記事サムネの巻き込み防止）
        if f.startswith(slug) and f not in files:
            files.append(f)
    if not files:
        log.info("reimage: no own images %s", slug)
        return 0

    want = images._cities_in(slug)
    query = images._ensure_japan(_query_for(slug))
    photos = images._pexels_photos(query, len(files) + 16, orientation="landscape")
    photos = images._rank_photos(photos, want)
    if not photos:
        log.error("reimage: pexels empty %s (q=%s)", slug, query)
        return 0

    img_dir = SITE_DIR / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for fname in files:
        p = _take_photo(photos, used_ids)
        if p is None:
            log.error("reimage: 未使用の写真が尽きた %s/%s (重複を避けるためスキップ)", slug, fname)
            continue
        try:
            src = p.get("src", {})
            url = src.get("large") or src.get("large2x") or src.get("original")
            base = images._download(url, 1200, 675)
            base.save(img_dir / fname, "JPEG", quality=86)
            n += 1
            if "-body" in fname:
                html = _set_img_alt(html, fname, _alt_for(want))
            html = _set_img_credit(html, fname, p.get("photographer") or "", p.get("url") or "")
            # 検証用: 選んだ写真の alt をログに残す（場所違いが無いか目視できる）
            log.info("reimage %s <- alt=%r photographer=%r", fname, p.get("alt"), p.get("photographer"))
        except Exception as e:
            log.error("reimage失敗 %s/%s: %s", slug, fname, e)
    log.info("reimage: %s の画像%d枚を都市整合で差し替え(query=%s, want=%s)", slug, n, query, sorted(want))
    if n:
        path.write_text(html, encoding="utf-8")
    return n


def run() -> int:
    total = 0
    used_ids: set = set()
    for slug in TARGETS:
        total += reimage_slug(slug, used_ids)
    log.info("reimage完了: 計%d枚", total)
    return total


if __name__ == "__main__":
    run()
