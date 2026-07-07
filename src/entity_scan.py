# -*- coding: utf-8 -*-
"""施策3-1: エンティティ・ホワイトリスト照合スキャナ（レビュー送り方式）。

docs/ の各記事本文から「ホテル名・商品名・ブランド名らしき固有名詞」を抽出し、
facts/entities.yaml に登録済みのエンティティ/既知ブランドと照合する。未登録の候補を
レビュー・レポート（docs/_review/entities-review.json）に書き出す。

設計方針（指示書 §3-1 / §3 冒頭「AI自己採点は自己の捏造を検出できない」）:
  * これは **fail-open（レビュー送り）**。既存の~50記事には未登録の固有名詞が多数あり、
    ここで fail-closed にすると全デプロイが止まるため。ハードなCIブロックは link_linter
    （収益リンク）に限定する（指示書の方針どおり）。
  * 生成パイプライン側（新規記事）には別途 intent_validator と合わせてゲートをかける想定。
  * レポートは週次レビューIssue（3-6 weekly_review.py）が集約して人間に提示する。

標準ライブラリのみ + PyYAML（リポジトリのconfigで既に使用）。
実行: `python -m src.entity_scan`（extras もしくは weekly から）。
"""
from __future__ import annotations
import glob
import json
import os
import re
import sys

DOCS = "docs"
ENTITIES_YAML = os.path.join("facts", "entities.yaml")
REVIEW_DIR = os.path.join(DOCS, "_review")
REVIEW_JSON = os.path.join(REVIEW_DIR, "entities-review.json")

# 記事本文でない出力ページ（ハブ/ツール/法務など）は固有名詞照合の対象外
SKIP_FILES = {
    "index.html", "404.html", "plan.html", "contact.html", "privacy.html",
    "about.html", "how-we-make-guides.html", "sitemap.html", "search.html",
    "get-the-japan-checklist.html",
}
SKIP_PREFIXES = ("_", "hub-", "category-", "tag-")

# 文頭大文字・一般英単語などの誤検知を抑えるストップワード（小文字比較）
_STOP = {
    "the", "a", "an", "and", "or", "but", "if", "for", "with", "without", "from",
    "to", "in", "on", "at", "by", "of", "as", "is", "are", "was", "were", "be",
    "this", "that", "these", "those", "you", "your", "we", "our", "they", "their",
    "it", "its", "he", "she", "his", "her", "not", "no", "yes", "can", "will",
    "day", "days", "week", "month", "year", "hour", "minute", "tip", "tips",
    "note", "why", "how", "what", "when", "where", "who", "quick", "best", "good",
    "family", "families", "kid", "kids", "child", "children", "baby", "babies",
    "toddler", "toddlers", "parent", "parents", "travel", "trip", "guide", "guides",
    "hotel", "hotels", "room", "rooms", "train", "trains", "station", "food",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "japan", "japanese", "english", "wifi", "wi", "esim", "sim", "pdf",
    "north", "south", "east", "west", "central",
}

# 「実在確認が必要な固有名詞」らしさを高める手掛かり（施設/宿/商品の型）
_HOTEL_HINTS = re.compile(
    r"\b(hotels?|inns?|resorts?|ryokan|hostels?|suites?|residence|tower|lodge|"
    r"esim|sim|pass|card|museum|park|zoo|aquarium|land|sea|world|center|centre)\b",
    re.I,
)

# 連続する Capitalized トークン（2〜5語）を1候補とみなす。各語は大文字始まり。
_PHRASE = re.compile(r"\b([A-Z][A-Za-z0-9&'\.\-]+(?:\s+[A-Z][A-Za-z0-9&'\.\-]+){1,4})\b")
# タグ除去用
_TAG = re.compile(r"<[^>]+>")
# 本文とみなすブロック
_BLOCKS = re.compile(r"<(p|li|td|h2|h3|h4)\b[^>]*>(.*?)</\1>", re.I | re.S)


def _load_whitelist():
    """entities.yaml から照合用の許可語を作る。

    戻り値: (entity_names, brands_multi, brands_single)
      * entity_names  … 登録エンティティの正式名/別名（多くは複数語で具体的）。
                        フレーズ全体 or 相互部分一致で「既知」判定に使う。
      * brands_multi  … 複数語の一般ブランド（例: "don quijote"）。部分一致で既知判定。
      * brands_single … 単語の一般ブランド/地名（例: "tokyo", "moony"）。トークン除去にのみ使う
                        （短いので部分一致で使うとフレーズ全体を誤って既知化するため）。
    """
    entity_names, brands_multi, brands_single = set(), set(), set()
    try:
        import yaml  # PyYAML（configで使用済み）
        with open(ENTITIES_YAML, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for e in (data.get("entities") or []):
            v = e.get("name_en")
            if v:
                entity_names.add(v.lower())
            for a in (e.get("aliases") or []):
                entity_names.add(str(a).lower())
        for b in (data.get("known_brands") or []):
            bl = str(b).lower().strip()
            if " " in bl:
                brands_multi.add(bl)
            else:
                brands_single.add(bl)
    except Exception as ex:  # レポート側で扱う。ここでは空集合で継続（fail-open）
        print("WARN: could not load %s: %s" % (ENTITIES_YAML, ex), file=sys.stderr)
    return entity_names, brands_multi, brands_single


def _pages():
    for path in sorted(glob.glob(os.path.join(DOCS, "*.html"))):
        name = os.path.basename(path)
        if name in SKIP_FILES or name.startswith(SKIP_PREFIXES):
            continue
        yield path, name


def _candidates(html):
    """本文ブロックから固有名詞らしい候補フレーズを抽出。"""
    found = {}
    for m in _BLOCKS.finditer(html):
        text = _TAG.sub(" ", m.group(2))
        # HTMLエンティティを軽く戻す（&amp; など）
        text = text.replace("&amp;", "&").replace("&rsquo;", "'").replace("&mdash;", "-")
        for pm in _PHRASE.finditer(text):
            toks = [t for t in re.split(r"\s+", pm.group(1)) if t]
            # 先頭/末尾のストップワード（"The" 等の文頭大文字など）を落とす
            while toks and toks[0].lower().strip(".,&'-") in _STOP:
                toks.pop(0)
            while toks and toks[-1].lower().strip(".,&'-") in _STOP:
                toks.pop()
            if len(toks) < 2:  # 2語未満になったら固有名詞フレーズとして扱わない
                continue
            phrase = " ".join(toks)
            found[phrase] = found.get(phrase, 0) + 1
    return found


def _is_known(low, toks, entity_names, brands_multi, brands_single):
    """候補フレーズが既知（登録済みエンティティ/一般ブランド/地名の組合せ）かを判定。"""
    # 1) 登録エンティティ名との一致 or 相互部分一致（多くが複数語で具体的なので安全）
    if low in entity_names:
        return True
    for en in entity_names:
        if len(en) >= 5 and (en in low or low in en):
            return True
    # 2) 複数語の一般ブランドがフレーズに含まれる（例: "akachan honpo store"）
    for bm in brands_multi:
        if bm in low:
            return True
    # 3) 全トークンが「単語ブランド/地名 or ストップワード」なら固有名詞ではない
    for t in toks:
        tl = t.lower().strip(".,&'-")
        if tl and tl not in brands_single and tl not in _STOP:
            return False  # 有意なトークンが残る＝未登録候補
    return True


def scan():
    entity_names, brands_multi, brands_single = _load_whitelist()
    report = {}
    total = 0
    for path, name in _pages():
        try:
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
        except Exception:
            continue
        unknown = []
        for phrase, cnt in _candidates(html).items():
            low = phrase.lower()
            toks = [t for t in re.split(r"\s+", phrase) if t]
            if _is_known(low, toks, entity_names, brands_multi, brands_single):
                continue
            # 施設/宿/商品の手掛かりがある候補を優先的にレビュー対象へ
            priority = bool(_HOTEL_HINTS.search(phrase))
            unknown.append({"name": phrase, "count": cnt, "hotel_like": priority})
        if unknown:
            # hotel_like を先頭に、出現回数の多い順
            unknown.sort(key=lambda x: (not x["hotel_like"], -x["count"], x["name"]))
            report[name] = unknown
            total += len(unknown)
    return report, total


def main() -> int:
    report, total = scan()
    os.makedirs(REVIEW_DIR, exist_ok=True)
    # noindex 用のマーカーは不要（_review はサイトから未リンク）。JSONのみ出力。
    payload = {
        "generated_by": "entity_scan",
        "pages_flagged": len(report),
        "candidates_total": total,
        "report": report,
    }
    with open(REVIEW_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    # 上位だけ標準出力にサマリ（ログ用）
    print("entity_scan: %d pages with unregistered candidates, %d total" % (len(report), total))
    shown = 0
    for name, items in report.items():
        hot = [i["name"] for i in items if i["hotel_like"]]
        if hot:
            print("  REVIEW %s: %s" % (name, ", ".join(hot[:6])))
            shown += 1
        if shown >= 25:
            print("  ... (see %s for the full list)" % REVIEW_JSON)
            break
    # fail-open: 常に0で返す（デプロイは止めない）。人間レビューは週次Issueで消化。
    return 0


if __name__ == "__main__":
    sys.exit(main())
