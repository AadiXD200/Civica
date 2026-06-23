# tension_detector.py
"""
Post-Round-2 analysis of cross-demographic disagreement on specialist risks.
Identifies where agents with similar income but different tenure disagree,
or where geographic fault lines appear in risk confirmation.
"""

from typing import Any

# ---------------------------------------------------------------------------
# City classification helpers
# ---------------------------------------------------------------------------

_URBAN_CITIES = {
    "Toronto", "Vancouver", "Montreal", "Calgary", "Edmonton",
    "Ottawa", "Hamilton", "Kitchener-Waterloo", "Halifax", "Victoria",
    # common aliases
    "Kitchener", "KW",
}

_RURAL_KEYWORDS = {"Rural", "Remote", "Reserve", "Nunavut", "PEI"}


def _classify_geography(city: str) -> str:
    """Returns 'urban' or 'rural' for a city name."""
    if city in _URBAN_CITIES:
        return "urban"
    for kw in _RURAL_KEYWORDS:
        if kw in city:
            return "rural"
    # Default unknown to urban (most validators are urban)
    return "urban"


# ---------------------------------------------------------------------------
# Income grouping
# ---------------------------------------------------------------------------

def _income_group(income_bracket: str) -> str:
    """Maps income bracket to low / medium / high."""
    low_brackets = {"very_low", "low"}
    high_brackets = {"high", "very_high"}
    if income_bracket in low_brackets:
        return "low"
    if income_bracket in high_brackets:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Age grouping
# ---------------------------------------------------------------------------

def _age_group(age_bracket: str) -> str:
    """Maps age bracket to young / older."""
    young_brackets = {"18-24", "25-34"}
    if age_bracket in young_brackets:
        return "young"
    return "older"


# ---------------------------------------------------------------------------
# Immigration grouping
# ---------------------------------------------------------------------------

def _immigration_group(immigration_status: str) -> str:
    """Maps immigration status to immigrant / born_here."""
    immigrant_statuses = {"recent_immigrant", "established_immigrant", "refugee"}
    if immigration_status in immigrant_statuses:
        return "immigrant"
    return "born_here"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_risk_confirmations(
    validator_results: list[dict],
    n_risks: int,
) -> dict[int, dict[str, Any]]:
    """
    For each risk index (1..n_risks), computes confirmation rates broken down by:
      tenure, income, geography, age, immigration.

    Returns:
        {
            risk_index: {
                "tenure": {
                    "renter": {"confirmed": int, "total": int, "rate": float},
                    "owner":  {"confirmed": int, "total": int, "rate": float},
                },
                "income": {
                    "low":    {"confirmed": int, "total": int, "rate": float},
                    "medium": {"confirmed": int, "total": int, "rate": float},
                    "high":   {"confirmed": int, "total": int, "rate": float},
                },
                "geography": {
                    "urban": {"confirmed": int, "total": int, "rate": float},
                    "rural": {"confirmed": int, "total": int, "rate": float},
                },
                "age": {
                    "young": {"confirmed": int, "total": int, "rate": float},
                    "older": {"confirmed": int, "total": int, "rate": float},
                },
                "immigration": {
                    "immigrant":  {"confirmed": int, "total": int, "rate": float},
                    "born_here":  {"confirmed": int, "total": int, "rate": float},
                },
            }
        }
    """

    def _empty_counter():
        return {"confirmed": 0, "total": 0, "rate": 0.0}

    # Initialise accumulators
    data: dict[int, dict] = {}
    for ri in range(1, n_risks + 1):
        data[ri] = {
            "tenure": {
                "renter": _empty_counter(),
                "owner": _empty_counter(),
            },
            "income": {
                "low": _empty_counter(),
                "medium": _empty_counter(),
                "high": _empty_counter(),
            },
            "geography": {
                "urban": _empty_counter(),
                "rural": _empty_counter(),
            },
            "age": {
                "young": _empty_counter(),
                "older": _empty_counter(),
            },
            "immigration": {
                "immigrant": _empty_counter(),
                "born_here": _empty_counter(),
            },
        }

    for vr in validator_results:
        tenure = vr.get("tenure", "")
        income_group = _income_group(vr.get("income_bracket", "medium"))
        geo_group = _classify_geography(vr.get("city", ""))
        age_group = _age_group(vr.get("age_bracket", "35-49"))
        imm_group = _immigration_group(vr.get("immigration_status", "canadian_born"))

        for val in vr.get("validations", []):
            ri = val.get("risk_index")
            if ri is None or ri not in data:
                continue

            confirmed = 1 if val.get("applies", False) else 0

            # tenure
            if tenure in data[ri]["tenure"]:
                data[ri]["tenure"][tenure]["total"] += 1
                data[ri]["tenure"][tenure]["confirmed"] += confirmed

            # income
            data[ri]["income"][income_group]["total"] += 1
            data[ri]["income"][income_group]["confirmed"] += confirmed

            # geography
            data[ri]["geography"][geo_group]["total"] += 1
            data[ri]["geography"][geo_group]["confirmed"] += confirmed

            # age
            data[ri]["age"][age_group]["total"] += 1
            data[ri]["age"][age_group]["confirmed"] += confirmed

            # immigration
            data[ri]["immigration"][imm_group]["total"] += 1
            data[ri]["immigration"][imm_group]["confirmed"] += confirmed

    # Compute rates
    for ri in data:
        for dimension in data[ri]:
            for group in data[ri][dimension]:
                cell = data[ri][dimension][group]
                if cell["total"] > 0:
                    cell["rate"] = cell["confirmed"] / cell["total"]
                else:
                    cell["rate"] = 0.0

    return data


# ---------------------------------------------------------------------------
# Tension detection
# ---------------------------------------------------------------------------

# Risk categories where high-income confirmation reflects civic awareness / asset
# exposure rather than personal vulnerability.
_AWARENESS_CATEGORIES = {"fiscal", "infrastructure", "timeline", "geographic"}

# Risk categories where high-income confirmation is genuinely surprising and
# worth flagging as a vulnerability signal.
_VULNERABILITY_CATEGORIES = {"affordability", "displacement", "equity", "employment"}


def _interpret(dimension: str, group_a: str, rate_a: float, group_b: str, rate_b: float, risk_category: str = "") -> str:
    """Returns an interpretation sentence for a detected tension."""
    cat = risk_category.lower()

    if dimension == "tenure":
        if group_a == "renter":
            return "Renters confirm this risk at much higher rates, suggesting the burden falls asymmetrically on non-owners."
        return "Owners confirm this risk at much higher rates, suggesting the primary exposure is to property-holding households — likely through asset value or tax effects."

    if dimension == "income":
        if group_a == "low":
            return "Lower-income households confirm this risk at much higher rates, indicating a regressive distributional impact."
        # group_a == "high" or "medium" — interpret based on risk category
        if cat in _AWARENESS_CATEGORIES:
            return (
                f"Higher-income households confirm this {cat} risk at higher rates, likely reflecting "
                "greater awareness of fiscal or infrastructure effects rather than personal financial vulnerability."
            )
        if cat in _VULNERABILITY_CATEGORIES:
            return (
                f"Higher-income households confirming this {cat} risk at higher rates is unexpected — "
                "it may indicate broad market-wide effects that reach beyond the most vulnerable."
            )
        return "Higher-income households confirm this risk at higher rates; interpret with caution — this may reflect awareness rather than personal exposure."

    if dimension == "geography":
        if group_a == "urban":
            return "Urban validators confirm this at higher rates, consistent with the policy targeting cities over 100,000 — rural and remote communities are structurally excluded."
        return "Rural validators confirm this at higher rates, suggesting the risk is more acute in low-density or remote contexts where services and supply are already constrained."

    if dimension == "age":
        if group_a == "young":
            return "Younger validators confirm this risk at higher rates, suggesting near-term housing market entrants bear disproportionate exposure."
        return "Older validators confirm this risk at higher rates, suggesting the burden falls on established households or those on fixed incomes."

    if dimension == "immigration":
        if group_a == "immigrant":
            return "Immigrant households confirm this at higher rates, likely reflecting precarious tenure, limited program access, and concentration in high-cost urban rental markets."
        return "Canadian-born validators confirm this at higher rates, which may reflect different patterns of home ownership and longer-term market exposure."

    return "Significant disagreement detected between demographic subgroups on this risk."


def _pairs_for_dimension(dimension: str) -> list[tuple[str, str]]:
    """Returns the group pairs to compare for a given dimension."""
    pairs = {
        "tenure": [("renter", "owner")],
        "income": [("low", "high"), ("low", "medium"), ("medium", "high")],
        "geography": [("urban", "rural")],
        "age": [("young", "older")],
        "immigration": [("immigrant", "born_here")],
    }
    return pairs.get(dimension, [])


MIN_COUNT = 3
MIN_GAP = 0.25


def detect_tensions(
    risk_confirmations: dict[int, dict],
    specialist_risks: list[dict],
) -> list[dict]:
    """
    For each risk and each dimension, checks for meaningful demographic splits.
    A split is flagged when:
      - rate difference > MIN_GAP (0.25)
      - both groups have at least MIN_COUNT (3) validators

    Returns list of tension objects.
    """
    tensions = []

    for ri, dim_data in risk_confirmations.items():
        # risk title and category (risks are 1-indexed)
        risk_title = ""
        risk_category = ""
        if 1 <= ri <= len(specialist_risks):
            risk_title = specialist_risks[ri - 1].get("risk", f"Risk {ri}")
            risk_category = specialist_risks[ri - 1].get("category", "")

        for dimension, groups in dim_data.items():
            for group_a, group_b in _pairs_for_dimension(dimension):
                cell_a = groups.get(group_a, {})
                cell_b = groups.get(group_b, {})

                total_a = cell_a.get("total", 0)
                total_b = cell_b.get("total", 0)
                rate_a = cell_a.get("rate", 0.0)
                rate_b = cell_b.get("rate", 0.0)

                if total_a < MIN_COUNT or total_b < MIN_COUNT:
                    continue

                gap = rate_a - rate_b

                if abs(gap) <= MIN_GAP:
                    continue

                # Ensure group_a is the higher-rate group for interpretation
                if gap < 0:
                    group_a, group_b = group_b, group_a
                    rate_a, rate_b = rate_b, rate_a
                    gap = -gap

                interpretation = _interpret(dimension, group_a, rate_a, group_b, rate_b, risk_category)

                tensions.append({
                    "risk_index": ri,
                    "risk_title": risk_title,
                    "risk_category": risk_category,
                    "dimension": dimension,
                    "group_a": group_a,
                    "rate_a": round(rate_a, 3),
                    "group_b": group_b,
                    "rate_b": round(rate_b, 3),
                    "gap": round(gap, 3),
                    "interpretation": interpretation,
                })

    # Sort by gap descending so the sharpest splits surface first
    tensions.sort(key=lambda t: t["gap"], reverse=True)
    return tensions


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_tensions_for_coordinator(
    tensions: list[dict],
    risk_confirmations: dict[int, dict],
) -> str:
    """
    Formats the tension list as a text block for the coordinator prompt.
    Groups by risk, shows fault lines clearly.
    """
    if not tensions:
        return "No significant cross-demographic disagreements detected."

    # Group by risk_index
    by_risk: dict[int, list[dict]] = {}
    for t in tensions:
        by_risk.setdefault(t["risk_index"], []).append(t)

    lines = ["=== CROSS-DEMOGRAPHIC TENSION ANALYSIS ===", ""]

    for ri in sorted(by_risk.keys()):
        risk_tensions = by_risk[ri]
        risk_title = risk_tensions[0]["risk_title"] or f"Risk {ri}"
        lines.append(f"Risk {ri}: {risk_title}")
        lines.append("-" * (len(f"Risk {ri}: {risk_title}")))

        for t in risk_tensions:
            pct_a = f"{t['rate_a'] * 100:.0f}%"
            pct_b = f"{t['rate_b'] * 100:.0f}%"
            gap_pct = f"{t['gap'] * 100:.0f}pp"
            lines.append(
                f"  [{t['dimension'].upper()}] {t['group_a']} confirm at {pct_a} vs "
                f"{t['group_b']} at {pct_b} (gap: {gap_pct})"
            )
            lines.append(f"  -> {t['interpretation']}")

        lines.append("")

    lines.append(
        f"Total tensions detected: {len(tensions)} across {len(by_risk)} risk(s)."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def run_tension_detection(
    validator_results: list[dict],
    specialist_risks: list[dict],
) -> tuple[list[dict], str]:
    """
    Top-level function. Runs the full tension detection pipeline.

    Args:
        validator_results: list of validator agent result dicts
        specialist_risks:  list of risk dicts from specialist round (0-indexed, risk["risk"] = title)

    Returns:
        (tensions_list, formatted_text)
    """
    n_risks = len(specialist_risks)
    risk_confirmations = compute_risk_confirmations(validator_results, n_risks)
    tensions = detect_tensions(risk_confirmations, specialist_risks)
    formatted_text = format_tensions_for_coordinator(tensions, risk_confirmations)
    return tensions, formatted_text
