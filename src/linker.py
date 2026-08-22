# -*- coding: utf-8 -*-
"""トピッククラスタに基づき、記事本文末へ『関連ガイド』を自動挿入。
孤立ページ（記事間リンクなし）を解消し、回遊と主題権威を作る。標準ライブラリ＋PyYAMLのみ。"""
from __future__ import annotations
import json
import os

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


# Phase 2-2: カニバリ統合で301した旧slug。related/内部リンクの候補から除外し、
# 統合先へリンクを集約する（サイトマップ・index からの除外は site.py 側で参照）。
# 旧slug -> 統合先slug。ここが単一の正であり、以下すべてがこのmapから導出される:
#   * docs/_redirects (Cloudflare Pages の 301)      … seo_fixups._build_redirects()
#   * <link rel="canonical">                          … seo_fixups._consolidate_canonicals()
#   * sitemap / index からの除外・内部リンク掃除      … site.py
#   * 内部リンクを張ってはいけないslugの検査          … link_linter
REDIRECT_MAP = {
    # Phase 2-2 (PR #18): カニバリ統合4クラスタ
    "buying-baby-diapers-wipes-and-formula-in-japan-2026": "diapers-formula-baby-gear-in-japan-what-to-pack-buy",
    "diapers-formula-in-japan-brands-sizes-where-to-buy": "diapers-formula-baby-gear-in-japan-what-to-pack-buy",
    "tokyo-disney-vs-disneysea-for-kids": "tokyo-disneyland-vs-disneysea-young-kids",
    "navigating-japan-s-public-transport-with-kids-2026": "japan-public-transport-with-kids-fares-strollers-facilities",
    "tokyo-family-hotels-connecting-rooms-kitchenettes": "best-family-hotels-tokyo-connecting-rooms",

    # 復旧スプリントC (2026-08-21): 8月の自動生成期(重複ガード不在)に量産された近接重複。
    # 統合先の選定基準は 内容の充実度 → 内部リンク被リンク数 → URLの検索意図適合。
    # 語数差が10%以内は「同等」とみなし次の基準に送る、という運用で機械的に決めた。
    # 医療・健康 6本 -> 1本（語数2160w・被リンク3・intentが最も広い）
    "family-healthcare-in-japan-what-to-do-for-kids-2026-guide": "japan-healthcare-for-kids-clinics-pharmacies-emergencies-202",
    "accessing-medical-care-in-japan-for-families-2026-what-paren": "japan-healthcare-for-kids-clinics-pharmacies-emergencies-202",
    "child-gets-sick-in-japan-2026-a-practical-parent-s-guide": "japan-healthcare-for-kids-clinics-pharmacies-emergencies-202",
    "family-health-emergencies-in-japan-a-2026-parent-s-guide": "japan-healthcare-for-kids-clinics-pharmacies-emergencies-202",
    "child-sick-in-japan-essential-medical-guide-for-families-202": "japan-healthcare-for-kids-clinics-pharmacies-emergencies-202",
    # 旅館 3本 -> 1本（2129w/被リンク3。2304wの候補とは語数差8%＝同等とみなし被リンクで決定）
    "ryokan-with-kids-family-stays-in-japan-2026-guide": "ryokan-stays-with-kids-in-japan-family-inns-etiquette-2026",
    "staying-in-a-ryokan-with-kids-family-friendly-japan-tips": "ryokan-stays-with-kids-in-japan-family-inns-etiquette-2026",
    # パッキング 2本 -> 1本（語数差9%・被リンク同数のため検索意図の一致で決定）
    "japan-with-kids-2026-the-ultimate-seasonal-packing-list": "japan-packing-list-for-families-2026-kids-travel-essentials",
}

REDIRECTED_SLUGS = set(REDIRECT_MAP)


def resolve(slug: str) -> str:
    """301統合済みのslugなら統合先を返す。それ以外はそのまま。

    2026-08-22: related() が REDIRECTED_SLUGS を単に「除外」していたため、統合した
    クラスタ（accommodation の pillar など）が実質空になり、統合先である本物の
    マネーページには内部リンクが1本も張られていなかった（実測: ホテル1本・ディズニー0本・
    eSIM 0本）。301は「捨てる」ではなく「寄せる」ものなので、張り替えに変更する。
    """
    return REDIRECT_MAP.get(slug, slug)


def load_clusters(path: str = "config/clusters.yaml") -> dict:
    if not yaml or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _index(clusters: dict) -> dict:
    """slug -> cluster名 の逆引き。"""
    idx = {}
    for name, c in (clusters or {}).items():
        for s in [c.get("pillar")] + list(c.get("members", []) or []):
            if s:
                idx[s] = name
    return idx


def cluster_of(slug: str, clusters: dict):
    name = _index(clusters).get(slug)
    return (name, clusters.get(name)) if name else (None, None)


def related(slug: str, clusters: dict, n: int = 3) -> list:
    """同クラスタの兄弟記事n本＋ピラー記事1本。未分類なら practical のピラーへ寄せる。"""
    name, c = cluster_of(slug, clusters)
    if not c:
        # 未分類スラッグは practical クラスタにフォールバック（孤立を作らない）
        c = clusters.get("practical")
        if not c:
            return []
        out = [resolve(s) for s in ([c.get("pillar")] + list(c.get("members", []) or [])) if s]
        out = [s for s in out if s != slug]
        seen, dedup = set(), []
        for s2 in out:
            if s2 not in seen:
                seen.add(s2); dedup.append(s2)
        return dedup[:n + 1]
    sibs = [s for s in (c.get("members", []) or []) if s != slug]
    out = sibs[:n]
    if c.get("pillar") and c["pillar"] != slug:
        out.append(c["pillar"])  # ピラーへ必ず1本＝権威集約
    # 重複除去・順序維持
    seen, dedup = set(), []
    for s in out:
        s = resolve(s)                     # 301済みは統合先へ寄せる（捨てない）
        if s and s != slug and s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup


def load_titles(state_path: str = "data/state.json") -> dict:
    """state.json の posted から slug->title を作る。"""
    try:
        with open(state_path, encoding="utf-8") as f:
            st = json.load(f)
        return {p["slug"]: p.get("article_title", p["slug"])
                for p in st.get("posted", []) if p.get("slug")}
    except Exception:
        return {}


def inject_links(body_html: str, slug: str, clusters: dict, titles: dict) -> str:
    """本文HTML末尾に『関連ガイド』ブロックを付与して返す。"""
    if not body_html:
        return body_html
    links = related(slug, clusters)
    if not links:
        return body_html
    items = "".join(
        f"<li><a href=\"/{s}.html\">{titles.get(s, s.replace('-', ' '))}</a></li>"
        for s in links
    )
    block = (
        "<section class=\"related\"><h2>Related guides</h2>"
        f"<ul>{items}</ul></section>"
    )
    # 既に関連ブロックがあれば二重付与しない（冪等）
    if "class=\"related\"" in body_html:
        return body_html
    return body_html + block
