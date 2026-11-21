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

_UNIT_CONVERSIONS = [
    (r"(\d+(?:\.\d+)?)\s*crores?\b", lambda v: f"{v:g} crore = {v * 10_000_000:,.0f} ({v / 100:g} billion)"),
    (r"(\d+(?:\.\d+)?)\s*lakhs?\b", lambda v: f"{v:g} lakh = {v * 100_000:,.0f}"),
    (r"(\d+(?:\.\d+)?)\s*mph\b", lambda v: f"{v:g} mph = {v * 1.60934:.2f} km/h"),
    (r"(\d+(?:\.\d+)?)\s*km/h\b", lambda v: f"{v:g} km/h = {v / 1.60934:.2f} mph"),
    (r"(-?\d+(?:\.\d+)?)\s*°?\s*f\b", lambda v: f"{v:g}°F = {(v - 32) * 5 / 9:.2f}°C"),
    (r"(-?\d+(?:\.\d+)?)\s*°?\s*c\b", lambda v: f"{v:g}°C = {(v * 9 / 5) + 32:.2f}°F"),
    (r"(\d+(?:\.\d+)?)\s*miles?\b", lambda v: f"{v:g} miles = {v * 1.60934:.2f} km"),
]


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
    """Deterministic symbolic, temporal, arithmetic, and unit-normalization unit."""

    @classmethod
    def analyze(cls, claim: str, documents: list[dict]) -> list[str]:
        facts: list[str] = []
        now = datetime.now(timezone.utc)
        current_year = now.year
        facts.append(f"CURRENT_DATE_UTC: {now.strftime('%Y-%m-%d')} (Year {current_year})")

        # 1. Temporal duration & chronological checks
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

        # 2. Arithmetic & percentage checks
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

        # 3. Unit & Scale Normalization (crores/lakhs, mph/kmh, °C/°F, miles/km)
        combined_text = claim + " " + " ".join(str(d.get("content", ""))[:400] for d in documents[:3])
        for pattern, formatter in _UNIT_CONVERSIONS:
            m = re.search(pattern, combined_text, flags=re.I)
            if m:
                try:
                    val = float(m.group(1))
                    facts.append(f"UNIT_NORMALIZATION: {formatter(val)}")
                except ValueError:
                    pass

        # 4. Cross-evidence years
        ev_years: set[int] = set()
        for doc in documents[:5]:
            blob = f"{doc.get('title', '')} {doc.get('content', '')}"
            for y in re.findall(r"\b(19\d{2}|20\d{2})\b", blob):
                ev_years.add(int(y))
        if ev_years:
            facts.append(f"EVIDENCE_YEARS_MENTIONED: {sorted(ev_years)}")

        return facts[:10]
