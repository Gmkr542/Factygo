from __future__ import annotations

import ast
from datetime import datetime, timezone
import operator as op
import re


_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}


def _safe_eval_expr(expr: str) -> float | None:
    try:
        node = ast.parse(expr, mode="eval").body

        def _eval(n):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return float(n.value)
            if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
                return _OPS[type(n.op)](_eval(n.left), _eval(n.right))
            if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
                return _OPS[type(n.op)](_eval(n.operand))
            raise ValueError("Unsupported expression")

        val = _eval(node)
        return round(val, 4) if val is not None else None
    except Exception:
        return None


class LogicService:
    """Deterministic symbolic, temporal, and arithmetic verification unit."""

    @classmethod
    def analyze(cls, claim: str, documents: list[dict]) -> list[str]:
        facts: list[str] = []
        now = datetime.now(timezone.utc)
        current_year = now.year
        facts.append(f"CURRENT_DATE_UTC: {now.strftime('%Y-%m-%d')} (Year {current_year})")

        # 1. Temporal duration & chronological checks on years in claim + evidence
        claim_years = sorted({int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", claim)})
        if len(claim_years) >= 2:
            span = claim_years[-1] - claim_years[0]
            facts.append(f"CLAIM_YEAR_SPAN: {claim_years[-1]} - {claim_years[0]} = {span} year(s)")
        for y in claim_years:
            diff = current_year - y
            if diff > 0:
                facts.append(f"TEMPORAL_DELTA: Year {y} was {diff} year(s) before {current_year}.")
            elif diff < 0:
                facts.append(f"TEMPORAL_DELTA: Year {y} is {abs(diff)} year(s) in the future relative to {current_year}.")
            else:
                facts.append(f"TEMPORAL_DELTA: Year {y} is the current year ({current_year}).")

        # 2. Explicit arithmetic expressions in claim (e.g., "25% of 400", "10 + 15 = 30")
        eq_match = re.search(r"(\d+(?:\.\d+)?\s*[+\-*/]\s*\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)", claim)
        if eq_match:
            computed = _safe_eval_expr(eq_match.group(1))
            claimed_val = float(eq_match.group(2))
            if computed is not None:
                is_equal = abs(computed - claimed_val) < 1e-4
                facts.append(
                    f"ARITHMETIC_CHECK: {eq_match.group(1)} evaluates to {computed:g}, claimed {claimed_val:g} (MATCH={is_equal})."
                )

        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s+of\s+(\d+(?:\.\d+)?)", claim, flags=re.I)
        if pct_match:
            pct = float(pct_match.group(1))
            base = float(pct_match.group(2))
            res = round((pct / 100.0) * base, 4)
            facts.append(f"PERCENTAGE_COMPUTATION: {pct:g}% of {base:g} = {res:g}.")

        # 3. Cross-evidence year & numerical extraction
        ev_years: set[int] = set()
        for doc in documents[:5]:
            blob = f"{doc.get('title', '')} {doc.get('content', '')}"
            for y in re.findall(r"\b(19\d{2}|20\d{2})\b", blob):
                ev_years.add(int(y))
        if ev_years:
            facts.append(f"EVIDENCE_YEARS_MENTIONED: {sorted(ev_years)}")

        return facts[:8]
