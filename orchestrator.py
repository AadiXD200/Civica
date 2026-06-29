import asyncio
import hashlib
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
from fiscal_scorecard import run_fiscal_scorecard
from institutional_panel import get_institutional_personas, generate_institutional_personas, run_institutional_validation, build_institutional_summary_block
from peer_reviewer import run_peer_review, build_peer_review_block
from specialist_calibrator import calibrate_specialist_prompt, get_specialist_relevance
from benefits_analyzer import run_benefits_analysis, aggregate_benefits
from persona_calibrator import format_persona_for_prompt, build_cohort_summary
from sector_inference import infer_sector_profile, format_sector_for_persona_prompt
from tension_detector import run_tension_detection
import pumf_matcher

load_dotenv()


def _compute_panel_version(agents: list) -> str:
    """Stable hash of panel composition — same agents in any order → same ID."""
    fingerprints = sorted(
        f"{a.get('agent_id','')}:{a.get('tenure','')}:{a.get('city','')}:{a.get('income_bracket','')}:{a.get('age_bracket','')}:{a.get('domain_persona', False)}"
        for a in agents
    )
    return hashlib.md5("\n".join(fingerprints).encode()).hexdigest()[:10]


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

# ── Domain-specific specialist rosters ───────────────────────────────────────
# Keyed by domain string returned by classify_policy.
# Each list is exactly 8 specialists to keep concurrency uniform.

_DOMAIN_SPECIALISTS: dict[str, list[dict]] = {
    "healthcare": [
        {"id": "health_economist", "title": "Health Economist", "focus": "Healthcare financing, drug pricing, insurance market dynamics, cost-effectiveness of public vs private coverage, out-of-pocket expenditure impacts", "categories": ["fiscal", "affordability"]},
        {"id": "pharmacist_analyst", "title": "Pharmacist & Drug Supply Analyst", "focus": "Formulary design, drug supply chains, generic vs brand substitution, dispensing fee impacts, pharmacy business models", "categories": ["infrastructure", "employment"]},
        {"id": "provincial_relations", "title": "Federal-Provincial Relations Expert", "focus": "Constitutional jurisdiction, opt-out mechanics, asymmetric agreements, transfer conditions, intergovernmental negotiations", "categories": ["geographic", "fiscal"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Access gaps by income, geography, and immigration status; Indigenous health disparities; chronic disease burden in vulnerable populations", "categories": ["equity", "displacement"]},
        {"id": "labour_market_analyst", "title": "Labour Market Analyst", "focus": "Impacts on healthcare workforce: nursing, pharmacy, administrative staff; employer drug benefit displacement; gig worker coverage gaps", "categories": ["employment"]},
        {"id": "insurance_industry_analyst", "title": "Private Insurance Industry Analyst", "focus": "Private insurer market displacement, employer plan transition costs, supplementary coverage market, industry restructuring", "categories": ["fiscal", "affordability"]},
        {"id": "regional_development_analyst", "title": "Regional & Rural Health Analyst", "focus": "Rural and remote access to formulary drugs, pharmacy deserts, telemedicine integration, northern community supply chains", "categories": ["geographic", "equity"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Implementation risks, moral hazard, formulary limitations, political feasibility, unintended consequences, opt-out incentive structures", "categories": ["fiscal", "equity"]},
    ],
    "labour": [
        {"id": "labor_economist", "title": "Labor Economist", "focus": "Wage floors, employment elasticity, hours reduction, labor substitution, sector-specific impacts", "categories": ["employment"]},
        {"id": "small_business_analyst", "title": "Small Business Analyst", "focus": "SME compliance costs, payroll impacts, thin-margin sectors (hospitality, retail, agriculture), hiring freezes", "categories": ["employment", "fiscal"]},
        {"id": "automation_analyst", "title": "Automation & Technology Analyst", "focus": "Labour-saving technology adoption rates, capital-for-labour substitution, gig economy restructuring", "categories": ["employment", "timeline"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Distributional impacts by income bracket, youth and newcomer employment, precarious work patterns", "categories": ["equity"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Government payroll tax revenue, EI and social transfer interactions, compliance enforcement costs", "categories": ["fiscal"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Province-by-province labour market variation, rural employment, resource sector impacts", "categories": ["geographic", "equity"]},
        {"id": "union_relations_analyst", "title": "Labour Relations Analyst", "focus": "Collective bargaining implications, union density effects, strike risk, sectoral wage compression", "categories": ["employment"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Unintended employment effects, evasion mechanisms, enforcement gaps, constitutional labour jurisdiction", "categories": ["fiscal", "equity"]},
    ],
    "fiscal": [
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Federal budget impacts, deficit financing, tax expenditure accounting, revenue projections", "categories": ["fiscal"]},
        {"id": "tax_economist", "title": "Tax Economist", "focus": "Tax incidence, avoidance and evasion behavior, capital gains dynamics, corporate tax shifting", "categories": ["fiscal", "affordability"]},
        {"id": "provincial_relations", "title": "Federal-Provincial Fiscal Expert", "focus": "Transfer payment structures, equalization formula impacts, shared-cost programs, fiscal federalism", "categories": ["fiscal", "geographic"]},
        {"id": "labor_economist", "title": "Labor Economist", "focus": "Labour supply distortions from taxation, income effect on work hours, high-earner emigration", "categories": ["employment"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Distributional analysis of tax burden and benefit incidence across income quintiles", "categories": ["equity"]},
        {"id": "capital_markets_analyst", "title": "Capital Markets Analyst", "focus": "Investment incentive effects, business investment decisions, capital allocation, financial sector impacts", "categories": ["fiscal"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Regional economic impacts, resource-dependent province exposure, interprovincial competitiveness", "categories": ["geographic"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Revenue forecast reliability, behavioural response uncertainty, implementation complexity, international comparison", "categories": ["fiscal"]},
    ],
    "climate": [
        {"id": "climate_economist", "title": "Climate & Energy Economist", "focus": "Carbon pricing efficiency, clean energy transition costs, stranded asset risk, green investment multipliers", "categories": ["fiscal", "affordability"]},
        {"id": "fossil_fuel_analyst", "title": "Fossil Fuel Industry Analyst", "focus": "Oil & gas sector impacts, royalty revenue, Alberta fiscal exposure, export competitiveness", "categories": ["employment", "fiscal"]},
        {"id": "clean_tech_analyst", "title": "Clean Technology Analyst", "focus": "Renewable energy deployment, EV adoption curves, grid modernization, cleantech job creation", "categories": ["employment", "infrastructure"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Carbon cost burden on low-income households, rural heating costs, Indigenous resource rights", "categories": ["equity"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Province-by-province energy mix variation, resource community transition, northern infrastructure", "categories": ["geographic", "equity"]},
        {"id": "urban_planner", "title": "Urban & Buildings Analyst", "focus": "Building retrofit mandates, urban heat island, transit electrification, zoning for density", "categories": ["infrastructure"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Carbon revenue recycling, federal-provincial transfer interactions, green bond financing", "categories": ["fiscal"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Competitiveness leakage, carbon border adjustment feasibility, political durability, measurement and enforcement", "categories": ["fiscal", "geographic"]},
    ],
    "immigration": [
        {"id": "immigration_economist", "title": "Immigration Economist", "focus": "Immigrant labour market integration, wage complementarity vs competition, credential recognition gaps", "categories": ["employment", "affordability"]},
        {"id": "housing_economist", "title": "Housing Market Economist", "focus": "Population-driven housing demand pressure, rental market tightening in gateway cities", "categories": ["affordability"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Newcomer service access gaps, discrimination in hiring, refugee vs economic immigrant outcomes", "categories": ["equity"]},
        {"id": "settlement_services_analyst", "title": "Settlement Services Analyst", "focus": "Language training capacity, settlement agency funding, integration program throughput", "categories": ["infrastructure", "equity"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Rural immigration streams, regional nominee programs, small-city absorption capacity", "categories": ["geographic"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Net fiscal contribution of immigrants, transfer dependency, health and education cost projections", "categories": ["fiscal"]},
        {"id": "provincial_relations", "title": "Federal-Provincial Relations Expert", "focus": "Provincial nominee programs, healthcare and education jurisdiction, asylum seeker cost-sharing", "categories": ["geographic", "fiscal"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Processing backlogs, fraud risk, international treaty obligations, public opinion dynamics", "categories": ["equity", "fiscal"]},
    ],
    "education": [
        {"id": "education_economist", "title": "Education Economist", "focus": "Returns to education, student debt burden, labour market signal value of credentials, skill mismatch", "categories": ["employment", "affordability"]},
        {"id": "provincial_relations", "title": "Federal-Provincial Relations Expert", "focus": "Education jurisdiction, transfer conditions, provincial autonomy, curriculum standards", "categories": ["geographic", "fiscal"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Access gaps by income and geography, Indigenous education outcomes, newcomer integration", "categories": ["equity"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Post-secondary funding models, tuition revenue, student loan default rates, public investment ROI", "categories": ["fiscal"]},
        {"id": "labour_market_analyst", "title": "Labour Market Analyst", "focus": "Graduate employment outcomes, skilled trade shortages, credential inflation, employer upskilling", "categories": ["employment"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Rural school consolidation, northern access, brain drain from small communities", "categories": ["geographic"]},
        {"id": "technology_analyst", "title": "EdTech & Digital Learning Analyst", "focus": "Online learning scalability, digital divide, AI in education, infrastructure requirements", "categories": ["infrastructure", "equity"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Implementation timelines, institutional resistance, credential devaluation risks, international student impacts", "categories": ["fiscal", "equity"]},
    ],
    "transit": [
        {"id": "transit_economist", "title": "Transit & Mobility Economist", "focus": "Ridership demand elasticity, fare revenue, modal shift from car to transit, congestion pricing", "categories": ["affordability", "fiscal"]},
        {"id": "urban_planner", "title": "Urban Planner", "focus": "Transit-oriented development, station area density, last-mile connectivity, land use integration", "categories": ["infrastructure", "geographic"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Capital cost financing, federal-provincial-municipal cost-sharing, P3 risk allocation, operating subsidies", "categories": ["fiscal"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Transit access for low-income, seniors, and disabled riders; fare affordability; equity of service distribution", "categories": ["equity"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Rural transit gaps, intercity connectivity, Indigenous community access, small-city service models", "categories": ["geographic", "equity"]},
        {"id": "labour_market_analyst", "title": "Labour Market Analyst", "focus": "Transit operator workforce, construction jobs, commute time effects on labour supply", "categories": ["employment"]},
        {"id": "climate_analyst", "title": "Climate & Emissions Analyst", "focus": "Vehicle emission reductions from modal shift, electrification of transit fleet, climate target contribution", "categories": ["infrastructure"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Ridership projections reliability, construction overruns, political jurisdiction conflicts, displacement during construction", "categories": ["fiscal", "geographic"]},
    ],
    "ai": [
        {"id": "ai_economist", "title": "AI & Automation Economist", "focus": "Labour displacement from AI, productivity gains, wage polarization, task-level automation exposure by occupation", "categories": ["employment", "affordability"]},
        {"id": "technology_policy_analyst", "title": "Technology Policy Analyst", "focus": "AI governance frameworks, algorithmic accountability, data governance, international regulatory comparison", "categories": ["fiscal", "equity"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Algorithmic bias, facial recognition disparities, AI-driven discrimination in hiring/lending/benefits", "categories": ["equity"]},
        {"id": "privacy_analyst", "title": "Privacy & Data Rights Analyst", "focus": "Surveillance risks, data sovereignty, consent frameworks, PIPEDA reform implications", "categories": ["equity", "infrastructure"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Compliance costs for industry, government AI procurement, enforcement agency capacity", "categories": ["fiscal"]},
        {"id": "innovation_analyst", "title": "Innovation & Competitiveness Analyst", "focus": "Canadian AI sector competitiveness, brain drain risk, startup burden, US/EU regulatory arbitrage", "categories": ["employment", "fiscal"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Uneven AI adoption across regions, rural digital divide, resource sector AI use", "categories": ["geographic"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Definitional ambiguity, enforcement gaps, innovation chilling effect, constitutional jurisdiction over private sector AI", "categories": ["fiscal", "equity"]},
    ],
    "corrections": [
        {"id": "criminal_justice_economist", "title": "Criminal Justice Economist", "focus": "Incarceration costs, recidivism rates, cost-effectiveness of rehabilitation vs incarceration, public safety outcomes", "categories": ["fiscal"]},
        {"id": "social_equity_researcher", "title": "Social Equity Researcher", "focus": "Racial and Indigenous overrepresentation, systemic bias, re-entry barriers, family impacts", "categories": ["equity"]},
        {"id": "fiscal_analyst", "title": "Fiscal Policy Analyst", "focus": "Correctional service budgets, capital costs for facility expansion, provincial transfer payments", "categories": ["fiscal"]},
        {"id": "labour_market_analyst", "title": "Labour Market Analyst", "focus": "Post-release employment barriers, correctional officer workforce, prison labour programs", "categories": ["employment"]},
        {"id": "mental_health_analyst", "title": "Mental Health & Addictions Analyst", "focus": "Mental health burden in corrections, addiction treatment access, trauma-informed approaches", "categories": ["equity", "infrastructure"]},
        {"id": "regional_development_analyst", "title": "Regional Development Analyst", "focus": "Rural facility siting, Indigenous community impact, northern access to legal services", "categories": ["geographic", "equity"]},
        {"id": "provincial_relations", "title": "Federal-Provincial Relations Expert", "focus": "Jurisdictional split between federal and provincial corrections, transfer of offenders, parole board authority", "categories": ["geographic", "fiscal"]},
        {"id": "policy_critic", "title": "Policy Critic", "focus": "Mandatory minimum evidence base, constitutional charter challenges, political feasibility, international human rights standards", "categories": ["equity", "fiscal"]},
    ],
}

# Cross-cutting specialists always included for non-housing domains
_ALWAYS_INCLUDE = {"social_equity_researcher", "fiscal_analyst", "regional_development_analyst", "policy_critic"}


def get_specialists_for_domain(domain: str) -> list[dict]:
    """Return the 8-specialist roster for a given domain, falling back to housing."""
    domain = (domain or "housing").lower()
    return _DOMAIN_SPECIALISTS.get(domain, SPECIALISTS)

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

def _filter_cities_summary(cities_summary: str, specialist: dict) -> str:
    """
    Non-regional specialists get a trimmed city summary — major urban centres only.
    Regional/geographic specialists get the full summary including rural/remote.
    This prevents every specialist from latching onto Nunavut/Northern Ontario as
    a default rural-exclusion framing when it's not their analytical domain.
    """
    is_regional = any(c in specialist.get("categories", []) for c in ("geographic",)) or \
        any(kw in specialist.get("id", "").lower() for kw in ("regional", "rural", "geographic", "northern", "remote"))
    if is_regional:
        return cities_summary
    # Return only lines that don't mention rural/remote/reserve/nunavut/northern
    _rural_markers = {"rural", "remote", "reserve", "nunavut", "northern"}
    filtered = []
    for line in cities_summary.splitlines():
        if not any(m in line.lower() for m in _rural_markers):
            filtered.append(line)
    return "\n".join(filtered)


async def call_specialist(client, thread_id, specialist, policy_text, policy_classification, cities_summary):
    ref_docs = get_relevant_docs(specialist["categories"], policy_classification)
    ref_block = format_docs_for_prompt(ref_docs)
    survey_block = format_survey_stats_for_prompt(policy_classification, specialist["categories"])
    historical_block = format_historical_precedents_for_specialist(
        specialist["categories"], policy_classification
    )
    # Build citation list for the JSON schema (doc titles the model can reference)
    citation_options = [{"id": str(i+1), "title": d["title"], "url": d["url"]} for i, d in enumerate(ref_docs)]

    # Non-regional specialists get urban-only city data to prevent rural-framing convergence
    specialist_cities_summary = _filter_cities_summary(cities_summary, specialist)

    base_prompt = f"""You are a {specialist['title']} analyzing a Canadian government policy.

Your domain: {specialist['focus']}

Policy: {policy_text}
Policy classification: {json.dumps(policy_classification)}

Real city data from Statistics Canada:
{specialist_cities_summary}

{survey_block}

{ref_block}

{historical_block}

CRITICAL INSTRUCTION — LENS DISCIPLINE:
You are a {specialist['title']}. Every risk you identify MUST flow from YOUR SPECIFIC PROFESSIONAL LENS — not from a generic equity or access concern that any analyst could raise.
Ask yourself: "What do I see from my specific vantage point that other specialists cannot?" If your finding could have been written by a generic policy analyst, it is not specific enough. Rewrite it from your exact domain perspective.

Examples of lens discipline:
- A "Parental Controls Analyst" must reason about the specific parental-attestation or override mechanics in the bill — not generic digital exclusion
- A "Pharmaceutical Supply Chain Analyst" must reason about formulary logistics, dispensing, and distribution — not generic affordability
- A "Labour Relations Analyst" must reason about collective agreement clauses, strike risk, and wage compression — not generic employment effects

Before identifying any risks, do two things:
1. State the policy's DIRECT MECHANISM in one sentence — what specific action does this policy require, prohibit, or create?
2. Identify any BUILT-IN MITIGATION — does the policy contain a rebate, exemption, transition fund, phase-in, or offset that directly limits the harm you are about to flag? If yes, factor it into your severity score.

DEDUPLICATION RULE: Before finalizing your findings, check: are any of your risks essentially the same causal chain described in different words? If two risks share the same mechanism and affected population, merge them into one. Do not submit more than one finding about "exclusion of vulnerable groups" or "compliance cost burden" — pick the most specific version and cut the rest.

CATEGORY DISCIPLINE: Use `geographic` ONLY if the primary risk mechanism is geographic — i.e. location itself determines who is harmed, not just that some places have fewer resources. Do not tag a risk `geographic` just because rural areas exist or because the policy affects multiple regions differently — that applies to almost every policy. If the real mechanism is affordability, label it `affordability`. If it's employment loss in a sector, label it `employment`. Reserve `geographic` for risks where someone's physical location is the direct cause of harm (e.g. no broadband → can't comply; remote → no alternative supplier).

Only identify risks that are CAUSED or MATERIALLY WORSENED by this policy's specific mechanism — not pre-existing problems, not trends the policy touches on thematically, not second-order speculation more than 2 causal steps from the policy action.

For TAX policies: always reason about TAX INCIDENCE before flagging a risk. Who legally pays the tax is not always who economically bears it.

For time-limited policies (benefits, emergency programs, phase-ins): explicitly assess the CLIFF EFFECT — what happens when this policy ends or phases out?

Identify 2-4 specific risks that this policy CREATES or WORSENS. For each risk, ground it in the real city data above. Reference specific numbers. Explain the economic mechanism — the causal chain from the policy's specific action to the negative outcome.

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


async def generate_specialist_roster(client, asst_id, policy_text, policy_classification) -> list[dict]:
    """Ask the LLM to generate 8 policy-specific specialists for this exact policy."""
    prompt = f"""You are designing a policy risk analysis panel for a specific Canadian government policy.

Policy: {policy_text}
Classification: {json.dumps(policy_classification)}

Generate exactly 8 specialist roles that cover DISTINCT analytical traditions for this policy.

HARD RULES:
1. Each specialist must come from a DIFFERENT analytical tradition. No two specialists may share a primary lens.
   - BANNED: more than one specialist whose primary lens is equity/access/inclusion/rights/marginalization. One Social Equity Researcher covers that entire tradition — do not add "Digital Rights Analyst", "Youth Advocate", "Civil Rights Analyst", "Digital Literacy Analyst" etc. alongside it. These are the same lens.
   - BANNED: more than one specialist whose primary lens is compliance cost or regulatory burden on business.
   - BANNED: more than one specialist whose primary lens is rural/geographic access.
2. The 8 slots must cover genuinely different risk dimensions. A good panel for an age-gating/screen-time policy would include slots like: legal/constitutional, platform economics, behavioural science, parental/family systems, enforcement/implementation, fiscal/compliance, regional, and equity — each a distinct tradition.
3. Always include exactly one Policy Critic and exactly one Social Equity Researcher. The other 6 must be domain-specific technical roles, not variations on equity or access themes.
4. Each specialist's focus must name a specific mechanism from THIS policy — not a general concern.

For each specialist return:
- id: snake_case unique identifier
- title: professional title (e.g. "Platform Revenue Economist")
- focus: one sentence on what they analyze — must reference the policy's specific mechanism
- categories: list of 1-2 strings from [employment, fiscal, affordability, equity, displacement, infrastructure, geographic, timeline]

Return only valid JSON with no markdown:
{{
  "specialists": [
    {{"id": "...", "title": "...", "focus": "...", "categories": ["..."]}}
  ]
}}"""

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
        parsed = json.loads(raw)
        specialists = parsed.get("specialists", [])
        if len(specialists) == 8:
            log(f"  Generated specialist roster: {[s['title'] for s in specialists]}")
            return specialists
    except Exception as e:
        log(f"  Specialist generation failed ({e}), falling back to domain lookup")

    # Fallback to domain lookup
    domain = (policy_classification or {}).get("type", "housing")
    return get_specialists_for_domain(domain)


async def generate_validator_personas(client, asst_id, policy_text, policy_classification, n: int = 15) -> list[dict]:
    """Ask the LLM to generate n domain-specific validator personas for this policy."""

    # Derive explicit persona quotas so the LLM doesn't default to generic adult spread
    policy_type = (policy_classification or {}).get("type", "")
    domain_label = (policy_classification or {}).get("domain_label", policy_type)
    key_attrs = " ".join((policy_classification or {}).get("key_attributes", [])).lower()

    is_youth_policy = any(kw in (policy_text + key_attrs).lower() for kw in
        {"age verification", "age gating", "minor", "under 16", "under 18", "youth", "screen time", "parental consent", "children"})
    is_elder_policy = any(kw in (policy_text + key_attrs).lower() for kw in
        {"seniors", "elder", "long-term care", "retirement", "pension", "dementia", "aging"})
    is_worker_policy = any(kw in (policy_text + key_attrs).lower() for kw in
        {"minimum wage", "gig worker", "labour", "employment insurance", "union", "collective bargaining"})

    if is_youth_policy:
        quota_instruction = f"""MANDATORY PERSONA DISTRIBUTION for this youth/age-gating policy (must sum to {n}):
- {n//2} personas aged 18-24 (young adults directly affected as near-minor users, or as older siblings/peers of minors)
- {n//4} personas aged 25-34 (parents of minors, early-career adults with children)
- {n//4} personas aged 35-49 (parents of teenagers, guardians navigating consent requirements)
Zero personas aged 50-64 or 65+. This policy's primary affected population is youth and parents of youth — not retirees."""
    elif is_elder_policy:
        quota_instruction = f"""MANDATORY PERSONA DISTRIBUTION for this seniors/elder policy (must sum to {n}):
- {n//2} personas aged 65+ (primary affected population)
- {n//4} personas aged 50-64 (approaching retirement, caregivers for aging parents)
- {n//4} personas aged 35-49 (adult children managing elder care)"""
    elif is_worker_policy:
        quota_instruction = f"""MANDATORY PERSONA DISTRIBUTION for this labour/worker policy (must sum to {n}):
- {n//2} personas in gig/self_employed/hourly employment (primary affected workers)
- {n//4} personas aged 18-24 (young workers most exposed to wage floors and gig economy)
- {n//4} personas as small business owners or salaried workers affected by cost pass-through"""
    else:
        quota_instruction = f"""Distribute {n} personas across the demographics MOST DIRECTLY affected by this specific policy's mechanism. Do not default to a generic Canadian spread — think about who this policy actually touches first."""

    prompt = f"""You are designing demographic validator personas for a Canadian policy risk simulation.

Policy: {policy_text}
Classification: {json.dumps(policy_classification)}

{quota_instruction}

These personas represent people who will DIRECTLY feel the effects — not bystanders who are vaguely concerned.
Each persona's domain_role and domain_context must describe their specific relationship to THIS policy's mechanism.

Return only valid JSON with no markdown:
{{
  "personas": [
    {{
      "city": "Toronto",
      "tenure": "renter",
      "age_bracket": "18-24",
      "income_bracket": "low",
      "employment_type": "student",
      "immigration_status": "born_here",
      "family_size": "single",
      "debt_load": "low",
      "domain_role": "19-year-old university student and heavy TikTok/Instagram user",
      "domain_context": "Uses social media 4h/day; turned 18 last year so technically exempt but younger friends face the verification barrier"
    }}
  ]
}}

age_bracket options: 18-24, 25-34, 35-49, 50-64, 65+
income_bracket options: very_low, low, medium, high, very_high
employment_type options: salaried, self_employed, gig, unemployed, retired, student
immigration_status options: born_here, established_immigrant, recent_immigrant, non_permanent_resident
family_size options: single, couple, small_family, large_family
debt_load options: none, low, medium, high
tenure options: renter, owner"""

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
        parsed = json.loads(raw)
        personas = parsed.get("personas", [])
        if personas:
            log(f"  Generated {len(personas)} domain validator personas: {[p.get('domain_role') for p in personas[:5]]}...")
            return personas[:n]
    except Exception as e:
        log(f"  Validator persona generation failed ({e}), using PUMF-only panel")

    return []


async def run_specialists(client, asst_id, policy_text, policy_classification, pre_threads=None, cities_summary=None, specialists=None):
    """Run all domain specialists in parallel.

    Accepts pre_threads (already created in parallel with classify_policy) and
    a pre-built cities_summary to avoid redundant work.
    """
    if specialists is None:
        domain = (policy_classification or {}).get("type", "housing")
        specialists = get_specialists_for_domain(domain)

    if cities_summary is None:
        cities_summary = build_all_cities_summary()

    if pre_threads is None:
        pre_threads = await asyncio.gather(*[client.create_thread(asst_id) for _ in specialists])

    results = await asyncio.gather(
        *[
            call_specialist(client, t.thread_id, s, policy_text, policy_classification, cities_summary)
            for t, s in zip(pre_threads, specialists)
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
    _housing_types = {"housing", "supply", "demand", "rent_control", "zoning", "tenant_protection"}
    is_housing = policy_type in _housing_types

    # Domain label — used in prompt framing so validator reasons from the right context
    _DOMAIN_LABELS = {
        "healthcare": "Canadian healthcare policy", "labour": "Canadian labour market policy",
        "fiscal": "Canadian fiscal and tax policy", "climate": "Canadian climate and energy policy",
        "environment": "Canadian climate and energy policy", "immigration": "Canadian immigration policy",
        "education": "Canadian education policy", "transit": "Canadian transit policy",
        "ai": "Canadian AI and technology governance policy", "corrections": "Canadian criminal justice policy",
    }
    domain_label = _DOMAIN_LABELS.get(policy_type, f"Canadian {policy_type} policy")

    # Domain-injected persona context (for LLM-generated domain personas)
    domain_role = agent.get("domain_role", "")
    domain_context = agent.get("domain_context", "")
    domain_persona_block = ""
    if domain_role and domain_context:
        domain_persona_block = f"\nYour specific role: {domain_role}\nYour situation: {domain_context}\nReason from THIS specific situation — not from generic demographic assumptions."

    sector_profile = None
    if is_ai:
        sector_profile = infer_sector_profile(agent)
        context_block = format_sector_for_persona_prompt(sector_profile)
        grounding_note = (
            "Based on the real StatsCan sector data above, ground your persona in this person's "
            "actual AI exposure and employment sector risk."
        )
    elif is_housing:
        cohort_summary = build_cohort_summary(agent, cohort_stats, policy_classification)
        context_block = f"Statistics Canada CHS 2022 microdata for this demographic cohort:\n{cohort_summary}"
        grounding_note = (
            "Based on the real CHS data above, ground your persona in this person's actual "
            "housing cost burden and financial fragility."
        )
    else:
        # Non-housing, non-AI: use city income/employment data as the grounding anchor
        cohort_summary = build_cohort_summary(agent, cohort_stats, policy_classification)
        context_block = f"Statistics Canada data for this demographic cohort:\n{cohort_summary}"
        grounding_note = (
            f"Ground your persona in how this person's income level, employment type, and city "
            f"context makes them specifically exposed or insulated from this {policy_type} policy."
        )

    prompt = f"""You are simulating a real Canadian demographic persona for a {domain_label} risk simulation.

Agent demographics:
- Age bracket: {agent.get('age_bracket')}
- City: {agent.get('city')}, {agent.get('province')}
- Tenure: {agent.get('tenure')}
- Income bracket: {agent.get('income_bracket')}
- Employment: {agent.get('employment_type')}
- Family size: {agent.get('family_size')}
- Immigration status: {agent.get('immigration_status')}
- Debt load: {agent.get('debt_load')}{domain_persona_block}

Real city data: {city_line}{age_income_line}

{context_block}

{grounding_note}

Policy: {policy_text}

Specialist-identified risks:
{validation_context}

TASK: In a single response, do BOTH of the following:

1. PERSONA: Characterize this person's behavioral profile based on the real data above. If a specific role and situation is given above, use it — do not substitute generic assumptions.
2. VALIDATION: As this person, assess which specialist risks actually affect YOU, given your specific situation and city data. Your validation must be grounded in your actual demographic circumstances — not in what a generic person might experience.

CRITICAL: Your reason for each validation must reference YOUR SPECIFIC SITUATION (your income, your employment, your family, your domain role if given). Generic answers like "this could affect vulnerable people" are rejected — you are one specific person, reason as them.

For missed_risk — only flag a risk if: (1) NOT already covered above, (2) flows directly from THIS POLICY'S SPECIFIC MECHANISM, (3) specifically affects YOUR profile because of something particular about your age/employment/income/immigration status, (4) you can name the direct causal chain. Return null if uncertain.

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
      HIGH   — raw_confirmed >= 35 AND avg_severity_confirmed >= 2.2
             OR raw_confirmed >= 45 (near-unanimous consensus regardless of severity)
      LOW    — raw_confirmed < 8
      MEDIUM — everything else

    Overall risk level:
      Take the top 3 risks by (raw_confirmed / total) × avg_severity_confirmed.
      Average those 3 scores.
      HIGH   >= 0.60   (requires both broad confirmation AND high severity — not just one)
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

        if raw >= 45 or (raw >= 35 and avg_sev >= 2.2):
            sev = "HIGH"
        elif raw < 8:
            sev = "LOW"
        else:
            sev = "MEDIUM"

        score = (raw / max(total, 1)) * avg_sev
        per_risk.append(sev)
        scores.append(score)

    # Overall: average of top 3 scores
    top3 = sorted(scores, reverse=True)[:3]
    avg_top3 = sum(top3) / max(len(top3), 1)

    if avg_top3 >= 0.60:
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

def build_coordinator_prompt(policy_text, specialist_results, validator_results, specialist_risks, tension_text="", benefits_data=None, computed_severity=None, institutional_results=None, peer_review=None):
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

{build_institutional_summary_block(institutional_results) if institutional_results else ""}

{build_peer_review_block(peer_review) if peer_review else ""}

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


async def run_coordinator(client, asst_id, policy_text, specialist_results, validator_results, specialist_risks, tension_text="", benefits_data=None, institutional_results=None, peer_review=None):
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

    prompt = build_coordinator_prompt(policy_text, specialist_results, validator_results, specialist_risks, tension_text, benefits_data, computed_severity, institutional_results=institutional_results, peer_review=peer_review)
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

async def run_simulation(policy_text, event_queue=None, enable_peer_review: bool = False):
    async def emit(event: dict):
        if event_queue is not None:
            await event_queue.put(event)

    client = BackboardClient(api_key=BACKBOARD_API_KEY)

    log(f"\nCivica Risk Analysis: '{policy_text}'")
    log(f"Specialists: 8 ({SPECIALIST_PROVIDER}/{SPECIALIST_MODEL}) — domain roster selected after classification")
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
        return await asyncio.gather(*[client.create_thread(asst_id) for _ in range(8)])

    classify_task = asyncio.create_task(classify_policy(client, asst_id, policy_text))
    specialist_threads_task = asyncio.create_task(_create_specialist_threads())
    policy_classification, specialist_threads_pre = await asyncio.gather(classify_task, specialist_threads_task)
    log(f"Policy classified: {policy_classification['type']} | affects: {policy_classification['primary_affected']}")
    domain = (policy_classification or {}).get("type", "other")

    # Generate specialist roster + validator personas in parallel (LLM-driven, policy-specific)
    log("Generating specialist roster and validator personas...")
    await emit({"type": "status", "message": "Building policy-specific panel..."})
    # More injected personas for policies where PUMF age distribution is structurally wrong
    _policy_text_lower = policy_text.lower()
    _persona_n = 25 if any(kw in _policy_text_lower for kw in {
        "age verification", "age gating", "minor", "under 16", "under 18",
        "parental consent", "screen time", "children", "youth",
        "seniors", "elder", "long-term care", "pension",
    }) else 15

    active_specialists, generated_personas = await asyncio.gather(
        generate_specialist_roster(client, asst_id, policy_text, policy_classification),
        generate_validator_personas(client, asst_id, policy_text, policy_classification, n=_persona_n),
    )
    log(f"Specialist roster ({len(active_specialists)}): {[s['title'] for s in active_specialists]}")

    # Inject generated personas into the PUMF panel
    panel_agents = list(AGENTS)
    if generated_personas:
        from agent_generator import _inject_generated_personas
        panel_agents = _inject_generated_personas(panel_agents, generated_personas)
        log(f"Injected {len(generated_personas)} generated personas into validator panel")

    # ROUND 1: Domain specialist analysis (threads already created above)
    log(f"\nRound 1: {len(active_specialists)} domain specialists analyzing policy...")
    await emit({"type": "status", "message": f"Round 1: {len(active_specialists)} specialists analyzing policy..."})
    r1_start = time.time()
    specialist_results = await run_specialists(client, asst_id, policy_text, policy_classification, pre_threads=specialist_threads_pre, cities_summary=cities_summary, specialists=active_specialists)
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
    log(f"\nRound 2: {len(panel_agents)} demographic validators checking risks + benefits analysis...")
    _is_ai = policy_classification.get("type") in ("ai", "technology", "digital")
    _calibration_label = "AI sector exposure data" if _is_ai else "CHS 2022 microdata"
    await emit({"type": "status", "message": f"Round 2: Calibrating {len(panel_agents)} validator personas against {_calibration_label}..."})
    r2_start = time.time()
    (validator_results, behavioral_profiles), benefit_results_raw = await asyncio.gather(
        run_validators(client, asst_id, panel_agents, policy_text, validation_context, policy_classification, SURVEY_STATS),
        run_benefits_analysis(client, asst_id, active_specialists, policy_text, policy_classification),
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

    # INSTITUTIONAL PANEL: Generate policy-specific actors + run validations
    log("\nGenerating institutional actor panel...")
    await emit({"type": "status", "message": "Building institutional actor panel..."})
    institutional_personas = await generate_institutional_personas(
        client, asst_id, policy_text, policy_classification,
        llm_provider=COORDINATOR_PROVIDER, llm_model=COORDINATOR_MODEL,
    )
    log(f"  Institutional actors: {[p['label'] for p in institutional_personas]}")
    institutional_results = await run_institutional_validation(
        client, asst_id, policy_text, institutional_personas, specialist_risks,
        llm_provider=VALIDATOR_PROVIDER, llm_model=VALIDATOR_MODEL,
    )
    log(f"  Institutional panel: {len(institutional_results)} actors validated")

    # PEER REVIEW: Adversarial critique (optional)
    peer_review = None
    if enable_peer_review:
        log("\nRunning adversarial peer review...")
        await emit({"type": "status", "message": "Adversarial peer review running..."})
        peer_review = await run_peer_review(
            client, asst_id, policy_text, specialist_results, specialist_risks,
            llm_provider=SPECIALIST_PROVIDER, llm_model=SPECIALIST_MODEL,
        )
        log(f"  Peer review: {len(peer_review.get('critiques', []))} critiques")

    # COORDINATOR: Synthesize risk report
    log("\nCoordinator synthesizing risk report...")
    await emit({"type": "status", "message": "Coordinator synthesizing risk report..."})
    c_start = time.time()
    risk_report = await run_coordinator(
        client, asst_id, policy_text, specialist_results, validator_results,
        specialist_risks, tension_text, benefits_data,
        institutional_results=institutional_results, peer_review=peer_review,
    )
    log(f"Coordinator complete in {time.time() - c_start:.1f}s")

    total_time = time.time() - start
    log(f"\nAnalysis complete in {total_time:.1f}s")

    # Save outputs
    output = {
        "policy": policy_text,
        "total_time_seconds": round(total_time, 2),
        "specialists_total": len(active_specialists),
        "validators_total": len(panel_agents),
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
        "institutional_panel": institutional_results,
        "peer_review": peer_review,
    }

    with open("cache/round_1_specialists.json", "w") as f:
        json.dump(specialist_results, f, indent=2)
    with open("cache/round_2_validators.json", "w") as f:
        json.dump(validator_results, f, indent=2)

    # Confidence score + fiscal scorecard (parallel)
    confidence, fiscal_scorecard = await asyncio.gather(
        asyncio.to_thread(
            calculate_confidence,
            policy_classification,
            CITY_PROFILES,
            specialist_results,
            validator_results,
            domain=domain,
        ),
        run_fiscal_scorecard(
            client, asst_id, policy_text, specialist_results,
            llm_provider=COORDINATOR_PROVIDER, llm_model=COORDINATOR_MODEL,
        ),
    )
    output["confidence"] = confidence
    output["fiscal_scorecard"] = fiscal_scorecard
    output["policy_classification"] = policy_classification
    output["panel_version_id"] = _compute_panel_version(panel_agents)

    # Seal for forward validation
    seal_id = seal_simulation(policy_text, output)
    output["seal_id"] = seal_id

    # Single write with all fields populated
    with open("cache/full_simulation.json", "w") as f:
        json.dump(output, f, indent=2)

    log(f"\nConfidence: {confidence['score']}/{confidence['out_of']} — {confidence['reason']}")
    log(f"Seal ID: {seal_id} | Panel: {output['panel_version_id']}")

    await emit({"type": "done", "data": output})

    return output
