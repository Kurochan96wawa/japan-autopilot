# -*- coding: utf-8 -*-
"""施策3-5: 検索意図バリデータ（レビュー送り方式）。

タイトル/スラッグのパターン別に「検索意図を満たす最低要素」を機械チェックする。
不合格ページを docs/_review/intent-review.json に書き出す（人間レビューは週次Issueで消化）。

チェック内容（指示書 §3-5）:
  * best-* / *-compared … facts/entities.yaml 登録済みエンティティが本文に4個以上
      （マネーページに固有名詞ゼロ＝検索意図未充足の再発防止）。
  * *-itinerary-* … 「Day N」見出しが存在（旅程記事なのに旅程が無い状態の検出）。
  * FAQ を持つページ … 「Absolutely!」型の空回答（具体名詞・数値の無い回答）が過半なら不合格。

方針: これも **fail-open（レビュー送り）**。既存記事を一斉に fail-closed にしないため
（ハードなCIブロックは収益リンク link_linter に限定という指示書方針を踏襲）。
新規生成パイプライン側のゲートとしても流用できるよう、判定関数 validate_page() を公開する。

標準ライブラリのみ + PyYAML。実行: `python -m src.intent_validator`。
"""
from __future__ import annotations
import glob
import json
import os
import re
import sys

try:
    from .entity_scan import _load_whitelist, _pages, SKIP_FILES, SKIP_PREFIXES
except Exception:  # 直接実行時のフォールバック
    from entity_scan import _load_whitelist, _pages, SKIP_FILES, SKIP_PREFIXES

DOCS = "docs"
REVIEW_DIR = os.path.join(DOCS, "_review")
REVIEW_JSON = os.path.join(REVIEW_DIR, "intent-review.json")

MIN_ENTITIES = 4  # best-*/*-compared に必要な登録エンティティ数

_TAG = re.compile(r"<[^>]+>")
_DAY_HEADING = re.compile(r"<h[23][^>]*>\s*Day\s*\d+", re.I)
# 空回答の手掛かり（断定だけで中身が無い定型）
_VACUOUS_START = re.compile(
    r"^(absolutely|definitely|of course|yes,?|sure|certainly|no,?|not really)\b", re.I)
_HAS_NUMBER = re.compile(r"\d")


def _text(html):
    t = _TAG.sub(" ", html)
    return re.sub(r"\s+", " ", t)


def _page_type(name):
    base = name[:-5] if name.endswith(".html") else name  # strip .html
    types = []
    if base.startswith("best-"):
        types.append("best")
    if base.endswith("-compared") or "-compared-" in base or "-vs-" in base:
        types.append("compared")
    if "itinerary" in base:
        types.append("itinerary")
    return types, base


def _count_registered_entities(text, entity_names):
    low = text.lower()
    hits = set()
    for en in entity_names:
        # 3文字以下の別名は誤カウントを避けてスキップ
        if len(en) >= 5 and en in low:
            hits.add(en)
    return len(hits)


def _expected_days(base):
    m = re.search(r"(\d+)\s*-?\s*day", base)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _faq_answers(html):
    """FAQ回答テキストの配列を返す（無ければ空）。"""
    answers = []
    # schema.org FAQ: acceptedAnswer text、または <details><summary>Q</summary>A</details>、
    # または dt/dd、q/a クラス。まず acceptedAnswer JSON-LD を軽く拾う。
    for m in re.finditer(r'"acceptedAnswer"\s*:\s*\{[^}]*?"text"\s*:\s*"(.*?)"', html, re.S):
        answers.append(re.sub(r"\\.", " ", m.group(1)))
    if answers:
        return answers
    # details/summary パターン
    for m in re.finditer(r"<details[^>]*>(.*?)</details>", html, re.I | re.S):
        block = m.group(1)
        block = re.sub(r"<summary[^>]*>.*?</summary>", " ", block, flags=re.I | re.S)
        answers.append(_text(block))
    if answers:
        return answers
    # dt/dd
    for m in re.finditer(r"<dd[^>]*>(.*?)</dd>", html, re.I | re.S):
        answers.append(_text(m.group(1)))
    return answers


def validate_page(name, html, entity_names):
    """1ページを検証し、問題（文字列）の配列を返す。空なら合格。"""
    issues = []
    types, base = _page_type(name)
    text = _text(html)

    if "best" in types or "compared" in types:
        n = _count_registered_entities(text, entity_names)
        if n < MIN_ENTITIES:
            issues.append(
                "money-intent page has only %d registered entities (need >=%d): "
                "add named, verified picks to facts/entities.yaml" % (n, MIN_ENTITIES))

    if "itinerary" in types:
        days = len(_DAY_HEADING.findall(html))
        exp = _expected_days(base)
        if days == 0:
            issues.append("itinerary page has no 'Day N' headings (no actual itinerary)")
        elif exp and days < exp:
            issues.append("itinerary names %d days in slug but has %d 'Day N' headings"
                          % (exp, days))

    answers = _faq_answers(html)
    if len(answers) >= 3:
        vacuous = 0
        for a in answers:
            a = a.strip()
            words = len(a.split())
            starts_vacuous = bool(_VACUOUS_START.match(a))
            has_num = bool(_HAS_NUMBER.search(a))
            # 断定で始まり、数値も無く、短い回答＝中身が薄い
            if starts_vacuous and not has_num and words < 25:
                vacuous += 1
        if vacuous > len(answers) / 2:
            issues.append("FAQ: %d/%d answers look vacuous (assertion without specifics)"
                          % (vacuous, len(answers)))
    return issues


def validate():
    entity_names, _bm, _bs = _load_whitelist()
    report = {}
    for path, name in _pages():
        try:
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
        except Exception:
            continue
        issues = validate_page(name, html, entity_names)
        if issues:
            report[name] = issues
    return report


def main() -> int:
    report = validate()
    os.makedirs(REVIEW_DIR, exist_ok=True)
    payload = {
        "generated_by": "intent_validator",
        "pages_failed": len(report),
        "report": report,
    }
    with open(REVIEW_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("intent_validator: %d pages need review" % len(report))
    for name, issues in list(report.items())[:25]:
        print("  REVIEW %s: %s" % (name, "; ".join(issues)))
    # fail-open: デプロイは止めない。
    return 0


if __name__ == "__main__":
    sys.exit(main())
