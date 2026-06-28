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
        out = [s for s in ([c.get("pillar")] + list(c.get("members", []) or [])) if s and s != slug]
        return out[:n + 1]
    sibs = [s for s in (c.get("members", []) or []) if s != slug]
    out = sibs[:n]
    if c.get("pillar") and c["pillar"] != slug:
        out.append(c["pillar"])  # ピラーへ必ず1本＝権威集約
    # 重複除去・順序維持
    seen, dedup = set(), []
    for s in out:
        if s not in seen:
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
