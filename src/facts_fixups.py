# -*- coding: utf-8 -*-
"""施策3-4: 記事間で共有される事実の矛盾を冪等に正規化する後段fixup。

facts/facts.yaml（公式確認済みの単一情報源）の normalize ルールに従い、docs/ の
記事間の数値矛盾を修正する（例: ディズニーのベビーカー体重制限を 15kg に統一）。

安全設計（指示書 §0-2 捏造禁止 / §3-4 / 既存 *_fixups の冪等方針）:
  * fail-safe（例外は握りつぶし、置換ゼロでも正常終了）。CIは止めない（リンターの役目）。
  * 誤爆防止のため、置換は「近傍(±WINDOW文字)に context語と cue語が両方ある」場合のみ。
  * 冪等: correct 値は wrong 正規表現にマッチしないよう facts.yaml 側で設計する
    （例: 正値 "15 kg" は wrong の 16-25kg にマッチしない）。
  * 標準ライブラリ + PyYAML。実行: `python -m src.facts_fixups`
    （daily.yml の他 fixups と並べ、link_linter の前に置く）。
"""
from __future__ import annotations
import glob
import os
import re
import sys

DOCS = "docs"
FACTS_YAML = os.path.join("facts", "facts.yaml")

SKIP_PREFIXES = ("_",)

# 文の区切り（誤爆防止のため context/cue は「同一文」内でのみ探す）。
# 句読点・タグ境界・改行を境界とみなす。
_SENT_BREAK_BEFORE = ('.', '!', '?', '>', '\n')
_SENT_BREAK_AFTER = ('.', '!', '?', '<', '\n')


def _sentence_around(html, s, e):
    """マッチ位置(s,e)を含む「文」を返す（前後の文へはまたがない）。"""
    start = 0
    for ch in _SENT_BREAK_BEFORE:
        i = html.rfind(ch, 0, s)
        if i + 1 > start:
            start = i + 1
    end = len(html)
    for ch in _SENT_BREAK_AFTER:
        i = html.find(ch, e)
        if i != -1 and i < end:
            end = i
    return html[start:end].lower()


def _load_rules():
    """facts.yaml から (fact_id, compiled_regex, correct, context, cue) の配列を返す。"""
    rules = []
    try:
        import yaml
        with open(FACTS_YAML, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as ex:
        print("WARN: could not load %s: %s" % (FACTS_YAML, ex), file=sys.stderr)
        return rules
    for f in (data.get("facts") or []):
        fid = f.get("id", "?")
        for rule in (f.get("normalize") or []):
            wrong = rule.get("wrong")
            correct = rule.get("correct")
            if not wrong or correct is None:
                continue
            try:
                rx = re.compile(wrong, re.I)
            except re.error as e:
                print("WARN: bad regex in %s: %s (%s)" % (fid, wrong, e), file=sys.stderr)
                continue
            rules.append((fid, rx, correct,
                          (rule.get("context") or "").lower(),
                          (rule.get("cue") or "").lower()))
    return rules


def _pages():
    for path in sorted(glob.glob(os.path.join(DOCS, "*.html"))):
        if os.path.basename(path).startswith(SKIP_PREFIXES):
            continue
        yield path


def _apply(html, rules):
    """1ページにルールを適用。(new_html, 置換件数) を返す。"""
    changes = 0

    def make_sub(correct, context, cue):
        def _repl(m):
            nonlocal changes
            sentence = _sentence_around(html, m.start(), m.end())
            if context and context not in sentence:
                return m.group(0)  # 同一文に文脈語が無い→置換しない（誤爆防止）
            if cue and cue not in sentence:
                return m.group(0)
            changes += 1
            return correct
        return _repl

    for _fid, rx, correct, context, cue in rules:
        html = rx.sub(make_sub(correct, context, cue), html)
    return html, changes


def run():
    rules = _load_rules()
    if not rules:
        print("facts_fixups: no normalize rules; nothing to do")
        return 0
    total = 0
    pages = 0
    for path in _pages():
        try:
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
        except Exception:
            continue
        new_html, n = _apply(html, rules)
        if n and new_html != html:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new_html)
                total += n
                pages += 1
                print("facts_fixups: %s (%d fix)" % (os.path.basename(path), n))
            except Exception as e:
                print("WARN: could not write %s: %s" % (path, e), file=sys.stderr)
    print("facts_fixups: normalized %d value(s) across %d page(s)" % (total, pages))
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
