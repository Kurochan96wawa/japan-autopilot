# -*- coding: utf-8 -*-
"""本文のTF-IDFコサイン類似度で重複/ニアミス記事を検出する（標準ライブラリのみ）。
レポート指摘の実重複（例: diapers-formula-baby-gear… と diapers-formula-in-japan…）を可視化。

方針（是々非々）: 流入0の段階で自動 canonical/noindex は誤って良ページを消すリスクが高い。
よって本モジュールは既定で“検出＆レポート”に徹し、canonical適用は明示呼び出し時のみ行う。
PVが出てから「残す方をPVで決めて canonical」を回す運用に移行する。"""
from __future__ import annotations
import re
import math
import glob
import os
from collections import Counter

SKIP = {"index.html", "about.html", "disclosure.html", "privacy.html",
        "contact.html", "how-we-make-guides.html"}


def _text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"<[^>]+>", " ", html).lower()


def _tokens(t: str) -> list:
    return re.findall(r"[a-z0-9]+", t)


def _tfidf(token_lists: list) -> list:
    df = Counter()
    tfs = []
    for toks in token_lists:
        c = Counter(toks)
        tfs.append(c)
        for w in c:
            df[w] += 1
    n = len(token_lists)
    vecs = []
    for c in tfs:
        vecs.append({w: f * (math.log((n + 1) / (df[w] + 1)) + 1) for w, f in c.items()})
    return vecs


def _cos(a: dict, b: dict) -> float:
    common = set(a) & set(b)
    num = sum(a[w] * b[w] for w in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return num / (na * nb) if na and nb else 0.0


def find_similar(docs_dir: str = "docs", threshold: float = 0.86) -> list:
    files = [f for f in glob.glob(os.path.join(docs_dir, "*.html"))
             if os.path.basename(f) not in SKIP]
    if len(files) < 2:
        return []
    texts = []
    for f in files:
        try:
            texts.append(_tokens(_text(open(f, encoding="utf-8").read())))
        except Exception:
            texts.append([])
    vecs = _tfidf(texts)
    pairs = []
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            s = _cos(vecs[i], vecs[j])
            if s >= threshold:
                pairs.append((os.path.basename(files[i]),
                              os.path.basename(files[j]), round(s, 3)))
    return sorted(pairs, key=lambda x: -x[2])


def set_canonical(path: str, canonical_url: str) -> None:
    """明示呼び出し時のみ canonical を上書き（自動運用ではまだ使わない）。"""
    html = open(path, encoding="utf-8").read()
    new = f'<link rel="canonical" href="{canonical_url}">'
    if re.search(r'<link[^>]+rel="canonical"[^>]*>', html):
        html = re.sub(r'<link[^>]+rel="canonical"[^>]*>', new, html)
    else:
        html = html.replace("</head>", new + "</head>")
    open(path, "w", encoding="utf-8").write(html)


def report(docs_dir: str = "docs", threshold: float = 0.86) -> str:
    """週次レポート用のMarkdown断片を返す（検出のみ・破壊操作なし）。"""
    pairs = find_similar(docs_dir, threshold)
    if not pairs:
        return "## 重複チェック\n\n類似度{:.2f}以上の重複ペアは検出されませんでした。\n".format(threshold)
    lines = ["## 重複チェック（要・角度分離 or canonical検討）", ""]
    for a, b, s in pairs:
        lines.append(f"- 類似度 {s}: `{a}` ↔ `{b}`")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    for a, b, s in find_similar():
        print(f"{s}  {a}  <->  {b}")
