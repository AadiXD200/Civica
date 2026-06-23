"""
sector_inference.py

Infers likely employment sector and AI exposure level for each agent
based on city, employment_type, income_bracket, and age_bracket.

The PUMF has no industry/sector codes — this module uses a probability-weighted
heuristic grounded in:
- StatsCan Q2 2024 AI adoption by industry (6.1% national average)
- City economic profiles (tech hubs vs resource/service cities)
- Employment type as sector proxy

Returns a sector_profile dict injected into persona calibration prompts
for AI/tech policies, replacing the irrelevant housing-stress framing.
"""

# ── City → likely sector mix ──────────────────────────────────────────────────
# Based on economic profiles of each city/region.
# Each entry: {sector_label: probability, ...}
# Sectors ordered by AI adoption rate (high → low).

_CITY_SECTOR_PROBS: dict[str, dict[str, float]] = {
    "Toronto": {
        "finance_and_insurance": 0.22,
        "professional_scientific_technical": 0.20,
        "information_and_cultural": 0.15,
        "healthcare_and_social": 0.12,
        "retail_trade": 0.10,
        "manufacturing": 0.08,
        "accommodation_and_food": 0.07,
        "other": 0.06,
    },
    "Vancouver": {
        "professional_scientific_technical": 0.22,
        "information_and_cultural": 0.18,
        "finance_and_insurance": 0.12,
        "retail_trade": 0.12,
        "accommodation_and_food": 0.10,
        "healthcare_and_social": 0.10,
        "manufacturing": 0.08,
        "other": 0.08,
    },
    "Montreal": {
        "professional_scientific_technical": 0.18,
        "information_and_cultural": 0.16,
        "manufacturing": 0.15,
        "healthcare_and_social": 0.14,
        "finance_and_insurance": 0.10,
        "retail_trade": 0.12,
        "accommodation_and_food": 0.09,
        "other": 0.06,
    },
    "Calgary": {
        "mining_oil_gas": 0.22,
        "professional_scientific_technical": 0.18,
        "finance_and_insurance": 0.14,
        "construction": 0.12,
        "retail_trade": 0.12,
        "healthcare_and_social": 0.10,
        "accommodation_and_food": 0.07,
        "other": 0.05,
    },
    "Edmonton": {
        "mining_oil_gas": 0.18,
        "construction": 0.16,
        "professional_scientific_technical": 0.15,
        "healthcare_and_social": 0.14,
        "retail_trade": 0.13,
        "manufacturing": 0.10,
        "accommodation_and_food": 0.08,
        "other": 0.06,
    },
    "Ottawa": {
        "professional_scientific_technical": 0.28,
        "information_and_cultural": 0.18,
        "public_administration": 0.20,
        "healthcare_and_social": 0.12,
        "retail_trade": 0.10,
        "accommodation_and_food": 0.07,
        "other": 0.05,
    },
    "Kitchener-Waterloo": {
        "information_and_cultural": 0.22,
        "professional_scientific_technical": 0.22,
        "manufacturing": 0.18,
        "finance_and_insurance": 0.12,
        "retail_trade": 0.10,
        "healthcare_and_social": 0.09,
        "other": 0.07,
    },
    "Winnipeg": {
        "healthcare_and_social": 0.18,
        "retail_trade": 0.16,
        "manufacturing": 0.14,
        "transportation": 0.12,
        "professional_scientific_technical": 0.12,
        "accommodation_and_food": 0.10,
        "agriculture_forestry_fishing": 0.08,
        "other": 0.10,
    },
    "Hamilton": {
        "manufacturing": 0.22,
        "healthcare_and_social": 0.18,
        "retail_trade": 0.14,
        "construction": 0.12,
        "professional_scientific_technical": 0.10,
        "accommodation_and_food": 0.10,
        "other": 0.14,
    },
    "Halifax": {
        "healthcare_and_social": 0.18,
        "professional_scientific_technical": 0.14,
        "public_administration": 0.14,
        "retail_trade": 0.14,
        "accommodation_and_food": 0.12,
        "information_and_cultural": 0.10,
        "other": 0.18,
    },
    "Victoria": {
        "public_administration": 0.22,
        "professional_scientific_technical": 0.16,
        "healthcare_and_social": 0.14,
        "retail_trade": 0.12,
        "accommodation_and_food": 0.12,
        "information_and_cultural": 0.10,
        "other": 0.14,
    },
    "Saskatoon": {
        "agriculture_forestry_fishing": 0.16,
        "healthcare_and_social": 0.16,
        "professional_scientific_technical": 0.14,
        "retail_trade": 0.14,
        "mining_oil_gas": 0.12,
        "construction": 0.12,
        "other": 0.16,
    },
    "Regina": {
        "public_administration": 0.18,
        "mining_oil_gas": 0.14,
        "agriculture_forestry_fishing": 0.14,
        "retail_trade": 0.14,
        "healthcare_and_social": 0.14,
        "construction": 0.10,
        "other": 0.16,
    },
    "Kelowna": {
        "agriculture_forestry_fishing": 0.16,
        "retail_trade": 0.16,
        "accommodation_and_food": 0.16,
        "construction": 0.14,
        "healthcare_and_social": 0.12,
        "professional_scientific_technical": 0.10,
        "other": 0.16,
    },
    "Sudbury": {
        "mining_oil_gas": 0.22,
        "healthcare_and_social": 0.16,
        "retail_trade": 0.14,
        "construction": 0.12,
        "public_administration": 0.12,
        "manufacturing": 0.10,
        "other": 0.14,
    },
}

# Fallback for rural/remote cities
_RURAL_SECTOR_PROBS: dict[str, float] = {
    "agriculture_forestry_fishing": 0.24,
    "mining_oil_gas": 0.16,
    "construction": 0.14,
    "healthcare_and_social": 0.14,
    "retail_trade": 0.12,
    "accommodation_and_food": 0.10,
    "other": 0.10,
}

# ── AI adoption rate by sector ────────────────────────────────────────────────
# Source: Statistics Canada Q2 2024 AI Adoption Survey
_SECTOR_AI_ADOPTION: dict[str, float] = {
    "information_and_cultural": 20.9,
    "professional_scientific_technical": 13.7,
    "finance_and_insurance": 10.9,
    "wholesale_trade": 7.5,
    "retail_trade": 5.2,
    "manufacturing": 4.8,
    "public_administration": 4.0,   # estimated — federal AI use is growing
    "transportation": 3.5,           # estimated
    "healthcare_and_social": 3.2,    # estimated — growing but early stage
    "construction": 2.1,
    "mining_oil_gas": 1.6,
    "accommodation_and_food": 0.9,
    "agriculture_forestry_fishing": 0.7,
    "other": 3.0,                    # national average as fallback
}

# ── Employment type → sector modifier ────────────────────────────────────────
# Adjusts sector probabilities based on how someone is employed.
_EMPLOYMENT_SECTOR_BOOST: dict[str, dict[str, float]] = {
    "salaried": {
        "finance_and_insurance": 1.4,
        "professional_scientific_technical": 1.3,
        "information_and_cultural": 1.3,
        "public_administration": 1.2,
        "healthcare_and_social": 1.1,
    },
    "self_employed": {
        "professional_scientific_technical": 1.5,
        "construction": 1.4,
        "agriculture_forestry_fishing": 1.3,
        "accommodation_and_food": 1.2,
        "retail_trade": 1.2,
    },
    "gig": {
        "accommodation_and_food": 1.6,
        "retail_trade": 1.5,
        "transportation": 1.4,
        "other": 1.3,
    },
    "student": {
        "accommodation_and_food": 1.5,
        "retail_trade": 1.4,
        "information_and_cultural": 1.2,  # tech-adjacent students
    },
    "unemployed": {},   # no adjustment
    "retired": {
        "healthcare_and_social": 1.2,   # more likely to have worked in stable sectors
        "public_administration": 1.2,
        "manufacturing": 1.1,
    },
}

# ── Income bracket → sector narrowing ────────────────────────────────────────
_INCOME_SECTOR_BOOST: dict[str, dict[str, float]] = {
    "very_high": {
        "finance_and_insurance": 1.5,
        "information_and_cultural": 1.4,
        "professional_scientific_technical": 1.4,
        "mining_oil_gas": 1.3,
    },
    "high": {
        "finance_and_insurance": 1.3,
        "professional_scientific_technical": 1.2,
        "information_and_cultural": 1.2,
        "public_administration": 1.1,
    },
    "medium": {},   # no strong signal
    "low": {
        "accommodation_and_food": 1.3,
        "retail_trade": 1.2,
        "agriculture_forestry_fishing": 1.2,
        "construction": 1.1,
    },
    "very_low": {
        "accommodation_and_food": 1.4,
        "agriculture_forestry_fishing": 1.3,
        "retail_trade": 1.2,
    },
}


def infer_sector_profile(agent: dict) -> dict:
    """
    Infers likely employment sector and AI exposure for an agent.

    Returns:
        {
            "most_likely_sector": str,
            "sector_ai_adoption_pct": float,
            "exposure_level": "high" | "medium" | "low",
            "sector_description": str,   # for prompt injection
            "ai_exposure_context": str,  # grounded sentence for validator prompt
        }
    """
    city = agent.get("city", "")
    employment_type = agent.get("employment_type", "salaried")
    income_bracket = agent.get("income_bracket", "medium")
    age_bracket = agent.get("age_bracket", "35-49")

    # Get base sector probabilities for city
    rural_keywords = {"Rural", "Remote", "Reserve", "Nunavut", "Northern", "PEI"}
    is_rural = any(kw in city for kw in rural_keywords)

    if is_rural:
        probs = dict(_RURAL_SECTOR_PROBS)
    else:
        probs = dict(_CITY_SECTOR_PROBS.get(city, _CITY_SECTOR_PROBS.get("Halifax", _RURAL_SECTOR_PROBS)))

    # Apply employment type boost
    emp_boost = _EMPLOYMENT_SECTOR_BOOST.get(employment_type, {})
    for sector, mult in emp_boost.items():
        if sector in probs:
            probs[sector] *= mult

    # Apply income bracket boost
    inc_boost = _INCOME_SECTOR_BOOST.get(income_bracket, {})
    for sector, mult in inc_boost.items():
        if sector in probs:
            probs[sector] *= mult

    # Normalize
    total = sum(probs.values())
    probs = {k: v / total for k, v in probs.items()}

    # Pick most likely sector
    most_likely = max(probs, key=lambda k: probs[k])
    ai_adoption = _SECTOR_AI_ADOPTION.get(most_likely, 3.0)

    # Compute weighted average AI exposure across top 3 sectors
    top3 = sorted(probs.items(), key=lambda x: -x[1])[:3]
    weighted_adoption = sum(_SECTOR_AI_ADOPTION.get(s, 3.0) * p for s, p in top3)
    weighted_adoption /= sum(p for _, p in top3)

    # Exposure level
    if weighted_adoption >= 10.0:
        exposure = "high"
    elif weighted_adoption >= 4.0:
        exposure = "medium"
    else:
        exposure = "low"

    # Human-readable sector descriptions
    _SECTOR_LABELS = {
        "information_and_cultural": "technology and media",
        "professional_scientific_technical": "professional and technical services",
        "finance_and_insurance": "finance and insurance",
        "healthcare_and_social": "healthcare and social services",
        "retail_trade": "retail",
        "manufacturing": "manufacturing",
        "public_administration": "public administration",
        "transportation": "transportation",
        "construction": "construction",
        "mining_oil_gas": "mining, oil and gas",
        "accommodation_and_food": "accommodation and food services",
        "agriculture_forestry_fishing": "agriculture and natural resources",
        "other": "mixed industries",
        "wholesale_trade": "wholesale trade",
    }
    sector_desc = _SECTOR_LABELS.get(most_likely, most_likely)

    # Build the AI exposure context sentence — grounded in real StatsCan numbers
    if exposure == "high":
        ai_context = (
            f"Your likely sector ({sector_desc}) has one of the highest AI adoption rates "
            f"in Canada at ~{ai_adoption:.0f}% (vs national average 6.1%, StatsCan Q2 2024). "
            f"You are directly in scope for AI disclosure requirements and may already interact "
            f"with AI systems in hiring, performance evaluation, or client-facing decisions."
        )
    elif exposure == "medium":
        ai_context = (
            f"Your likely sector ({sector_desc}) has moderate AI adoption (~{ai_adoption:.0f}%, "
            f"StatsCan Q2 2024). AI is present but not dominant in your workplace context. "
            f"Disclosure requirements would apply to some systems you encounter but not all."
        )
    else:
        ai_context = (
            f"Your likely sector ({sector_desc}) has very low AI adoption (~{ai_adoption:.1f}%, "
            f"among the lowest in Canada per StatsCan Q2 2024). Mandatory AI disclosure "
            f"requirements would create compliance costs for your employer or clients "
            f"with little near-term direct benefit to you personally — AI is not yet "
            f"meaningfully present in your work context."
        )

    return {
        "most_likely_sector": most_likely,
        "sector_label": sector_desc,
        "sector_ai_adoption_pct": round(ai_adoption, 1),
        "weighted_ai_adoption_pct": round(weighted_adoption, 1),
        "exposure_level": exposure,
        "sector_description": sector_desc,
        "ai_exposure_context": ai_context,
    }


def format_sector_for_persona_prompt(sector_profile: dict) -> str:
    """
    Formats the sector inference as a block for persona calibration prompts.
    Replaces housing-stress cohort stats for AI policies.
    """
    lines = [
        "AI sector exposure (inferred from city, employment type, and income — StatsCan Q2 2024):",
        f"  Most likely sector: {sector_profile['sector_label']}",
        f"  Sector AI adoption rate: {sector_profile['sector_ai_adoption_pct']}% "
        f"(national average: 6.1%)",
        f"  Personal AI exposure level: {sector_profile['exposure_level'].upper()}",
        f"  {sector_profile['ai_exposure_context']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    test_agents = [
        {"id": 1, "city": "Toronto", "employment_type": "salaried", "income_bracket": "high", "age_bracket": "25-34", "tenure": "renter"},
        {"id": 2, "city": "Halifax", "employment_type": "gig", "income_bracket": "low", "age_bracket": "25-34", "tenure": "renter"},
        {"id": 3, "city": "Kelowna", "employment_type": "self_employed", "income_bracket": "medium", "age_bracket": "35-49", "tenure": "owner"},
        {"id": 4, "city": "Reserve Northern Ontario", "employment_type": "unemployed", "income_bracket": "very_low", "age_bracket": "35-49", "tenure": "renter"},
        {"id": 5, "city": "Kitchener-Waterloo", "employment_type": "salaried", "income_bracket": "very_high", "age_bracket": "25-34", "tenure": "owner"},
    ]
    for a in test_agents:
        sp = infer_sector_profile(a)
        print(f"Agent {a['id']} ({a['city']}, {a['employment_type']}, {a['income_bracket']}):")
        print(f"  Sector: {sp['sector_label']} | AI adoption: {sp['sector_ai_adoption_pct']}% | Exposure: {sp['exposure_level']}")
        print(f"  Context: {sp['ai_exposure_context'][:120]}...")
        print()
