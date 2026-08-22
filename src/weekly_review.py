# -*- coding: utf-8 -*-
"""施策3-6: 週次レビュー・ダイジェスト生成。

人間の週次工数を30〜60分に収めるため、レビューが必要な情報を1つのIssue本文
（Markdown）に集約する。ワークフロー weekly-review.yml がこれを実行し、標準出力を
`gh issue create --body-file` に渡してIssueを立てる（送信＝Issue作成はワークフロー側）。

集約する内容（指示書 §3-6）:
  1. 今週の新規公開記事（data/state.json の posted を posted_at で7日分）
  2. レビュー待ち … entities.yaml 未登録エンティティ（3-1）＋ 検索意図バリデータ不合格（3-5）
  3. 収益リンクのリンター違反（3-2 link_linter）
  4. facts.yaml の期限切れ（verified_date が6ヶ月超）… 月次再確認対象（3-4 と連携。無ければ省略）

すべて best-effort（例外は握りつぶしてセクションを省く）。標準ライブラリ + PyYAML。
実行: `python -m src.weekly_review > body.md`
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone, timedelta

DATA_STATE = os.path.join("data", "state.json")
FACTS_YAML = os.path.join("facts", "facts.yaml")
BODY_ENV = "WEEKLY_ISSUE_BODY"  # 出力先ファイルの上書き用（任意）


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _parse_iso(s):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _new_articles(days=7):
    state = _load_json(DATA_STATE) or {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for rec in state.get("posted", []):
        dt = _parse_iso(rec.get("posted_at"))
        if dt and dt >= cutoff:
            out.append((rec.get("article_title") or rec.get("slug") or "(untitled)",
                        rec.get("slug", "")))
    return out


def _entity_review():
    """entity_scan を実行して未登録候補（hotel_like優先）を返す。"""
    try:
        from . import entity_scan  # type: ignore
    except Exception:
        try:
            import entity_scan  # type: ignore
        except Exception:
            return {}
    try:
        report, _ = entity_scan.scan()
        return report
    except Exception:
        return {}


def _intent_review():
    try:
        from . import intent_validator  # type: ignore
    except Exception:
        try:
            import intent_validator  # type: ignore
        except Exception:
            return {}
    try:
        return intent_validator.validate()
    except Exception:
        return {}


def _link_violations():
    try:
        from . import link_linter  # type: ignore
    except Exception:
        try:
            import link_linter  # type: ignore
        except Exception:
            return [], []
    try:
        return link_linter.lint()
    except Exception:
        return [], []


def _stale_facts(months=6):
    data = _load_json_yaml(FACTS_YAML)
    if not data:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    stale = []
    facts = data.get("facts") if isinstance(data, dict) else data
    for f in (facts or []):
        if not isinstance(f, dict):
            continue
        dt = _parse_iso(str(f.get("verified_date", "")))
        fid = f.get("id") or f.get("key") or f.get("name") or "(fact)"
        if dt is None or dt < cutoff:
            stale.append(fid)
    return stale


def _load_json_yaml(path):
    try:
        import yaml
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except Exception:
        return None


def build_body():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    L = []
    L.append("## littletabi 週次レビュー (%s)" % today)
    L.append("")
    L.append("自動生成。approve/reject はこのIssueにコメント/ラベルで。詳細レポートは "
             "`docs/_review/*.json`。")
    L.append("")

    # 1. 新規公開
    arts = _new_articles(7)
    L.append("### 1. 今週の新規公開記事 (%d)" % len(arts))
    if arts:
        for title, slug in arts:
            L.append("- %s  `%s`" % (title, slug))
    else:
        L.append("- (なし)")
    L.append("")

    # 3. 収益リンク違反（先に出す＝最優先）
    fails, warns = _link_violations()
    L.append("### 2. 収益リンクのリンター (FAIL=%d / WARN=%d)" % (len(fails), len(warns)))
    if fails:
        L.append("**FAIL（デプロイを止める重大違反）:**")
        for f in fails[:40]:
            L.append("- [ ] %s" % f)
    if warns:
        L.append("WARN:")
        for w in warns[:20]:
            L.append("- %s" % w)
    if not fails and not warns:
        L.append("- 違反なし ✅")
    L.append("")

    # 2. レビュー待ち：未登録エンティティ
    ent = _entity_review()
    hot_pages = {n: [i["name"] for i in items if i.get("hotel_like")]
                 for n, items in ent.items()}
    hot_pages = {n: v for n, v in hot_pages.items() if v}
    L.append("### 3. レビュー待ち: 未登録の固有名詞（施設/宿/商品らしきもの）")
    if hot_pages:
        L.append("→ 実在確認して `facts/entities.yaml` に登録、または本文から除去。")
        for n, names in list(hot_pages.items())[:25]:
            L.append("- **%s**: %s" % (n, ", ".join(names[:8])))
    else:
        L.append("- 優先度の高い未登録候補なし（全候補は `entities-review.json`）")
    L.append("")

    # 2b. 検索意図バリデータ不合格
    intent = _intent_review()
    L.append("### 4. レビュー待ち: 検索意図バリデータ不合格 (%d)" % len(intent))
    if intent:
        for n, issues in list(intent.items())[:25]:
            L.append("- **%s**: %s" % (n, "; ".join(issues)))
    else:
        L.append("- なし ✅")
    L.append("")

    # 4. facts.yaml 期限切れ
    stale = _stale_facts(6)
    if stale:
        L.append("### 5. 月次: 再確認が必要な共有ファクト（verified_date 6ヶ月超）")
        for fid in stale[:30]:
            L.append("- [ ] %s" % fid)
        L.append("")

    L.append("---")
    L.append("_generated by src.weekly_review_")
    return "\n".join(L)


def main() -> int:
    body = build_body()
    dest = os.environ.get(BODY_ENV)
    if dest:
        try:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(body)
        except Exception as e:
            print("WARN: could not write %s: %s" % (dest, e), file=sys.stderr)
    # 標準出力にも本文（ワークフローが --body-file か stdout を使える）
    sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
