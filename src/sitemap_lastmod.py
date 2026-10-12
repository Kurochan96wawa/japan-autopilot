"""sitemap.xml の <lastmod> を「本文が実際に変わった日」に固定する。

2026-10-12 実測: 本番 sitemap の全96URLの lastmod が、生成のたびにその日の日付で上書きされていた
（site._write_seo_files / seo_fixups / quality_fixups / webstory がそれぞれ today を書く）。
毎日動く lastmod は Google に信用されなくなる。

方式: ページごとに「本文」のハッシュを state.json["sitemap_lastmod"] に保存し、
前回と同じなら前回の lastmod を据え置き、変わっていたら今日にする。
  * 本文 = <main> の中（無ければ <body>）から header/nav/footer/script/style/コメントと
    日付表記（"Last updated: …" 等）を除いたもの。毎run変わる部分でハッシュが動かないようにする。
  * 保存先が state.json なのは、daily.yml が data/ のうち state.json しかコミットしないため
    （data/ 直下の別ファイルだと次のrunで消え、毎回「初回」扱いになる）。
  * daily は quality_fixups の後に facts_fixups が本文を触り、その後 webstory で再度この処理が走る。
    1runの中で同じページのハッシュが2通り出るので、直近のハッシュを数個覚えておき、
    そのどれかと一致すれば「変化なし」とみなす（でないと毎日 lastmod が進む）。

呼び出し: quality_fixups.main / webstory.main の最後（各workflowで docs/ を触る最終段）。
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime, timezone

from .state import load_state, save_state
from .util import SITE_DIR, log

STATE_KEY = "sitemap_lastmod"
_KEEP_HASHES = 4

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
           "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
_DATE_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"),
    re.compile(r"\b(?:" + _MONTHS + r")\.? \d{1,2}, \d{4}"),
    re.compile(r"\b\d{1,2} (?:" + _MONTHS + r")\.? \d{4}"),
    re.compile(r"\d{4}/\d{1,2}/\d{1,2}"),
]
_STRIP_BLOCKS = [
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"<script\b.*?</script>", re.S | re.I),
    re.compile(r"<style\b.*?</style>", re.S | re.I),
    re.compile(r"<header\b.*?</header>", re.S | re.I),
    re.compile(r"<nav\b.*?</nav>", re.S | re.I),
    re.compile(r"<footer\b.*?</footer>", re.S | re.I),
]


def body_hash(html: str) -> str:
    """毎run変わる部分（ナビ・フッター・スクリプト・日付表示）を除いた本文のハッシュ。"""
    m = re.search(r"<main\b[^>]*>(.*)</main>", html, re.S | re.I)
    if not m:
        m = re.search(r"<body\b[^>]*>(.*)</body>", html, re.S | re.I)
    body = m.group(1) if m else html
    for pat in _STRIP_BLOCKS:
        body = pat.sub("", body)
    for pat in _DATE_PATTERNS:
        body = pat.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _rel_from_loc(loc: str) -> str:
    """https://littletabi.com/x → x / ルート → index（store のキー兼ファイル名）。"""
    path = re.sub(r"^https?://[^/]+/?", "", loc).split("#")[0].split("?")[0]
    path = path.removesuffix(".html").strip("/")
    return path or "index"


def lookup(loc: str, default: str) -> str:
    """保存済みの lastmod を返す（更新はしない）。sitemap を最初に書く site.py 用。"""
    try:
        rec = (load_state().get(STATE_KEY) or {}).get(_rel_from_loc(loc))
    except Exception:
        rec = None
    return rec.get("lastmod", default) if isinstance(rec, dict) else default


def stabilize() -> int:
    """docs/sitemap.xml の全 <lastmod> を本文ハッシュに基づいて付け直す。変更したURL数を返す。"""
    sm_path = SITE_DIR / "sitemap.xml"
    if not sm_path.exists():
        return 0
    xml = sm_path.read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).date().isoformat()
    state = load_state()
    before = state.get(STATE_KEY) or {}
    store = {k: dict(v) for k, v in before.items() if isinstance(v, dict)}   # 比較用に元は残す
    bumped = []

    def _fix(m: re.Match) -> str:
        loc = m.group(2)
        rel = _rel_from_loc(loc)
        page = SITE_DIR / f"{rel}.html"
        if not page.exists():
            return m.group(0)
        try:
            digest = body_hash(page.read_text(encoding="utf-8"))
        except Exception:
            return m.group(0)
        rec = store.get(rel) if isinstance(store.get(rel), dict) else {}
        hashes = list(rec.get("hashes") or [])
        lastmod = rec.get("lastmod")
        if not lastmod or digest not in hashes:
            lastmod = today
            bumped.append(rel)
        if digest in hashes:
            hashes.remove(digest)
        store[rel] = {"lastmod": lastmod, "hashes": ([digest] + hashes)[:_KEEP_HASHES]}
        return f"{m.group(1)}{lastmod}{m.group(3)}"

    new = re.sub(r"(<loc>([^<]+)</loc>\s*<lastmod>)[^<]*(</lastmod>)", _fix, xml)
    # ファイルが消えたページの記録は捨てる（store を肥大させない）
    for rel in [k for k in store if not (SITE_DIR / f"{k}.html").exists()]:
        del store[rel]
    if before != store:
        state[STATE_KEY] = dict(sorted(store.items()))
        save_state(state)
    if new != xml:
        sm_path.write_text(new, encoding="utf-8")
    log.info("sitemap_lastmod: lastmod固定 (本文変化=%d件%s)", len(bumped),
             (": " + ", ".join(bumped[:8]) + ("…" if len(bumped) > 8 else "")) if bumped else "")
    return len(bumped)


if __name__ == "__main__":
    stabilize()
