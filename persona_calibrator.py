# persona_calibrator.py
"""
Generates policy-sensitive behavioral profiles for demographic validators.
Runs one lightweight LLM call per agent before Round 2.
"""

import asyncio
import json
import os

import pumf_matcher
from sector_inference import infer_sector_profile, format_sector_for_persona_prompt

_AI_POLICY_TYPES = {"ai", "technology", "digital", "labour"}

VALIDATOR_PROVIDER = os.getenv("VALIDATOR_PROVIDER", "openai")
VALIDATOR_MODEL = os.getenv("VALIDATOR_MODEL", "gpt-4o-mini")

# Policy type → which cohort stats are most relevant (ordered list)
_POLICY_STAT_PRIORITY: dict[str, list[str]] = {
    "supply": [
        "core_housing_need_pct",
        "shelter_cost_100pct_plus_pct",
        "shelter_cost_30pct_plus_pct",
        "on_waitlist_pct",
    ],
    "fiscal": [
        "median_household_income",
        "shelter_cost_30pct_plus_pct",
        "shelter_cost_100pct_plus_pct",
        "no_employment_pct",
    ],
    "affordability": [
        "core_housing_need_pct",
        "shelter_cost_100pct_plus_pct",
        "shelter_cost_30pct_plus_pct",
        "median_household_income",
    ],
    "social": [
        "social_housing_pct",
        "on_waitlist_pct",
        "core_housing_need_pct",
        "dwelling_issues_pct",
    ],
    "zoning": [
        "core_housing_need_pct",
        "shelter_cost_30pct_plus_pct",
        "dwelling_issues_pct",
        "social_housing_pct",
    ],
    "default": [
        "core_housing_need_pct",
        "shelter_cost_30pct_plus_pct",
        "median_household_income",
        "on_waitlist_pct",
    ],
}

_STAT_LABELS: dict[str, str] = {
    "core_housing_need_pct":       "{val}% are in core housing need",
    "shelter_cost_30pct_plus_pct": "{val}% spend ≥30% of income on shelter",
    "shelter_cost_100pct_plus_pct": "{val}% spend their entire income (or more) on shelter",
    "median_household_income":     "Median household income: ${val:,}",
    "dwelling_issues_pct":         "{val}% have at least one major dwelling issue",
    "social_housing_pct":          "{val}% live in social or affordable housing",
    "on_waitlist_pct":             "{val}% are on a social housing waitlist",
    "no_employment_pct":           "{val}% have no employed person in the household",
}


# ── 1. build_cohort_summary ────────────────────────────────────────────────────

def build_cohort_summary(agent: dict, cohort_stats: dict, policy_classification: dict) -> str:
    """
    Assembles a compact, policy-relevant text block of CHS cohort statistics
    for the given agent. Selects the 3–4 most policy-relevant stats.
    Returns a formatted string; returns a fallback message if stats are empty.
    """
    if not cohort_stats:
        return "CHS 2022 microdata unavailable for this profile."

    policy_type = (policy_classification.get("type") or "default").lower()
    priority_keys = _POLICY_STAT_PRIORITY.get(policy_type, _POLICY_STAT_PRIORITY["default"])

    n_weighted = cohort_stats.get("n_matched_weighted", 0)
    filters = cohort_stats.get("filters_applied", [])
    scope = "matched profile" if filters else "national average"

    lines = [f"CHS 2022 data for households matching your profile (n={n_weighted:,.0f} weighted, {scope}):"]

    shown = 0
    for key in priority_keys:
        val = cohort_stats.get(key)
        if val is None:
            continue
        template = _STAT_LABELS.get(key, "")
        if not template:
            continue
        try:
            if key == "median_household_income":
                line = template.format(val=int(val))
            else:
                line = template.format(val=val)
        except (TypeError, ValueError):
            continue
        lines.append(f"- {line}")
        shown += 1
        if shown >= 4:
            break

    # If we have room and haven't shown dwelling/waitlist yet, add them
    extra_fallbacks = ["dwelling_issues_pct", "on_waitlist_pct", "no_employment_pct"]
    for key in extra_fallbacks:
        if shown >= 4:
            break
        if key in priority_keys:
            continue  # already considered above
        val = cohort_stats.get(key)
        if val is None:
            continue
        template = _STAT_LABELS.get(key, "")
        if not template:
            continue
        try:
            line = template.format(val=val)
        except (TypeError, ValueError):
            continue
        lines.append(f"- {line}")
        shown += 1

    return "\n".join(lines)


# ── 2. calibrate_persona ──────────────────────────────────────────────────────

async def calibrate_persona(
    client,
    thread_id: str,
    agent: dict,
    cohort_stats: dict,
    policy_classification: dict,
) -> dict:
    """
    Async LLM call that returns a behavioral profile for the agent.
    Uses VALIDATOR_PROVIDER / VALIDATOR_MODEL (gpt-4o-mini).
    """
    policy_type = (policy_classification.get("type") or "").lower()
    is_ai = policy_type in _AI_POLICY_TYPES or any(
        kw in " ".join(policy_classification.get("key_attributes", [])).lower()
        for kw in {"ai", "artificial_intelligence", "automation", "tech", "digital"}
    )

    if is_ai:
        # For AI policies: replace housing cohort stats with sector AI exposure
        sector_profile = infer_sector_profile(agent)
        context_block = format_sector_for_persona_prompt(sector_profile)
        domain_label = "AI and technology governance"
        grounding_instruction = (
            "Based on the real StatsCan sector data above, characterize this person's likely "
            "stance on an AI accountability/disclosure policy, their financial exposure to compliance costs "
            "or AI-driven job changes, and their lived experience of AI in their work context. "
            "Be specific — a retail gig worker has almost no AI exposure today but faces structural "
            "displacement risk if adoption scales; a finance worker already encounters AI systems daily. "
            "Reference the sector adoption percentages directly."
        )
    else:
        # Housing policy: use CHS microdata as before
        cohort_summary = build_cohort_summary(agent, cohort_stats, policy_classification)
        context_block = f"Statistics Canada CHS 2022 microdata for this demographic cohort:\n{cohort_summary}"
        domain_label = "Canadian housing policy"
        grounding_instruction = (
            "Based on the real CHS data above, characterize this person's likely financial fragility, "
            "stance on this specific policy, and lived experience. Be specific and grounded in the "
            "statistics — not generic. Reference the data points directly."
        )
        sector_profile = None

    prompt = f"""You are calibrating a demographic persona for a {domain_label} simulation.

Agent demographics:
- Age bracket: {agent.get('age_bracket')}
- City: {agent.get('city')}, {agent.get('province')}
- Tenure: {agent.get('tenure')}
- Income bracket: {agent.get('income_bracket')}
- Employment: {agent.get('employment_type')}
- Family size: {agent.get('family_size')}
- Immigration status: {agent.get('immigration_status')}
- Debt load: {agent.get('debt_load')}

{context_block}

Policy being analyzed:
Type: {policy_classification.get('type')}
Primary affected groups: {policy_classification.get('primary_affected', '')}
Summary: {policy_classification.get('summary', '')}

{grounding_instruction}

Return only valid JSON:
{{
    "financial_fragility": "low|medium|high",
    "policy_stance": "supportive|skeptical_of_benefit|indifferent|opposed",
    "top_concerns": ["concern 1", "concern 2"],
    "lived_experience_note": "1-2 sentence narrative grounding this agent's perspective in their real circumstances and the data above"
}}"""

    fallback = {
        "financial_fragility": "medium",
        "policy_stance": "indifferent",
        "top_concerns": [],
        "lived_experience_note": "",
    }

    try:
        response = await client.add_message(
            thread_id=thread_id,
            content=prompt,
            llm_provider=VALIDATOR_PROVIDER,
            model_name=VALIDATOR_MODEL,
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)

        # Validate and sanitise fields
        valid_fragility = {"low", "medium", "high"}
        valid_stance = {"supportive", "skeptical_of_benefit", "indifferent", "opposed"}

        if parsed.get("financial_fragility") not in valid_fragility:
            parsed["financial_fragility"] = "medium"
        if parsed.get("policy_stance") not in valid_stance:
            parsed["policy_stance"] = "indifferent"
        if not isinstance(parsed.get("top_concerns"), list):
            parsed["top_concerns"] = []
        if not isinstance(parsed.get("lived_experience_note"), str):
            parsed["lived_experience_note"] = ""

        # Attach sector profile for AI policies so frontend can display it
        if sector_profile:
            parsed["sector_profile"] = sector_profile

        return parsed

    except Exception:
        return fallback


# ── 3. format_persona_for_prompt ──────────────────────────────────────────────

def format_persona_for_prompt(behavioral_profile: dict, cohort_stats: dict) -> str:
    """
    Formats the calibration output as a text block for injection into validator prompts.
    For AI policies: shows sector AI exposure. For housing: shows CHS microdata stats.
    """
    sector_profile = behavioral_profile.get("sector_profile")

    if sector_profile:
        # AI policy — use sector context
        lines = ["Persona context (grounded in Statistics Canada AI Adoption Survey Q2 2024):"]
    else:
        lines = ["Persona context (grounded in Statistics Canada CHS 2022 microdata):"]

    fragility = behavioral_profile.get("financial_fragility", "medium")
    stance = behavioral_profile.get("policy_stance", "indifferent")
    concerns = behavioral_profile.get("top_concerns", [])
    narrative = behavioral_profile.get("lived_experience_note", "")

    lines.append(f"  Financial fragility: {fragility}")
    lines.append(f"  Policy stance: {stance.replace('_', ' ')}")

    if concerns:
        lines.append(f"  Top concerns: {'; '.join(concerns[:2])}")

    if narrative:
        lines.append(f"  Lived experience: {narrative}")

    if sector_profile:
        # AI policy grounding — sector stats instead of housing stats
        lines.append(f"  Sector: {sector_profile.get('sector_label', 'unknown')}")
        lines.append(
            f"  AI exposure: {sector_profile.get('exposure_level', 'unknown').upper()} "
            f"({sector_profile.get('sector_ai_adoption_pct', '?')}% adoption in sector "
            f"vs 6.1% national average)"
        )
    else:
        # Housing policy grounding
        stat_keys = ["core_housing_need_pct", "shelter_cost_30pct_plus_pct", "shelter_cost_100pct_plus_pct", "median_household_income"]
        for key in stat_keys:
            val = cohort_stats.get(key)
            if val is None:
                continue
            template = _STAT_LABELS.get(key, "")
            if not template:
                continue
            try:
                if key == "median_household_income":
                    line = template.format(val=int(val))
                else:
                    line = template.format(val=val)
            except (TypeError, ValueError):
                continue
            lines.append(f"  CHS data: {line}")

    n = cohort_stats.get("n_matched_weighted")
    if n:
        filters = cohort_stats.get("filters_applied", [])
        scope = f"(cohort n={n:,.0f} weighted" + (f", filters: {', '.join(filters)}" if filters else ", national avg") + ")"
        lines.append(f"  {scope}")

    return "\n".join(lines)


# ── 4. run_calibrations ───────────────────────────────────────────────────────

async def run_calibrations(
    client,
    asst_id: str,
    agents: list[dict],
    policy_classification: dict,
    survey_stats: dict,
) -> dict[str, dict]:
    """
    Runs persona calibration for all agents with bounded concurrency (semaphore=15).
    Returns dict mapping agent_id → behavioral_profile.
    Falls back to a minimal profile on any per-agent exception.
    """
    sem = asyncio.Semaphore(15)

    _fallback = {
        "financial_fragility": "medium",
        "policy_stance": "indifferent",
        "top_concerns": [],
        "lived_experience_note": "",
    }

    async def calibrate_one(agent: dict) -> tuple[str, dict]:
        async with sem:
            try:
                cohort_stats = pumf_matcher.get_cohort_stats(agent)
                thread = await client.create_thread(asst_id)
                profile = await calibrate_persona(
                    client,
                    thread.thread_id,
                    agent,
                    cohort_stats,
                    policy_classification,
                )
                return agent["id"], profile
            except Exception:
                return agent["id"], dict(_fallback)

    results = await asyncio.gather(
        *[calibrate_one(a) for a in agents],
        return_exceptions=True,
    )

    profiles: dict[str, dict] = {}
    for item in results:
        if isinstance(item, Exception):
            continue
        agent_id, profile = item
        profiles[agent_id] = profile

    return profiles
