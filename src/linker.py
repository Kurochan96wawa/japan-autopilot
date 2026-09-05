# -*- coding: utf-8 -*-
"""トピッククラスタに基づき、記事本文末へ『関連ガイド』を自動挿入。
孤立ページ（記事間リンクなし）を解消し、回遊と主題権威を作る。標準ライブラリ＋PyYAMLのみ。"""
from __future__ import annotations
import json
import os
import re

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
            clusters = yaml.safe_load(f) or {}
    except Exception:
        return {}
    # 2026-09-05: 新記事は定義上 clusters.yaml に無いため、ci_assert ⑨（未分類ゼロ）が
    # 「新記事を書くたびに必ず失敗」していた（daily-post #89〜#92 が4連続で exit 1、
    # 生成した記事はコミットされず毎回捨てられた）。ここで未分類slugを自動分類して
    # yaml に追記し、ハブ掲載・関連リンク・ci_assert がすべて同じ設定を見るようにする。
    try:
        clusters = auto_assign(clusters, path=path)
    except Exception:
        pass
    return clusters


# ---- 未分類記事の自動クラスタ分類 -----------------------------------------
# slug のトークン（"-"区切り）で決める決定的ルール。上から順に最初に当たったクラスタ。
# 例: best-family-hotels-tokyo → accommodation（tokyo で attractions に落ちる前に hotel が当たる）
_AUTO_ORDER = ["accommodation", "food", "baby", "transport", "practical", "attractions"]
_AUTO_TOKENS = {
    "accommodation": {"hotel", "hotels", "ryokan", "ryokans", "onsen", "onsens", "stay", "stays",
                      "accommodation", "accommodations", "airbnb", "hostel", "hostels",
                      "minshuku", "lodging", "inn", "inns", "resort", "resorts"},
    "food": {"food", "foods", "eat", "eating", "meal", "meals", "ramen", "sushi", "snack", "snacks",
             "cafe", "cafes", "restaurant", "restaurants", "konbini", "breakfast", "dining", "picky",
             "eaters", "allergy", "allergies", "allergic", "vegetarian", "vegan", "halal", "izakaya",
             "bento", "dessert", "desserts", "drinks"},
    "baby": {"baby", "babies", "diaper", "diapers", "formula", "carrier", "carriers", "infant",
             "infants", "newborn", "newborns", "nursing", "breastfeeding", "jet", "lag", "packing",
             "pack", "crib", "cribs", "potty", "sleep", "naps", "nap"},
    "transport": {"shinkansen", "train", "trains", "rail", "railway", "transport", "transit",
                  "stroller", "strollers", "car", "cars", "rental", "renting", "airport", "airports",
                  "flight", "flights", "flying", "fly", "narita", "haneda", "luggage", "baggage",
                  "hands", "taxi", "taxis", "bus", "buses", "journey", "journeys", "subway", "metro",
                  "pass", "passes", "driving", "ferry", "ferries", "forwarding", "suitcase", "suitcases"},
    # practical は「強い語」だけ先に見る（tokyo-esim-guide が attractions に落ちないように）。
    # 当たらなければ最後の既定値としても practical に落ちる。
    "practical": {"esim", "esims", "sim", "wifi", "money", "cash", "currency", "yen", "phrases",
                  "phrase", "health", "healthcare", "medical", "sick", "illness", "emergency",
                  "emergencies", "insurance", "pharmacy", "pharmacies", "doctor", "doctors",
                  "hospital", "hospitals", "tax", "visa", "earthquake", "typhoon",
                  "checklist", "budget", "budgeting", "apps", "app", "translation", "connected"},
    "attractions": {"disney", "disneyland", "disneysea", "universal", "usj", "museum", "museums",
                    "park", "parks", "ghibli", "temple", "temples", "shrine", "shrines", "nara",
                    "trip", "trips", "osaka", "kyoto", "tokyo", "hakone", "hiroshima", "okinawa",
                    "sapporo", "hokkaido", "nikko", "kamakura", "fuji", "itinerary", "itineraries",
                    "gacha", "summer", "winter", "spring", "autumn", "culture", "cultural",
                    "aquarium", "aquariums", "zoo", "zoos", "playground", "playgrounds",
                    "sightseeing", "activities", "activity", "attractions", "things", "festival",
                    "festivals", "heat", "beach", "beaches", "ski", "skiing", "snow", "teamlab",
                    "pokemon", "sanrio", "puroland", "legoland", "kidzania", "onsen"},
}
_AUTO_SKIP_PREFIX = ("japan-with-kids-",)          # カテゴリハブ
_AUTO_SKIP = {"404", "index", "about", "contact", "privacy", "disclosure", "how-we-make-guides",
              "plan", "get-the-japan-checklist", "thanks", "thank-you"}


def classify_slug(slug: str) -> str:
    """slug からクラスタ名を決める。どれにも当たらなければ practical。"""
    toks = set(t for t in slug.lower().split("-") if t)
    for name in _AUTO_ORDER:
        if toks & _AUTO_TOKENS[name]:
            return name
    return "practical"


def _candidate_slugs(state_path: str = "data/state.json", docs_dir: str = "docs") -> list:
    """分類対象＝公開済み記事（state.posted）＋ docs 直下の記事HTML。静的ページ・ハブ・301済みは除外。"""
    out = []
    try:
        with open(state_path, encoding="utf-8") as f:
            st = json.load(f)
        out += [p["slug"] for p in st.get("posted", []) if p.get("slug")]
    except Exception:
        pass
    try:
        out += [fn[:-5] for fn in os.listdir(docs_dir) if fn.endswith(".html")]
    except Exception:
        pass
    seen, res = set(), []
    for s in out:
        if (not s or s in seen or s in _AUTO_SKIP or s in REDIRECT_MAP
                or s.startswith(_AUTO_SKIP_PREFIX)):
            continue
        seen.add(s); res.append(s)
    return res


def _append_member_text(text: str, name: str, slug: str, note: str) -> str:
    """clusters.yaml のテキストに、クラスタ name の members 末尾へ slug を追記する。
    yaml.dump で書き戻すとコメント（設計意図の記録）が全部消えるので、テキストで扱う。"""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^%s:\s*$" % re.escape(name), l)), None)
    if start is None:                      # クラスタ自体が無ければ末尾に新設
        lines += ["%s:" % name, "  members:", "    - %s%s" % (slug, note)]
        return "\n".join(lines) + "\n"
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\S", lines[i])), len(lines))
    mem = next((i for i in range(start + 1, end) if re.match(r"^  members:\s*$", lines[i])), None)
    if mem is None:
        lines[end:end] = ["  members:", "    - %s%s" % (slug, note)]
        return "\n".join(lines) + "\n"
    last = mem
    for i in range(mem + 1, end):
        if re.match(r"^    - ", lines[i]):
            last = i
    lines.insert(last + 1, "    - %s%s" % (slug, note))
    return "\n".join(lines) + "\n"


def auto_assign(clusters: dict, path: str = "config/clusters.yaml",
                state_path: str = "data/state.json", docs_dir: str = "docs", write: bool = True) -> dict:
    """未分類の記事slugをクラスタへ自動追加し、変更があれば yaml へ追記して返す（冪等）。"""
    assigned = set(_index(clusters))
    added = []
    for slug in _candidate_slugs(state_path, docs_dir):
        if slug in assigned:
            continue
        name = classify_slug(slug)
        clusters.setdefault(name, {}).setdefault("members", [])
        if clusters[name]["members"] is None:
            clusters[name]["members"] = []
        clusters[name]["members"].append(slug)
        assigned.add(slug); added.append((name, slug))
    if added and write and os.path.exists(path):
        import datetime
        note = "   # auto-assigned %s" % datetime.date.today().isoformat()
        text = open(path, encoding="utf-8").read()
        for name, slug in added:
            text = _append_member_text(text, name, slug, note)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return clusters


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


def _selftest() -> int:
    """既存の手動分類との一致率と、追記の冪等性を検査する。0=OK / 1=NG"""
    import tempfile, shutil
    cl = load_clusters()
    idx = _index(cl)
    manual = {s: n for s, n in idx.items()}
    agree = sum(1 for s, n in manual.items() if classify_slug(s) == n)
    rate = agree / max(1, len(manual))
    print("classify_slug agreement with manual clusters: %d/%d = %.0f%%" % (agree, len(manual), rate * 100))
    for s, n in sorted(manual.items()):
        if classify_slug(s) != n:
            print("  differs: %s  manual=%s auto=%s" % (s, n, classify_slug(s)))
    ok = rate >= 0.85
    # 追記の冪等性: 仮slugを1回追記→2回目は変化なし
    tmp = tempfile.mkdtemp()
    try:
        shutil.copy("config/clusters.yaml", os.path.join(tmp, "c.yaml"))
        st = os.path.join(tmp, "state.json")
        with open(st, "w", encoding="utf-8") as f:
            json.dump({"posted": [{"slug": "ghibli-museum-park-2026-with-kids-tickets-what-to-expect"},
                                  {"slug": "flying-to-japan-with-kids-narita-haneda-airport-arrival-guide"}]}, f)
        p = os.path.join(tmp, "c.yaml")
        c1 = auto_assign(yaml.safe_load(open(p, encoding="utf-8")), path=p, state_path=st, docs_dir=tmp)
        t1 = open(p, encoding="utf-8").read()
        c2 = auto_assign(yaml.safe_load(open(p, encoding="utf-8")), path=p, state_path=st, docs_dir=tmp)
        t2 = open(p, encoding="utf-8").read()
        i1 = _index(c1)
        print("auto: ghibli ->", i1.get("ghibli-museum-park-2026-with-kids-tickets-what-to-expect"),
              "/ narita ->", i1.get("flying-to-japan-with-kids-narita-haneda-airport-arrival-guide"))
        ok &= (i1.get("ghibli-museum-park-2026-with-kids-tickets-what-to-expect") == "attractions")
        ok &= (i1.get("flying-to-japan-with-kids-narita-haneda-airport-arrival-guide") == "transport")
        ok &= (t1 == t2) and (yaml.safe_load(t2) == c2)
        print("idempotent:", t1 == t2, "/ yaml parses:", yaml.safe_load(t2) is not None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("linker selftest:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest() if "--selftest" in sys.argv else 0)
