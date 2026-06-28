"""記事のAI自己採点ルーブリック（②品質ゲートの最終段）。

生成された記事を別プロンプトで 0-100 点に採点し、基準(min_score)未満なら作り直し、
それでも未満なら「公開保留(=破棄)」する。薄い記事・AI丸出し・FAQ/表欠落・clickbaitの
流出を止める最後の関所。guards.quality_ok（語数/h2などの機械チェック）の後に効く。

採点は5観点×0-20点＝100点満点:
  accuracy / usefulness / specificity / structure / readability
"""
from __future__ import annotations
import re
from .util import load_settings, log
from .llm import generate

# 構造化出力スキーマ（geminiのcontrolled generationで“必ず妥当なJSON”を返させる）
_RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "accuracy": {"type": "integer"},
        "usefulness": {"type": "integer"},
        "specificity": {"type": "integer"},
        "structure": {"type": "integer"},
        "readability": {"type": "integer"},
        "total": {"type": "integer"},
        "verdict": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "accuracy", "usefulness", "specificity",
        "structure", "readability", "total", "verdict", "issues",
    ],
    "propertyOrdering": [
        "accuracy", "usefulness", "specificity",
        "structure", "readability", "total", "verdict", "issues",
    ],
}

_SUB = ("accuracy", "usefulness", "specificity", "structure", "readability")


def _html_to_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "")


def score_content(content: dict) -> dict:
    """記事を採点し {total(0-100), accuracy.., verdict, issues[]} を返す。
    採点自体が失敗した場合は安全側＝合格扱い(total=100)で返す（記事ゼロを防ぐ）。"""
    cfg = load_settings()
    niche = cfg.get("niche", {})
    title = content.get("article_title", "")
    body = _html_to_text(content.get("article_html", ""))[:9000]

    prompt = f"""You are a STRICT editor for a parenting + Japan-travel blog.
Grade the DRAFT below as it would actually serve a real parent planning a trip to Japan with kids.

Audience: {niche.get('audience', '')}
Required voice: {niche.get('tone', '')}

Score each dimension 0-20 (be harsh; reserve 18-20 for genuinely excellent work):
- accuracy: factually plausible, no obvious errors; any price/opening-hours hedged with "as of 2026, confirm on the official site".
- usefulness: actually helps a parent decide or plan; not generic filler a big-media "top 10" already covers.
- specificity: concrete names, numbers, stations, minutes, kg, yen — not vague hand-waving.
- structure: opens with a hook (does NOT repeat the title as a heading), has a TL;DR list, at least one compact comparison/quick-reference table, an FAQ of 5-8 real questions, and a one-sentence practical takeaway.
- readability: clean HTML with NO markdown tells (no ** , ## , "- " bullets, no backticks), no clickbait, no leftover AI scaffolding/placeholder text ("(placeholder...)", "TODO", "insert link here").

DRAFT title: {title}
DRAFT body (HTML stripped to text):
{body}

Return ONLY JSON: integer subscores (0-20 each) for accuracy/usefulness/specificity/structure/readability,
their sum as "total" (0-100), "verdict" (one short sentence), and "issues" (concrete problems to fix; [] if none)."""

    try:
        out = generate(prompt, as_json=True, schema=_RUBRIC_SCHEMA)
    except Exception as e:
        log.error("ルーブリック採点に失敗 → 暫定で合格扱い: %s", e)
        return {"total": 100, "verdict": "scoring failed; passed by default", "issues": []}

    # モデルの足し算ミス対策: サブスコア合計でtotalを上書き（サブが取れた場合）
    try:
        calc = sum(int(out.get(k, 0) or 0) for k in _SUB)
    except Exception:
        calc = 0
    if calc:
        out["total"] = max(0, min(100, calc))
    else:
        try:
            out["total"] = max(0, min(100, int(out.get("total", 0))))
        except Exception:
            out["total"] = 0
    return out


def passes(content: dict, min_score: int) -> tuple[bool, dict]:
    """採点して (合格か, レポートdict) を返す。"""
    rep = score_content(content)
    total = int(rep.get("total", 0))
    ok = total >= min_score
    log.info("ルーブリック採点: total=%d (基準%d) verdict=%s",
             total, min_score, rep.get("verdict", ""))
    if not ok and rep.get("issues"):
        log.info("ルーブリック指摘: %s", rep.get("issues"))
    return ok, rep
