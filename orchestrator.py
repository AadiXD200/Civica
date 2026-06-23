import asyncio
import json
import os
import time

from backboard import BackboardClient
from dotenv import load_dotenv
from agents import AGENTS, get_demographic_breakdowns
from citations import get_relevant_docs, format_docs_for_prompt, format_survey_stats_for_prompt, format_historical_precedents_for_specialist
from data_pipeline import load_city_profiles
from policy_classifier import classify_policy
from confidence_scorer import calculate_confidence
from forward_validator import seal_simulation
from specialist_calibrator import calibrate_specialist_prompt, get_specialist_relevance
from benefits_analyzer import run_benefits_analysis, aggregate_benefits
from persona_calibrator import format_persona_for_prompt, build_cohort_summary
from sector_inference import infer_sector_profile, format_sector_for_persona_prompt
from tension_detector import run_tension_detection
import pumf_matcher

load_dotenv()

BACKBOARD_API_KEY = os.getenv("BACKBOARD_API_KEY", "")
SPECIALIST_PROVIDER = "openai"
SPECIALIST_MODEL = "gpt-4o"
VALIDATOR_PROVIDER = "openai"
VALIDATOR_MODEL = "gpt-4o-mini"
COORDINATOR_PROVIDER = "openai"
COORDINATOR_MODEL = "gpt-4o"
DEMOGRAPHIC_GROUPS = get_demographic_breakdowns(AGENTS)
CITY_PROFILES = load_city_profiles()

# Load survey stats once for persona calibration
def _load_survey_stats():
    path = os.path.join(os.path.dirname(__file__), "data", "survey_stats.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

SURVEY_STATS = _load_survey_stats()

# Map agent city names to data_pipeline city names
CITY_NAME_MAP = {
    "Kitchener-Waterloo": "Kitchener",
    "Northern Ontario Rural": "Northern Ontario",
    "Northern BC Rural": "Northern BC",
    "PEI Rural": "PEI",
    "Reserve Northern Ontario": "Indigenous Reserve Northern Ontario",
    "Nunavut Remote": "Nunavut",
}

RISK_CATEGORIES = [
    "affordability", "geographic", "timeline", "displacement",
    "fiscal", "employment", "infrastructure", "equity", "none",
]

SPECIALISTS = [
    {
        "id": "labor_economist",
        "title": "Labor Economist",
        "focus": "Labor market impacts: job creation, labor shortages, wage effects, employment shifts, skills gaps, construction workforce capacity",
        "categories": ["employment", "timeline"],
    },
    {
        "id": "urban_planner",
        "title": "Urban Planner",
        "focus": "Infrastructure and urban systems: transit capacity, utilities, schools, healthcare facilities, road networks, service delivery in new developments",
        "categories": ["infrastructure", "geographic"],
    },
    {
        "id": "fiscal_analyst",
        "title": "Fiscal Policy Analyst",
        "focus": "Government finances and taxation: municipal tax base changes, property tax impacts, government spending requirements, debt implications, cost-benefit of public investment",
        "categories": ["fiscal"],
    },
    {
        "id": "housing_economist",
        "title": "Housing Market Economist",
        "focus": "Housing supply and demand dynamics: price effects of new supply, rental market shifts, vacancy rate changes, speculative behavior, market absorption rates",
        "categories": ["affordability"],
    },
    {
        "id": "social_equity_researcher",
        "title": "Social Equity Researcher",
        "focus": "Distributional impacts: who benefits vs who bears costs, gentrification, displacement of vulnerable communities, access barriers, income inequality effects",
        "categories": ["equity", "displacement"],
    },
    {
        "id": "regional_development_analyst",
        "title": "Regional Development Analyst",
        "focus": "Geographic distribution: urban vs rural impacts, regional disparities, resource allocation across provinces, northern/remote community effects, Indigenous community impacts",
        "categories": ["geographic", "equity"],
    },
    {
        "id": "construction_industry_analyst",
        "title": "Construction Industry Analyst",
        "focus": "Construction sector capacity: material supply chains, contractor availability, building quality risks from rapid scaling, regulatory bottlenecks, zoning and permitting",
        "categories": ["timeline", "infrastructure"],
    },
    {
        "id": "demographic_economist",
        "title": "Demographic Economist",
        "focus": "Population and migration effects: immigration pull factors, internal migration patterns, aging population impacts, household formation trends, demand projections by age cohort",
        "categories": ["displacement", "affordability"],
    },
]

os.makedirs("cache", exist_ok=True)


def log(msg):
    print(msg, flush=True)


# --- City data helpers ---

# Approximate annual income midpoints by bracket (used for stress threshold math)
_INCOME_MIDPOINTS = {
    "very_low": 18000,
    "low": 32000,
    "medium": 58000,
    "high": 95000,
    "very_high": 160000,
}

# Rent-to-income thresholds (annualised rent / annual income)
_STRESS_THRESHOLD = 0.30      # standard affordability line
_HIGH_STRESS_THRESHOLD = 0.50  # housing stress
_DISPLACEMENT_THRESHOLD = 0.65 # displacement risk


def build_city_context(agent):
    city_key = CITY_NAME_MAP.get(agent["city"], agent["city"])
    city_data = CITY_PROFILES.get(city_key, {})

    parts = []
    if city_data.get("avg_rent_1br"):
        parts.append(f"avg_rent_1br: ${city_data['avg_rent_1br']:.0f}")
    if city_data.get("avg_rent_2br"):
        parts.append(f"avg_rent_2br: ${city_data['avg_rent_2br']:.0f}")
    if city_data.get("vacancy_rate") is not None:
        parts.append(f"vacancy: {city_data['vacancy_rate']}%")
    if city_data.get("median_household_income"):
        parts.append(f"median_income: ${city_data['median_household_income']:.0f}")
    if city_data.get("shelter_cost_to_income_ratio"):
        parts.append(f"shelter_cost_ratio: {city_data['shelter_cost_to_income_ratio']}")
    if city_data.get("unemployment_rate") is not None:
        parts.append(f"unemployment: {city_data['unemployment_rate']}%")
    if city_data.get("population"):
        parts.append(f"pop: {city_data['population']:.0f}")
    if city_data.get("population_growth_rate") is not None:
        parts.append(f"pop_growth: {city_data['population_growth_rate']}%")
    if city_data.get("housing_starts_annual"):
        parts.append(f"housing_starts: {city_data['housing_starts_annual']}")
    city_line = ", ".join(parts) if parts else "city data unavailable"

    age_income_line = ""
    income_by_age = city_data.get("income_by_age", {})
    if agent["age_bracket"] in income_by_age:
        age_income_line = f"\nDemographic income: median for {agent['age_bracket']} in {agent['city']}: ${income_by_age[agent['age_bracket']]:.0f}"

    # Compute rent-to-income stress flags for renters
    stress_flags = []
    if agent["tenure"] == "renter":
        # Use age-specific income if available, else bracket midpoint
        annual_income = income_by_age.get(agent["age_bracket"])
        if annual_income is None:
            annual_income = _INCOME_MIDPOINTS.get(agent["income_bracket"], 50000)

        family_size = agent.get("family_size", "single")
        rent_field = "avg_rent_2br" if family_size in ("small_family", "large_family", "couple") else "avg_rent_1br"
        monthly_rent = city_data.get(rent_field) or city_data.get("avg_rent_1br")

        if monthly_rent and annual_income > 0:
            rti = (monthly_rent * 12) / annual_income
            if rti >= _DISPLACEMENT_THRESHOLD:
                stress_flags.append(
                    f"DISPLACEMENT RISK: rent-to-income {rti:.2f} (>{_DISPLACEMENT_THRESHOLD:.0%} threshold) — housing loss is a realistic near-term outcome"
                )
            elif rti >= _HIGH_STRESS_THRESHOLD:
                stress_flags.append(
                    f"HOUSING STRESS: rent-to-income {rti:.2f} (>{_HIGH_STRESS_THRESHOLD:.0%} threshold) — severely cost-burdened, limited buffer for rent increases"
                )
            elif rti >= _STRESS_THRESHOLD:
                stress_flags.append(
                    f"COST-BURDENED: rent-to-income {rti:.2f} (>{_STRESS_THRESHOLD:.0%} standard affordability line)"
                )

    stress_line = ("\n" + "\n".join(stress_flags)) if stress_flags else ""

    return city_line, age_income_line + stress_line


def build_all_cities_summary():
    """Build a summary of all city data for specialists."""
    lines = []
    for city_key, data in CITY_PROFILES.items():
        parts = []
        if data.get("avg_rent_1br"):
            parts.append(f"rent_1br=${data['avg_rent_1br']:.0f}")
        if data.get("vacancy_rate") is not None:
            parts.append(f"vacancy={data['vacancy_rate']}%")
        if data.get("unemployment_rate") is not None:
            parts.append(f"unemp={data['unemployment_rate']}%")
        if data.get("population"):
            parts.append(f"pop={data['population']:.0f}")
        if data.get("housing_starts_annual"):
            parts.append(f"starts={data['housing_starts_annual']}")
        if data.get("median_household_income"):
            parts.append(f"income=${data['median_household_income']:.0f}")
        if parts:
            lines.append(f"  {city_key}: {', '.join(parts)}")
    return "\n".join(lines)


# --- Round 1: Domain specialist analysis (expensive model) ---

async def call_specialist(client, thread_id, specialist, policy_text, policy_classification, cities_summary):
    ref_docs = get_relevant_docs(specialist["categories"], policy_classification)
    ref_block = format_docs_for_prompt(ref_docs)
    survey_block = format_survey_stats_for_prompt(policy_classification, specialist["categories"])
    historical_block = format_historical_precedents_for_specialist(
        specialist["categories"], policy_classification
    )
    # Build citation list for the JSON schema (doc titles the model can reference)
    citation_options = [{"id": str(i+1), "title": d["title"], "url": d["url"]} for i, d in enumerate(ref_docs)]

    base_prompt = f"""You are a {specialist['title']} analyzing a Canadian government policy.

Your domain: {specialist['focus']}

Policy: {policy_text}
Policy classification: {json.dumps(policy_classification)}

Real city data from Statistics Canada:
{cities_summary}

{survey_block}

{ref_block}

{historical_block}

Before identifying any risks, do two things:
1. State the policy's DIRECT MECHANISM in one sentence — what specific action does this policy require, prohibit, or create?
2. Identify any BUILT-IN MITIGATION — does the policy contain a rebate, exemption, transition fund, phase-in, or offset that directly limits the harm you are about to flag? If yes, factor it into your severity score. A rebate that returns 90% of revenue changes the net impact. A 5-year new construction exemption changes who bears the cost. An income cap changes who can access the benefit. These are not footnotes — they are part of the mechanism.

Only identify risks that are CAUSED or MATERIALLY WORSENED by this policy's specific mechanism — not pre-existing problems, not trends the policy touches on thematically, not second-order speculation more than 2 causal steps from the policy action. If the policy's own mitigation fully addresses a risk, do not flag it. If the mitigation is structurally insufficient (wrong scale, wrong group, wrong timing), flag the residual risk and explain why the mitigation falls short.

For TAX policies: always reason about TAX INCIDENCE before flagging a risk. Who legally pays the tax is not always who economically bears it. A tax on undeveloped land falls on landholders who don't build — not on buyers of future homes. A tax on short-term sales falls on investors who flip — not on renters. If you cannot trace a direct line from who pays the tax to who is harmed, do not flag it as a risk.

For time-limited policies (benefits, emergency programs, phase-ins): explicitly assess the CLIFF EFFECT — what happens when this policy ends or phases out? Abrupt withdrawal of income support, housing assistance, or market interventions often produces risks that are larger than the ongoing policy itself. If a cliff effect exists, flag it as a distinct risk with timeline "escalating".

Identify 2-4 specific risks that this policy CREATES or WORSENS. For each risk, ground it in the real city data above. Reference specific numbers. Explain the economic mechanism — the causal chain from the policy's specific action to the negative outcome. Where possible, cite the reference documents and historical precedents provided above.

If historical precedent data is available above, include a "historical_precedent" field on the risk — one sentence referencing what happened in the comparable policy case. This is the most important credibility signal in the output.

Return only valid JSON:
{{
    "specialist": "{specialist['id']}",
    "risks": [
        {{
            "risk": "one sentence describing the specific risk",
            "mechanism": "2-3 sentences: the causal chain from policy to risk, referencing real data",
            "severity": 1|2|3,
            "category": "one of: {"|".join(c for c in RISK_CATEGORIES if c != 'none')}",
            "most_exposed": "which demographic groups bear this risk and why",
            "cities_most_affected": ["list", "of", "cities"],
            "historical_precedent": "one sentence citing a comparable Canadian policy outcome, or null",
            "citations": [{{"id": "1", "title": "...", "url": "..."}}]
        }}
    ]
}}
citations: reference 1-2 documents from the list above that support this risk. Use the exact id, title, and url provided. If no document directly applies, use an empty array.
Where severity means:
  1 = LOW — affects a small or narrow group, manageable with existing supports, unlikely to compound
  2 = MEDIUM — affects a meaningful share of a demographic group in multiple cities, limited mitigation available
  3 = HIGH — affects a large share of a vulnerable population nationally, likely to compound with other risks, hard to mitigate
Only use severity 3 if you would be comfortable defending it with specific population percentages and city data. When in doubt, use 2."""

    # Inject policy-specific focus directive (zero-cost, deterministic)
    prompt = calibrate_specialist_prompt(base_prompt, specialist, policy_classification, cities_summary)

    # For low-relevance specialists, add a hard scope constraint
    relevance = get_specialist_relevance(specialist, policy_classification)
    if relevance <= 0.3:
        prompt += (
            "\n\nNOTE: Your domain has limited direct relevance to this policy type. "
            "Only flag a risk if you can draw a direct causal line from this policy's specific mechanism to your domain. "
            "If no such risk exists, return an empty risks array. Do not force a connection."
        )

    fallback = {
        "specialist": specialist["id"],
        "risks": [],
    }

    try:
        response = await client.add_message(
            thread_id=thread_id,
            content=prompt,
            llm_provider=SPECIALIST_PROVIDER,
            model_name=SPECIALIST_MODEL,
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        # Validate each risk
        valid_risks = []
        for r in parsed.get("risks", []):
            if "risk" in r and "severity" in r and "category" in r:
                r["severity"] = r["severity"] if isinstance(r["severity"], int) and 1 <= r["severity"] <= 3 else 2
                r["category"] = r["category"] if r["category"] in RISK_CATEGORIES else "none"
                # Validate citations — keep only well-formed entries
                raw_cites = r.get("citations", [])
                r["citations"] = [
                    c for c in raw_cites
                    if isinstance(c, dict) and c.get("title") and c.get("url")
                ]
                # Preserve historical_precedent if present and non-empty
                hp = r.get("historical_precedent")
                r["historical_precedent"] = hp if isinstance(hp, str) and hp.strip() else None
                valid_risks.append(r)
        return {"specialist": specialist["id"], "risks": valid_risks}
    except Exception as e:
        log(f"  [WARN] Specialist {specialist['id']} failed: {e}")
        return fallback


async def run_specialists(client, asst_id, policy_text, policy_classification, pre_threads=None, cities_summary=None):
    """Run all domain specialists in parallel.

    Accepts pre_threads (already created in parallel with classify_policy) and
    a pre-built cities_summary to avoid redundant work.
    """
    if cities_summary is None:
        cities_summary = build_all_cities_summary()

    if pre_threads is None:
        pre_threads = await asyncio.gather(*[client.create_thread(asst_id) for _ in SPECIALISTS])

    results = await asyncio.gather(
        *[
            call_specialist(client, t.thread_id, s, policy_text, policy_classification, cities_summary)
            for t, s in zip(pre_threads, SPECIALISTS)
        ],
        return_exceptions=True,
    )

    return [r for r in results if not isinstance(r, Exception)]


# --- Round 2: Demographic validation (cheap model) ---

def build_validation_context(specialist_results):
    """Build a summary of top specialist findings for validators.

    Takes the highest-severity risk from each specialist, plus any severity-3
    risks, deduped by category. Caps at ~10 risks to keep the prompt short.
    """
    # Collect all risks with source
    all_risks = []
    for sr in specialist_results:
        for r in sr.get("risks", []):
            all_risks.append({
                "source": sr["specialist"],
                "risk": r["risk"],
                "mechanism": r.get("mechanism", ""),
                "severity": r["severity"],
                "category": r["category"],
                "most_exposed": r.get("most_exposed", ""),
                "cities_most_affected": r.get("cities_most_affected", []),
            })

    # Take highest-severity risk per specialist
    top_per_specialist = {}
    for r in all_risks:
        src = r["source"]
        if src not in top_per_specialist or r["severity"] > top_per_specialist[src]["severity"]:
            top_per_specialist[src] = r

    # Start with top per specialist, then add any remaining severity-3 risks
    selected = list(top_per_specialist.values())
    selected_keys = {(r["source"], r["risk"]) for r in selected}
    for r in all_risks:
        if r["severity"] == 3 and (r["source"], r["risk"]) not in selected_keys:
            selected.append(r)
            selected_keys.add((r["source"], r["risk"]))

    # Cap at 10 and sort by severity descending
    selected = sorted(selected, key=lambda r: -r["severity"])[:10]

    lines = []
    for i, r in enumerate(selected, 1):
        lines.append(f"Risk {i} [{r['category']}] (severity {r['severity']}/3):")
        lines.append(f"  {r['risk']}")
        lines.append(f"  Mechanism: {r['mechanism']}")
        lines.append("")

    return "\n".join(lines), selected


async def call_validator(client, thread_id, agent, policy_text, validation_context, behavioral_profile=None, cohort_stats=None):  # noqa: E501
    city_line, age_income_line = build_city_context(agent)

    persona_block = ""
    if behavioral_profile:
        cs = cohort_stats or {}
        persona_block = "\n\n" + format_persona_for_prompt(behavioral_profile, cs)

    prompt = f"""You are validating specialist risk assessments as a real person with the following profile. Domain experts identified the following risks for a Canadian policy. Your job: determine which risks ACTUALLY AFFECT someone matching your demographic profile, given your real city data.

Demographic profile: {agent['age_bracket']} {agent['tenure']} in {agent['city']}, {agent['income_bracket']} income, {agent['family_size']}, {agent['employment_type']}, {agent['immigration_status']}, {agent['debt_load']} debt
Real city data: {city_line}{age_income_line}{persona_block}

Policy: {policy_text}

Specialist-identified risks:
{validation_context}

For each risk, assess: does this risk ACTUALLY AFFECT someone with your specific profile and city data? Consider your income, tenure, location, employment type, and family situation.

Return only valid JSON:
{{
    "validations": [
        {{
            "risk_index": 1,
            "applies": true|false,
            "severity_for_me": 0|1|2|3,
            "reason": "one sentence — why this does or doesn't apply to your specific situation"
        }}
    ],
    "missed_risk": null or {{"risk": "one sentence", "category": "{"|".join(c for c in RISK_CATEGORIES if c != 'none')}", "severity": 1|2|3}}
}}
severity_for_me:
  0 = does not apply to my situation at all
  1 = minor inconvenience — I would adjust and cope without major hardship
  2 = significant impact — this would meaningfully affect my finances, housing, or employment
  3 = severe — this would cause serious hardship: housing instability, inability to afford essentials, or job loss
Be honest about your situation. Most policies affect most people at 0 or 1. Only use 3 if this risk would genuinely destabilize your life given your income and city data.
missed_risk: ONLY flag a risk that ALL of these are true: (1) it is NOT already covered by the specialist risks above, (2) it flows directly from THIS POLICY'S SPECIFIC MECHANISM — not a general life concern or background trend that exists regardless of this policy, (3) it specifically affects YOUR demographic profile — not a generic concern any Canadian would have, (4) you can explain WHY your age, tenure, income, employment type, or immigration status makes you uniquely exposed to this policy's action. If you cannot meet all four criteria, return null. Most agents should return null.

EXAMPLES OF WHAT TO REJECT: housing affordability concern in response to a pay equity policy (pre-existing, not caused by this policy); mental health concern in response to any policy (too generic); "I might lose my job" without a direct causal link to the specific policy mechanism."""

    fallback = {
        "agent_id": agent["id"],
        "city": agent["city"],
        "tenure": agent["tenure"],
        "age_bracket": agent["age_bracket"],
        "income_bracket": agent["income_bracket"],
        "immigration_status": agent["immigration_status"],
        "family_size": agent["family_size"],
        "employment_type": agent["employment_type"],
        "population_weight": agent["population_weight"],
        "city_data_used": {},
        "validations": [],
        "missed_risk": None,
        "behavioral_profile": behavioral_profile,
        "cohort_stats": cohort_stats if cohort_stats else None,
    }

    city_key = CITY_NAME_MAP.get(agent["city"], agent["city"])
    city_data = CITY_PROFILES.get(city_key, {})
    city_data_used = {k: v for k, v in {
        "avg_rent_1br": city_data.get("avg_rent_1br"),
        "avg_rent_2br": city_data.get("avg_rent_2br"),
        "vacancy_rate": city_data.get("vacancy_rate"),
        "median_household_income": city_data.get("median_household_income"),
        "shelter_cost_to_income_ratio": city_data.get("shelter_cost_to_income_ratio"),
        "unemployment_rate": city_data.get("unemployment_rate"),
        "population": city_data.get("population"),
        "population_growth_rate": city_data.get("population_growth_rate"),
        "housing_starts_annual": city_data.get("housing_starts_annual"),
        "income_for_age": city_data.get("income_by_age", {}).get(agent["age_bracket"]),
    }.items() if v is not None}

    for attempt in range(2):
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
            return {
                "agent_id": agent["id"],
                "city": agent["city"],
                "tenure": agent["tenure"],
                "age_bracket": agent["age_bracket"],
                "income_bracket": agent["income_bracket"],
                "immigration_status": agent["immigration_status"],
                "family_size": agent["family_size"],
                "employment_type": agent["employment_type"],
                "population_weight": agent["population_weight"],
                "city_data_used": city_data_used,
                "validations": parsed.get("validations", []),
                "missed_risk": parsed.get("missed_risk"),
                "behavioral_profile": behavioral_profile,
                "cohort_stats": cohort_stats if cohort_stats else None,
            }
        except Exception as e:
            if attempt == 0:
                continue
            log(f"  [WARN] Validator agent {agent['id']} ({agent['city']}) failed: {e}")
            return fallback

    return fallback


VALIDATOR_CONCURRENCY = 25  # raised from 15 — merged single-call per agent allows higher parallelism

_AI_POLICY_TYPES = {"ai", "technology", "digital"}
_AI_PERSONA_TYPES = {"ai", "technology", "digital", "labour"}


async def call_calibrate_and_validate(client, thread_id, agent, policy_text, validation_context, policy_classification, cohort_stats):
    """Single LLM call that does both persona calibration and risk validation in one pass.

    Replaces the previous two-call approach (calibrate_persona → call_validator) to halve
    the number of LLM round-trips and thread creates for the 50-agent validator panel.
    """
    city_line, age_income_line = build_city_context(agent)
    policy_type = (policy_classification.get("type") or "").lower()
    is_ai = policy_type in _AI_PERSONA_TYPES or any(
        kw in " ".join(policy_classification.get("key_attributes", [])).lower()
        for kw in {"ai", "artificial_intelligence", "automation", "tech", "digital"}
    )

    if is_ai:
        sector_profile = infer_sector_profile(agent)
        context_block = format_sector_for_persona_prompt(sector_profile)
        domain_label = "AI and technology governance"
        grounding_note = (
            "Based on the real StatsCan sector data above, ground your persona in this person's "
            "actual AI exposure and employment sector risk."
        )
    else:
        cohort_summary = build_cohort_summary(agent, cohort_stats, policy_classification)
        context_block = f"Statistics Canada CHS 2022 microdata for this demographic cohort:\n{cohort_summary}"
        domain_label = "Canadian housing policy"
        grounding_note = (
            "Based on the real CHS data above, ground your persona in this person's actual "
            "housing cost burden and financial fragility."
        )
        sector_profile = None

    prompt = f"""You are simulating a real Canadian demographic persona for a {domain_label} risk simulation.

Agent demographics:
- Age bracket: {agent.get('age_bracket')}
- City: {agent.get('city')}, {agent.get('province')}
- Tenure: {agent.get('tenure')}
- Income bracket: {agent.get('income_bracket')}
- Employment: {agent.get('employment_type')}
- Family size: {agent.get('family_size')}
- Immigration status: {agent.get('immigration_status')}
- Debt load: {agent.get('debt_load')}

Real city data: {city_line}{age_income_line}

{context_block}

{grounding_note}

Policy: {policy_text}

Specialist-identified risks:
{validation_context}

TASK: In a single response, do BOTH of the following:

1. PERSONA: Characterize this person's behavioral profile based on the real data above.
2. VALIDATION: As this person, assess which specialist risks actually affect them, given their real city data and circumstances.

For the validation — does each risk ACTUALLY AFFECT someone with this specific profile and city data?
For missed_risk — only flag a risk if: (1) NOT already covered above, (2) flows directly from THIS POLICY'S SPECIFIC MECHANISM — not a general life concern that exists regardless of this policy, (3) specifically affects THIS demographic profile, (4) you can explain WHY their age/tenure/income/employment/immigration makes them uniquely exposed to this policy's action. Housing affordability and mental health concerns are almost never valid missed_risks for non-housing policies — reject them unless there is a direct, named causal chain from this exact policy to that outcome.

Return only valid JSON:
{{
    "persona": {{
        "financial_fragility": "low|medium|high",
        "policy_stance": "supportive (net positive for me) | skeptical_of_benefit (sounds good but won't help me) | indifferent (doesn't affect me either way) | opposed (actively harms me)",
        "top_concerns": ["concern 1", "concern 2"],
        "lived_experience_note": "1-2 sentence narrative grounding this agent's perspective in the real data above"
    }},
    "validations": [
        {{
            "risk_index": 1,
            "applies": true|false,
            "severity_for_me": 0|1|2|3,
            "reason": "one sentence — why this does or doesn't apply to your specific situation"
        }}
    ],
    "missed_risk": null or {{"risk": "one sentence", "category": "{"|".join(c for c in RISK_CATEGORIES if c != 'none')}", "severity": 1|2|3}}
}}
severity_for_me: 0=does not apply, 1=minor inconvenience, 2=significant impact, 3=severe hardship.
Most risks affect most people at 0 or 1. Only use 3 if this would genuinely destabilize your life.
Most agents should return null for missed_risk."""

    city_key = CITY_NAME_MAP.get(agent["city"], agent["city"])
    city_data = CITY_PROFILES.get(city_key, {})
    city_data_used = {k: v for k, v in {
        "avg_rent_1br": city_data.get("avg_rent_1br"),
        "avg_rent_2br": city_data.get("avg_rent_2br"),
        "vacancy_rate": city_data.get("vacancy_rate"),
        "median_household_income": city_data.get("median_household_income"),
        "shelter_cost_to_income_ratio": city_data.get("shelter_cost_to_income_ratio"),
        "unemployment_rate": city_data.get("unemployment_rate"),
        "population": city_data.get("population"),
        "population_growth_rate": city_data.get("population_growth_rate"),
        "housing_starts_annual": city_data.get("housing_starts_annual"),
        "income_for_age": city_data.get("income_by_age", {}).get(agent["age_bracket"]),
    }.items() if v is not None}

    fallback_persona = {
        "financial_fragility": "medium",
        "policy_stance": "indifferent",
        "top_concerns": [],
        "lived_experience_note": "",
    }
    fallback = {
        "agent_id": agent["id"],
        "city": agent["city"],
        "tenure": agent["tenure"],
        "age_bracket": agent["age_bracket"],
        "income_bracket": agent["income_bracket"],
        "immigration_status": agent["immigration_status"],
        "family_size": agent["family_size"],
        "employment_type": agent["employment_type"],
        "population_weight": agent["population_weight"],
        "city_data_used": city_data_used,
        "validations": [],
        "missed_risk": None,
        "behavioral_profile": fallback_persona,
        "cohort_stats": cohort_stats or None,
    }

    for attempt in range(2):
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

            persona = parsed.get("persona", fallback_persona)
            # Sanitise persona fields
            if persona.get("financial_fragility") not in {"low", "medium", "high"}:
                persona["financial_fragility"] = "medium"
            if persona.get("policy_stance") not in {"supportive", "skeptical_of_benefit", "indifferent", "opposed"}:
                persona["policy_stance"] = "indifferent"
            if not isinstance(persona.get("top_concerns"), list):
                persona["top_concerns"] = []
            if not isinstance(persona.get("lived_experience_note"), str):
                persona["lived_experience_note"] = ""
            if sector_profile:
                persona["sector_profile"] = sector_profile

            return {
                "agent_id": agent["id"],
                "city": agent["city"],
                "tenure": agent["tenure"],
                "age_bracket": agent["age_bracket"],
                "income_bracket": agent["income_bracket"],
                "immigration_status": agent["immigration_status"],
                "family_size": agent["family_size"],
                "employment_type": agent["employment_type"],
                "population_weight": agent["population_weight"],
                "city_data_used": city_data_used,
                "validations": parsed.get("validations", []),
                "missed_risk": parsed.get("missed_risk"),
                "behavioral_profile": persona,
                "cohort_stats": cohort_stats or None,
            }
        except Exception as e:
            if attempt == 0:
                continue
            log(f"  [WARN] Validator agent {agent['id']} ({agent['city']}) failed: {e}")
            return fallback

    return fallback


async def run_validators(client, asst_id, agents, policy_text, validation_context, policy_classification, survey_stats):
    """Run merged calibration+validation in one LLM call per agent with raised concurrency.

    Pre-creates all threads in a single parallel batch before the semaphore loop,
    eliminating sequential thread-creation overhead inside the critical path.
    Returns (validator_results, behavioral_profiles).
    """
    _is_ai_policy = policy_classification.get("type") in _AI_POLICY_TYPES

    log(f"  Pre-creating {len(agents)} validator threads in batch...")
    threads = await asyncio.gather(*[client.create_thread(asst_id) for _ in agents])
    log(f"  Threads ready — running merged calibration+validation (concurrency={VALIDATOR_CONCURRENCY})...")

    sem = asyncio.Semaphore(VALIDATOR_CONCURRENCY)

    async def bounded_call(agent, thread):
        async with sem:
            cohort_stats = (
                {} if _is_ai_policy
                else pumf_matcher.get_cohort_stats(agent)
            )
            return await call_calibrate_and_validate(
                client, thread.thread_id, agent, policy_text, validation_context,
                policy_classification, cohort_stats,
            )

    results = await asyncio.gather(
        *[bounded_call(a, t) for a, t in zip(agents, threads)],
        return_exceptions=True,
    )

    valid_results = [r for r in results if r is not None and not isinstance(r, Exception)]
    behavioral_profiles = {r["agent_id"]: r["behavioral_profile"] for r in valid_results if r.get("behavioral_profile")}
    return valid_results, behavioral_profiles


async def call_deliberative_validator(client, thread_id, agent, policy_text, validation_context, dissenting_risks, behavioral_profile=None, cohort_stats=None):
    """
    Second-pass validator: shows the agent the highest-severity missed_risk
    from a validator with opposite tenure and asks if it changes their assessment.
    Only called for agents where a meaningful dissenting perspective exists.
    """
    city_line, age_income_line = build_city_context(agent)

    persona_block = ""
    if behavioral_profile:
        cs = cohort_stats or {}
        persona_block = "\n\n" + format_persona_for_prompt(behavioral_profile, cs)

    dissent_block = "\n".join(
        f"- [{r['from_tenure']} in {r['city']}] raised: {r['risk']} (severity {r['severity']}/3)"
        for r in dissenting_risks
    )

    prompt = f"""You previously assessed risks for this policy. A validator with a different housing tenure than yours has flagged risks that you did not raise.

Your profile: {agent['age_bracket']} {agent['tenure']} in {agent['city']}, {agent['income_bracket']} income, {agent['family_size']}, {agent['employment_type']}, {agent['immigration_status']}
Real city data: {city_line}{age_income_line}{persona_block}

Policy: {policy_text}

Original specialist risks (already assessed):
{validation_context}

Dissenting perspectives from validators with OPPOSITE tenure ({('owner' if agent['tenure'] == 'renter' else 'renter')}):
{dissent_block}

Do any of these dissenting risks change your assessment? Consider: does your demographic profile actually expose you to risks you initially dismissed? Are there second-order effects (e.g., market-wide rent increases affecting renters even if owners are the primary target) that you underweighted?

Return only valid JSON:
{{
    "revised_risks": [
        {{
            "dissent_index": 1,
            "now_applies": true|false,
            "revised_severity": 0|1|2|3,
            "reason": "one sentence — what changed in your assessment, or why it still doesn't apply to you"
        }}
    ]
}}
Be honest. If the dissenting risk genuinely does affect you after reflection, say so. If it still doesn't, explain why your specific situation insulates you."""

    fallback = {"agent_id": agent["id"], "revised_risks": []}

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
        return {
            "agent_id": agent["id"],
            "city": agent["city"],
            "tenure": agent["tenure"],
            "age_bracket": agent["age_bracket"],
            "income_bracket": agent["income_bracket"],
            "revised_risks": parsed.get("revised_risks", []),
            "dissenting_risks_shown": dissenting_risks,
        }
    except Exception as e:
        log(f"  [WARN] Deliberative validator {agent['id']} failed: {e}")
        return fallback


def _build_dissenting_risks(first_pass_results):
    """
    For each tenure group, collect the top missed_risks flagged by the OTHER tenure.
    Returns a dict: {agent_id: [list of dissenting risk dicts to show this agent]}
    Only agents where meaningful dissent exists are included.
    """
    # Group missed_risks by the tenure of who raised them
    renter_missed = []
    owner_missed = []
    for v in first_pass_results:
        mr = v.get("missed_risk")
        if not mr:
            continue
        entry = {**mr, "from_tenure": v["tenure"], "city": v["city"], "from_agent": v["agent_id"]}
        if v["tenure"] == "renter":
            renter_missed.append(entry)
        else:
            owner_missed.append(entry)

    # Sort by severity desc, take top 3 per side
    renter_missed.sort(key=lambda r: -r.get("severity", 0))
    owner_missed.sort(key=lambda r: -r.get("severity", 0))
    top_renter = renter_missed[:3]
    top_owner = owner_missed[:3]

    if not top_renter and not top_owner:
        return {}

    # Owners see renter-raised risks; renters see owner-raised risks
    assignments = {}
    for v in first_pass_results:
        if v["tenure"] == "owner" and top_renter:
            assignments[v["agent_id"]] = top_renter
        elif v["tenure"] == "renter" and top_owner:
            assignments[v["agent_id"]] = top_owner

    return assignments


async def run_deliberative_pass(client, asst_id, agents, policy_text, validation_context, first_pass_results, behavioral_profiles):
    """
    Deliberative second pass: each agent sees the top missed_risks raised by
    validators with the opposite tenure, then reconsiders their assessment.

    Skips agents where the dissenting risks are low-severity or already confirmed
    by that agent — no meaningful new information to deliberate on.
    Pre-batches thread creation for all revisit candidates.
    Returns a list of revised validator outputs (only agents who saw dissent).
    """
    dissent_map = _build_dissenting_risks(first_pass_results)
    if not dissent_map:
        log("  No cross-tenure dissent found — skipping deliberative pass")
        return []

    # Build a per-agent set of risks they already confirmed to filter out noise
    already_confirmed: dict[int, set[str]] = {}
    for v in first_pass_results:
        agent_confirmed = set()
        for val in v.get("validations", []):
            if val.get("applies"):
                agent_confirmed.add(str(val.get("risk_index", "")))
        already_confirmed[v["agent_id"]] = agent_confirmed

    # Only revisit agents where at least one dissenting risk has severity >= 2
    # and is genuinely new information (not a duplicate of something they confirmed)
    def has_meaningful_dissent(agent) -> bool:
        risks = dissent_map.get(agent["id"], [])
        return any(r.get("severity", 0) >= 2 for r in risks)

    agents_to_revisit = [a for a in agents if a["id"] in dissent_map and has_meaningful_dissent(a)]

    if not agents_to_revisit:
        log("  Dissent found but all signals low-severity — skipping deliberative pass")
        return []

    log(f"  Deliberative pass: {len(agents_to_revisit)} agents revisiting cross-tenure dissent (pre-batching threads...)")
    threads = await asyncio.gather(*[client.create_thread(asst_id) for _ in agents_to_revisit])

    sem = asyncio.Semaphore(VALIDATOR_CONCURRENCY)

    async def bounded_deliberate(agent, thread):
        async with sem:
            profile = behavioral_profiles.get(agent["id"])
            cohort_stats = pumf_matcher.get_cohort_stats(agent) if profile else {}
            return await call_deliberative_validator(
                client, thread.thread_id, agent, policy_text, validation_context,
                dissent_map[agent["id"]],
                behavioral_profile=profile, cohort_stats=cohort_stats,
            )

    results = await asyncio.gather(
        *[bounded_deliberate(a, t) for a, t in zip(agents_to_revisit, threads)],
        return_exceptions=True,
    )

    return [r for r in results if r is not None and not isinstance(r, Exception)]


# --- Python-computed severity (overrides LLM verdicts) ---

def compute_severity_labels(risk_validations: list, validator_results: list, benefits_data: dict | None) -> dict:
    """
    Computes overall_risk_level and per-risk severity entirely in Python.
    These values are passed to the coordinator as hard constraints — the LLM
    writes reasoning and titles but cannot change the numbers.

    Per-risk severity rules (in priority order):
      HIGH   — raw_confirmed >= 30 AND avg_severity_confirmed >= 2.0
             OR raw_confirmed >= 40 (regardless of severity — broad consensus)
      LOW    — raw_confirmed < 10
      MEDIUM — everything else

    Overall risk level:
      Take the top 3 risks by (raw_confirmed / total) × avg_severity_confirmed.
      Average those 3 scores.
      HIGH   >= 0.45
      LOW    <  0.15
      MEDIUM — everything else

    Net-impact adjustment:
      If benefits_data shows net_positive_validators > 35/50 AND overall would be HIGH,
      cap at MEDIUM — a policy where 70%+ validators are net positive is not HIGH risk.
    """
    total = len(validator_results)

    per_risk = []
    scores = []
    for rv in risk_validations:
        raw = rv["validators_confirmed"]
        avg_sev = rv["avg_severity_confirmed"]

        if raw >= 40 or (raw >= 30 and avg_sev >= 2.0):
            sev = "HIGH"
        elif raw < 10:
            sev = "LOW"
        else:
            sev = "MEDIUM"

        score = (raw / max(total, 1)) * avg_sev
        per_risk.append(sev)
        scores.append(score)

    # Overall: average of top 3 scores
    top3 = sorted(scores, reverse=True)[:3]
    avg_top3 = sum(top3) / max(len(top3), 1)

    if avg_top3 >= 0.45:
        overall = "HIGH"
    elif avg_top3 < 0.15:
        overall = "LOW"
    else:
        overall = "MEDIUM"

    # Net-impact cap: if majority validators are net positive, floor overall at MEDIUM
    if benefits_data:
        net_pos = benefits_data.get("summary", {}).get("net_positive_validators", 0)
        if net_pos > 30 and overall == "HIGH":
            overall = "MEDIUM"

    return {
        "overall_risk_level": overall,
        "per_risk_severity": per_risk,
        "scores": [round(s, 3) for s in scores],
        "avg_top3_score": round(avg_top3, 3),
    }


# --- Coordinator: Risk synthesis ---

def build_coordinator_prompt(policy_text, specialist_results, validator_results, specialist_risks, tension_text="", benefits_data=None, computed_severity=None):
    """Build coordinator prompt from specialist findings + demographic validation."""

    # Total population weight (dynamic agents are boosted-sampled so normalise)
    total_pop_weight = sum(v.get("population_weight", 1.0) for v in validator_results) or 1.0

    # Pre-compute rural validator count for blind_spots coverage note
    rural_validator_count = sum(
        1 for a in AGENTS
        if any(x in a["city"] for x in ["Northern", "Rural", "Nunavut", "PEI", "Reserve"])
    )

    # For each specialist risk compute raw counts AND population-weighted rates.
    # Dynamic agents over-sample renters (35/50 = 70% vs real Canada 35%) so raw
    # counts inflate renter-driven risks. The weighted rate corrects for this.
    risk_validations = []
    for i, risk in enumerate(specialist_risks):
        confirmed_by = []
        severities = []
        weighted_confirmed = 0.0
        weighted_severity_sum = 0.0

        for v in validator_results:
            pw = v.get("population_weight", 1.0)
            for val in v.get("validations", []):
                if val.get("risk_index") == i + 1 and val.get("applies"):
                    sev = val.get("severity_for_me", 0)
                    confirmed_by.append({
                        "agent_id": v["agent_id"],
                        "city": v["city"],
                        "tenure": v["tenure"],
                        "age_bracket": v["age_bracket"],
                        "income_bracket": v["income_bracket"],
                        "population_weight": round(pw, 4),
                        "reason": val.get("reason", ""),
                    })
                    severities.append(sev)
                    weighted_confirmed += pw
                    weighted_severity_sum += sev * pw

        risk_validations.append({
            "risk": risk["risk"],
            "mechanism": risk.get("mechanism", ""),
            "source_specialist": risk.get("source", ""),
            "original_severity": risk["severity"],
            "category": risk["category"],
            "most_exposed": risk.get("most_exposed", ""),
            "cities_most_affected": risk.get("cities_most_affected", []),
            "validators_confirmed": len(confirmed_by),
            "validators_total": len(validator_results),
            "population_weighted_confirmation_rate": round(weighted_confirmed / total_pop_weight, 3),
            "avg_severity_confirmed": round(sum(severities) / max(len(severities), 1), 1),
            "weighted_avg_severity": round(weighted_severity_sum / max(weighted_confirmed, 0.001), 2),
            "confirmed_demographics": confirmed_by[:10],
            # Python-computed severity — injected after risk_validations list is built
            "computed_severity": None,
        })

    # Collect missed risks from validators
    missed_risks = []
    for v in validator_results:
        if v.get("missed_risk"):
            missed_risks.append({
                "from_agent": v["agent_id"],
                "city": v["city"],
                "demographic": f"{v['age_bracket']} {v['tenure']} {v['income_bracket']}",
                **v["missed_risk"],
            })

    # Deduplicate risk_validations: if multiple risks share the same category AND
    # both have >= 20 confirmations, keep only the highest-confirmed one per category.
    # This prevents the coordinator from seeing 3 "affordability" risks and merging
    # them poorly — we pre-merge by keeping the best signal per category.
    seen_categories: dict[str, dict] = {}
    deduped = []
    for rv in risk_validations:
        cat = rv.get("category", "none")
        conf = rv["validators_confirmed"]
        if cat == "none" or conf < 20:
            # Low-confidence risks or uncategorised: keep as-is
            deduped.append(rv)
        elif cat not in seen_categories:
            seen_categories[cat] = rv
            deduped.append(rv)
        else:
            # Keep the higher-confirmed one; merge cities and mechanism into it
            existing = seen_categories[cat]
            if conf > existing["validators_confirmed"]:
                # New one is stronger — replace
                existing_idx = deduped.index(existing)
                rv["cities_most_affected"] = list(set(
                    rv.get("cities_most_affected", []) +
                    existing.get("cities_most_affected", [])
                ))[:5]
                deduped[existing_idx] = rv
                seen_categories[cat] = rv
            else:
                # Existing is stronger — merge cities into it
                existing["cities_most_affected"] = list(set(
                    existing.get("cities_most_affected", []) +
                    rv.get("cities_most_affected", [])
                ))[:5]

    risk_validations = deduped

    # Cap at top 8 by confirmation count
    risk_validations.sort(key=lambda x: x["validators_confirmed"], reverse=True)
    risk_validations = risk_validations[:8]

    # Inject computed severities into risk_validations
    if computed_severity:
        for i, rv in enumerate(risk_validations):
            if i < len(computed_severity["per_risk_severity"]):
                rv["computed_severity"] = computed_severity["per_risk_severity"][i]
            else:
                rv["computed_severity"] = "MEDIUM"
        computed_overall = computed_severity["overall_risk_level"]
    else:
        computed_overall = "MEDIUM"

    return f"""You are a senior policy risk analyst producing the final risk report for a Canadian policy.

Policy: {policy_text}

PROCESS: 8 domain specialists identified risks. Then 50 demographic personas validated each risk against their real city data. Below are the results.

SEVERITY IS PRE-COMPUTED: Each risk below has a "computed_severity" field calculated in Python from raw validator counts and average confirmed severity. You MUST use these exact values in your output — do not recalculate or override them. The overall_risk_level is also pre-computed: {computed_overall}. Use it exactly.

Specialist risks with demographic validation:
{json.dumps(risk_validations, indent=2)}

Additional risks flagged by demographic validators (missed by specialists):
{json.dumps(missed_risks, indent=2) if missed_risks else "None"}

Cross-demographic disagreement analysis (tenure, income, geography, age, immigration fault lines):
{tension_text if tension_text else "No tension analysis available."}

Benefits identified by domain specialists (who gains from this policy):
{json.dumps([{"benefit": b["benefit"], "magnitude": b["magnitude"], "primary_beneficiaries": b["primary_beneficiaries"], "caveat": b.get("caveat")} for b in (benefits_data.get("benefit_items", []) if benefits_data else [])], indent=2) if benefits_data and benefits_data.get("benefit_items") else "No benefits analysis available."}

Net impact summary across 50 validators (positive = net gain, negative = net loss):
{json.dumps({"by_tenure": benefits_data.get("net_by_tenure", {}), "by_income": benefits_data.get("net_by_income", {}), "net_positive_validators": benefits_data.get("summary", {}).get("net_positive_validators", 0), "net_negative_validators": benefits_data.get("summary", {}).get("net_negative_validators", 0)}, indent=2) if benefits_data else "Not available."}

Before producing the report, apply this MECHANISM FILTER to every risk in the input:
1. Write one sentence: "This policy [specific action] which causes [direct effect] which harms [group]."
2. Count the causal steps between the policy action and the harm. If there are more than 2 steps, reject the risk.
3. Ask: would this risk exist even if this policy were never passed? If yes, reject it.
4. For non-housing policies (healthcare, labour, benefits, regulation): any risk rooted in housing affordability or rental prices requires a DIRECT mechanism from this policy — not "disposable income changes affect rent" or "workers relocate to cities" — those are too indirect. Reject them.

After filtering, produce the final risk report. Include 3–5 distinct risks. Before writing the report, group all input risks by their ROOT CAUSAL MECHANISM:

Step 1: Write one sentence for each risk starting with "Because this policy [action], it causes [first-order effect]."
Step 2: If two risks have the same [action] → [first-order effect], they are the SAME risk. Merge them into one entry, listing all downstream effects in the reasoning.

Common merge patterns:
- "compliance costs burden SMEs" + "compliance costs reduce hiring" + "compliance costs slow AI adoption" → ONE risk: "Compliance cost burden on SMEs"
- "supply reduction → higher rents" + "supply reduction → displacement" + "supply reduction → affordability pressure" → ONE risk: "Reduced housing supply drives affordability pressure"
- Any two risks where the first causal step is identical → merge them

You should end up with 3–5 genuinely distinct first-order mechanisms. If you have more than 5, you have not merged enough. Where cross-demographic tensions are noted above, reflect them in your reasoning chain. Rank risks by:
1. Validation breadth — how many diverse demographic groups confirmed the risk
2. Average severity among those who confirmed it
3. Whether the risk was confirmed across multiple cities and tenure types (renters AND owners)

CRITICAL: Only include risks the policy CREATES or WORSENS, not pre-existing problems. Do not include a risk just because it appeared in specialist output — it must have meaningful validator confirmation (at least 10 validators confirming it). Hard rule: any risk with fewer than 10 confirmations is excluded unless it comes from a structurally underrepresented group (e.g. Indigenous reserve communities with only 2-3 validators where the low count reflects panel limits, not low real-world impact).

For validator-raised missed_risks: apply the same mechanism test — does this risk flow directly from what this policy specifically does? Reject it if you cannot name the specific causal chain.

MITIGATION ACCOUNTING: Before scoring each risk's severity, ask — does the policy itself contain a mechanism that offsets or limits this harm? A rebate, exemption, transition fund, or phase-in period that directly addresses the risk should reduce its severity by one level. Name the mitigation and explain why it is or isn't sufficient. A mitigation that exists on paper but is structurally inadequate (wrong scale, wrong target group, wrong timing) does not reduce severity.

For each risk, provide a REASONING CHAIN: (1) what economic mechanism this policy triggers, (2) what built-in mitigation exists and whether it's sufficient, (3) specific data points that support the residual risk, (4) which demographics confirmed it and why they're vulnerable, (5) confidence level based on validation breadth.

TIMELINE: For each risk, assess when it manifests. Use these categories:
- "immediate" — within 0–6 months of implementation (e.g. benefit starts flowing, landlords react to new rules)
- "short_term" — 6 months to 2 years (market absorption, behavioral responses)
- "medium_term" — 2–5 years (compounding structural effects, benefit erosion, construction pipeline)
- "long_term" — 5+ years (demographic shifts, market equilibrium effects, generational impacts)
If a risk evolves across multiple horizons (e.g. mild at first, worsens over time), use "escalating" and explain the trajectory.

CASCADE CHAINS: For the top 3 risks, identify whether they form a causal chain — where risk A materializes first and makes risk B more likely or more severe. If a chain exists, score its likelihood: LOW (risks are independent), MEDIUM (plausible mechanism but uncertain), HIGH (documented in comparable policy — reference the historical precedent). Do NOT describe cascades as just "it compounds things" — name the specific mechanism.

BLIND SPOTS: Report as a structured object, not a sentence. Cover:
1. Which demographic groups are structurally underrepresented in the validator panel and why (e.g., on-reserve Indigenous households — StatsCan microdata does not cover reserves). NOTE: the validator panel skews toward low-to-medium income renters. For policies with tax deduction or savings incentives, high-income earners who benefit most are underrepresented — flag this if relevant.
2. Which policy effects cannot be modeled (behavioral responses, political implementation quality, landlord strategy, uptake rates by income group). For housing supply policies, explicitly flag: community opposition and NIMBYism (documented to delay or block projects), municipal political will variability, and construction cost inflation under rapid build timelines.
3. What real-world data would most improve confidence if available
4. Whether the panel's income/tenure skew may have caused it to OVERSTATE risks that fall on renters and low-income households, or MISS benefits and risks that fall on owners and high-income households

OVERALL RISK LEVEL — already computed as {computed_overall}. Use this exact value in your output. Do not recalculate.

Return exactly this JSON:
{{
    "risks": [
        {{
            "rank": 1,
            "title": "short risk title",
            "severity": "copy exactly from computed_severity field above — do not change",
            "reasoning": "3-5 sentence reasoning chain grounded in specialist analysis and demographic validation",
            "affected_groups": "who bears this risk",
            "confirmed_by": 0,
            "out_of": {len(validator_results)},
            "cities": ["list", "of", "affected", "cities"],
            "timeline": "immediate|short_term|medium_term|long_term|escalating",
            "timeline_detail": "one sentence — when this risk materializes and how it evolves",
            "cascade_effect": {{
                "triggers": "which other risk title this feeds into, or null",
                "mechanism": "one sentence — the specific causal chain from this risk to the next",
                "likelihood": "LOW|MEDIUM|HIGH",
                "evidence": "one sentence — comparable policy or data point supporting this chain, or null"
            }}
        }}
    ],
    "blind_spots": {{
        "underrepresented_groups": "which demographic groups are structurally missing from the validator panel and why",
        "unmodeled_effects": "which real-world dynamics this simulation cannot capture",
        "data_gaps": "what real data would most improve confidence in these findings",
        "coverage_note": "Rural/remote validators represent {rural_validator_count}/50 validators by count but only ~4% of population weight in the panel. StatsCan CHS 2022 microdata does not cover on-reserve First Nations households — reserve community perspectives are approximated only.",
        "panel_skew_warning": "If this policy has tax deductions, savings incentives, or benefits that accrue primarily to high-income earners or homeowners, note that the validator panel skews toward low-to-medium income renters (35/50 renters, majority low-medium income) — the simulation may overstate risks to renters and miss risks or benefits specific to high-income or ownership groups. Otherwise return null."
    }},
    "overall_risk_level": "{computed_overall}",
    "key_insight": "one sentence — the single most important non-obvious finding that a policy analyst would not already expect. Must name a specific mechanism, group, threshold, or distributional effect. If the policy is primarily beneficial (supply creation, income support, access improvement), the insight should name WHO benefits most and WHY — not just catalogue risks. Generic statements are not acceptable."
}}"""


async def run_coordinator(client, asst_id, policy_text, specialist_results, validator_results, specialist_risks, tension_text="", benefits_data=None):
    # Compute severity in Python first — these are hard constraints passed to the LLM
    total_pop_weight = sum(v.get("population_weight", 1.0) for v in validator_results) or 1.0
    risk_validations_for_scoring = []
    for i, risk in enumerate(specialist_risks):
        confirmed = 0
        sevs = []
        for v in validator_results:
            for val in v.get("validations", []):
                if val.get("risk_index") == i + 1 and val.get("applies"):
                    confirmed += 1
                    sevs.append(val.get("severity_for_me", 0))
        risk_validations_for_scoring.append({
            "validators_confirmed": confirmed,
            "avg_severity_confirmed": sum(sevs) / max(len(sevs), 1) if sevs else 0.0,
        })
    computed_severity = compute_severity_labels(risk_validations_for_scoring, validator_results, benefits_data)
    log(f"  Python-computed overall: {computed_severity['overall_risk_level']} (avg_top3={computed_severity['avg_top3_score']})")
    for i, (sev, score) in enumerate(zip(computed_severity['per_risk_severity'], computed_severity['scores'])):
        log(f"    Risk {i+1}: {sev} (score={score})")

    prompt = build_coordinator_prompt(policy_text, specialist_results, validator_results, specialist_risks, tension_text, benefits_data, computed_severity)
    try:
        thread = await client.create_thread(asst_id)
        response = await client.add_message(
            thread_id=thread.thread_id,
            content=prompt,
            llm_provider=COORDINATOR_PROVIDER,
            model_name=COORDINATOR_MODEL,
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        # Hard-enforce Python-computed values — LLM cannot override these
        result["overall_risk_level"] = computed_severity["overall_risk_level"]

        # Build a lookup: confirmed_by count → Python severity
        # The coordinator reorders risks, so we match by confirmed_by count
        # Build from the scoring data used to compute severity
        conf_to_sev = {}
        for j, rv in enumerate(risk_validations_for_scoring):
            if j < len(computed_severity["per_risk_severity"]):
                conf_to_sev[rv["validators_confirmed"]] = computed_severity["per_risk_severity"][j]

        for i, risk in enumerate(result.get("risks", [])):
            conf = risk.get("confirmed_by", 0)
            # Try exact match first, then nearest, then positional
            if conf in conf_to_sev:
                risk["severity"] = conf_to_sev[conf]
            else:
                # Find closest confirmation count in scoring data
                nearest = min(conf_to_sev.keys(), key=lambda x: abs(x - conf), default=None)
                if nearest is not None:
                    risk["severity"] = conf_to_sev[nearest]
                elif i < len(computed_severity["per_risk_severity"]):
                    risk["severity"] = computed_severity["per_risk_severity"][i]

        # Fallback for blank key_insight
        if not result.get("key_insight"):
            top = result.get("risks", [{}])[0]
            result["key_insight"] = f"The highest-confirmed risk is {top.get('title','unknown')} ({top.get('confirmed_by',0)}/{len(validator_results)} validators confirmed it)."

        return result
    except Exception as e:
        log(f"  [WARN] Coordinator failed: {e}")
        return {
            "risks": [],
            "blind_spots": "coordinator unavailable",
            "overall_risk_level": "UNKNOWN",
            "key_insight": "coordinator unavailable",
        }


# --- Main simulation loop ---

async def run_simulation(policy_text, event_queue=None):
    async def emit(event: dict):
        if event_queue is not None:
            await event_queue.put(event)

    client = BackboardClient(api_key=BACKBOARD_API_KEY)

    log(f"\nCivica Risk Analysis: '{policy_text}'")
    log(f"Specialists: {len(SPECIALISTS)} ({SPECIALIST_PROVIDER}/{SPECIALIST_MODEL})")
    log(f"Validators: {len(AGENTS)} ({VALIDATOR_PROVIDER}/{VALIDATOR_MODEL})")
    log(f"Coordinator: {COORDINATOR_PROVIDER}/{COORDINATOR_MODEL}")
    log(f"Renters: {len(DEMOGRAPHIC_GROUPS['renters'])} | Owners: {len(DEMOGRAPHIC_GROUPS['owners'])}")
    log(f"Rural/remote: {len(DEMOGRAPHIC_GROUPS['rural'])} | Recent immigrants: {len(DEMOGRAPHIC_GROUPS['recent_immigrants'])}\n")
    start = time.time()

    # Create assistant
    assistant = await client.create_assistant(
        name="Civica Risk Analyst",
        system_prompt="You are a policy risk analyst. Always return valid JSON only.",
    )
    asst_id = assistant.assistant_id
    log(f"Created Backboard assistant: {asst_id}")

    # Classify policy + pre-create specialist threads in parallel
    log("Classifying policy and pre-creating specialist threads in parallel...")
    await emit({"type": "status", "message": "Classifying policy..."})
    cities_summary = build_all_cities_summary()

    async def _create_specialist_threads():
        return await asyncio.gather(*[client.create_thread(asst_id) for _ in SPECIALISTS])

    classify_task = asyncio.create_task(classify_policy(client, asst_id, policy_text))
    specialist_threads_task = asyncio.create_task(_create_specialist_threads())
    policy_classification, specialist_threads_pre = await asyncio.gather(classify_task, specialist_threads_task)
    log(f"Policy classified: {policy_classification['type']} | affects: {policy_classification['primary_affected']}")

    # ROUND 1: Domain specialist analysis (threads already created above)
    log(f"\nRound 1: {len(SPECIALISTS)} domain specialists analyzing policy...")
    await emit({"type": "status", "message": f"Round 1: {len(SPECIALISTS)} specialists analyzing policy..."})
    r1_start = time.time()
    specialist_results = await run_specialists(client, asst_id, policy_text, policy_classification, pre_threads=specialist_threads_pre, cities_summary=cities_summary)
    r1_time = time.time() - r1_start

    # Summarize specialist findings
    total_risks = sum(len(sr.get("risks", [])) for sr in specialist_results)
    log(f"Round 1 complete in {r1_time:.1f}s — {total_risks} risks from {len(specialist_results)} specialists")
    for sr in specialist_results:
        risks = sr.get("risks", [])
        if risks:
            cats = [r["category"] for r in risks]
            log(f"  {sr['specialist']}: {len(risks)} risks ({', '.join(cats)})")

    # Build validation context
    validation_context, specialist_risks = build_validation_context(specialist_results)
    log(f"\nSpecialist risks to validate: {len(specialist_risks)}")
    await emit({"type": "r1_complete", "specialists": specialist_results, "specialist_risks": specialist_risks})

    # ROUND 2: Demographic validation + Benefits analysis (parallel)
    log(f"\nRound 2: {len(AGENTS)} demographic validators checking risks + benefits analysis...")
    _is_ai = policy_classification.get("type") in ("ai", "technology", "digital")
    _calibration_label = "AI sector exposure data" if _is_ai else "CHS 2022 microdata"
    await emit({"type": "status", "message": f"Round 2: Calibrating {len(AGENTS)} validator personas against {_calibration_label}..."})
    r2_start = time.time()
    (validator_results, behavioral_profiles), benefit_results_raw = await asyncio.gather(
        run_validators(client, asst_id, AGENTS, policy_text, validation_context, policy_classification, SURVEY_STATS),
        run_benefits_analysis(client, asst_id, SPECIALISTS, policy_text, policy_classification),
    )
    r2_time = time.time() - r2_start
    total_benefits = sum(len(br.get("benefits", [])) for br in benefit_results_raw)
    log(f"Benefits analysis complete — {total_benefits} benefits identified across {len(benefit_results_raw)} specialists")

    # Summarize validation
    total_confirmations = 0
    for v in validator_results:
        for val in v.get("validations", []):
            if val.get("applies"):
                total_confirmations += 1
    missed_count = sum(1 for v in validator_results if v.get("missed_risk"))
    log(f"Round 2 complete in {r2_time:.1f}s — {total_confirmations} risk confirmations, {missed_count} new risks flagged")

    # ROUND 2b: Deliberative pass — cross-tenure exposure
    log(f"\nRound 2b: Deliberative pass — exposing agents to cross-tenure dissent...")
    await emit({"type": "status", "message": "Round 2b: Deliberative pass — agents reconsidering cross-tenure perspectives..."})
    r2b_start = time.time()
    deliberative_results = await run_deliberative_pass(
        client, asst_id, AGENTS, policy_text, validation_context,
        validator_results, behavioral_profiles,
    )
    r2b_time = time.time() - r2b_start
    revised_count = sum(
        1 for dr in deliberative_results
        for rr in dr.get("revised_risks", [])
        if rr.get("now_applies")
    )
    log(f"Round 2b complete in {r2b_time:.1f}s — {len(deliberative_results)} agents revisited, {revised_count} newly confirmed risks")

    # Per-risk confirmation counts
    for i, risk in enumerate(specialist_risks):
        confirmed = sum(
            1 for v in validator_results
            for val in v.get("validations", [])
            if val.get("risk_index") == i + 1 and val.get("applies")
        )
        log(f"  Risk {i+1} [{risk['category']}]: {confirmed}/{len(validator_results)} confirmed — {risk['risk'][:80]}")

    await emit({"type": "r2_complete", "validators": validator_results})
    await emit({"type": "r2b_complete", "deliberative": deliberative_results})
    await emit({"type": "status", "message": "Detecting cross-demographic fault lines..."})

    # Aggregate benefits + net impact scoring
    log("\nAggregating benefits and net impact per demographic...")
    benefits_data = aggregate_benefits(benefit_results_raw, validator_results)
    log(f"  Net positive: {benefits_data['summary']['net_positive_validators']} validators, "
        f"net negative: {benefits_data['summary']['net_negative_validators']}, "
        f"neutral: {benefits_data['summary']['net_neutral_validators']}")

    # Tension detection: cross-demographic disagreement analysis
    log("\nDetecting cross-demographic tensions...")
    tensions, tension_text = run_tension_detection(validator_results, specialist_risks)
    log(f"  {len(tensions)} fault lines detected")
    if tensions:
        for t in tensions[:3]:
            log(f"    Risk {t['risk_index']} [{t['dimension']}]: {t['group_a']} {t['rate_a']:.0%} vs {t['group_b']} {t['rate_b']:.0%}")

    # COORDINATOR: Synthesize risk report
    log("\nCoordinator synthesizing risk report...")
    await emit({"type": "status", "message": "Coordinator synthesizing risk report..."})
    c_start = time.time()
    risk_report = await run_coordinator(
        client, asst_id, policy_text, specialist_results, validator_results,
        specialist_risks, tension_text, benefits_data,
    )
    log(f"Coordinator complete in {time.time() - c_start:.1f}s")

    total_time = time.time() - start
    log(f"\nAnalysis complete in {total_time:.1f}s")

    # Save outputs
    output = {
        "policy": policy_text,
        "total_time_seconds": round(total_time, 2),
        "specialists_total": len(SPECIALISTS),
        "validators_total": len(AGENTS),
        "models": {
            "specialist": f"{SPECIALIST_PROVIDER}/{SPECIALIST_MODEL}",
            "validator": f"{VALIDATOR_PROVIDER}/{VALIDATOR_MODEL}",
            "coordinator": f"{COORDINATOR_PROVIDER}/{COORDINATOR_MODEL}",
        },
        "round_1_specialists": specialist_results,
        "specialist_risks": specialist_risks,
        "round_2_validators": validator_results,
        "round_2b_deliberative": deliberative_results,
        "risk_report": risk_report,
        "demographic_tensions": tensions,
        "benefits": benefits_data,
    }

    with open("cache/round_1_specialists.json", "w") as f:
        json.dump(specialist_results, f, indent=2)
    with open("cache/round_2_validators.json", "w") as f:
        json.dump(validator_results, f, indent=2)

    # Confidence score
    confidence = calculate_confidence(
        policy_classification,
        CITY_PROFILES,
        specialist_results,
        validator_results,
    )
    output["confidence"] = confidence
    output["policy_classification"] = policy_classification

    # Seal for forward validation
    seal_id = seal_simulation(policy_text, output)
    output["seal_id"] = seal_id

    # Single write with all fields populated
    with open("cache/full_simulation.json", "w") as f:
        json.dump(output, f, indent=2)

    log(f"\nConfidence: {confidence['score']}/{confidence['out_of']} — {confidence['reason']}")
    log(f"Seal ID: {seal_id}")

    await emit({"type": "done", "data": output})

    return output
