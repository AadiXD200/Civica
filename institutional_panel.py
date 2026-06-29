"""
institutional_panel.py — Generates institutional actor personas and runs a
structured validation pass on specialist risks from their perspective.

Institutional actors (landlords, provinces, employers, etc.) respond to policy
risks differently from citizens. This module gives those decisions a confirmation
signal instead of relying on specialist prose alone.
"""

import asyncio
import json

# ── Domain → institutional persona definitions ────────────────────────────────

_DOMAIN_PERSONAS: dict[str, list[dict]] = {
    "housing": [
        {
            "agent_id": "inst_landlord_midsize",
            "institution_type": "landlord",
            "label": "Mid-size landlord (Toronto, 120-unit building)",
            "city": "Toronto",
            "sector": "real_estate",
            "decision_context": "Owns 3 rental buildings totalling ~120 units. Operates on 4% net margin. Currently financing 2 of 3 buildings with variable-rate mortgages.",
            "primary_lever": "compliance_or_passthrough",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_landlord_small",
            "institution_type": "landlord",
            "label": "Small landlord (2-unit duplex, Montreal)",
            "city": "Montreal",
            "sector": "real_estate",
            "decision_context": "Owner-occupies one unit, rents the other. The rental income covers ~60% of the mortgage. Retirement savings are tied up in the property.",
            "primary_lever": "comply_or_sell",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_developer_condo",
            "institution_type": "developer",
            "label": "Condo developer (mid-size, GTA)",
            "city": "Toronto",
            "sector": "real_estate",
            "decision_context": "Develops 150–400-unit condo towers. Project timelines are 5–8 years. Pre-sale commitments lock in revenue 3 years before occupancy; cost changes mid-project are absorbed as margin loss.",
            "primary_lever": "proceed_delay_cancel",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_municipal_housing",
            "institution_type": "municipality",
            "label": "Municipal housing authority (City of Vancouver)",
            "city": "Vancouver",
            "sector": "public_administration",
            "decision_context": "Administers 8,000 social housing units. Budget is jointly funded by federal, provincial, and municipal governments. Waitlist currently has 14,000 applicants.",
            "primary_lever": "implement_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "healthcare": [
        {
            "agent_id": "inst_provincial_health",
            "institution_type": "province",
            "label": "Provincial health authority (Ontario)",
            "city": "Toronto",
            "sector": "public_health",
            "decision_context": "Manages hospital funding, physician billing, and drug coverage for 14M residents. Budget pressures from aging population; currently running a 3% structural deficit.",
            "primary_lever": "opt_in_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_private_insurer",
            "institution_type": "insurer",
            "label": "Private health insurer (national group plan provider)",
            "city": "Toronto",
            "sector": "insurance",
            "decision_context": "Provides supplemental coverage to 4M Canadians through employer group plans. Drug coverage represents 40% of claims. A public pharmacare expansion would displace a significant portion of the insured book.",
            "primary_lever": "adapt_or_exit",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_hospital_operator",
            "institution_type": "hospital_operator",
            "label": "Regional hospital operator (rural Ontario)",
            "city": "Sudbury",
            "sector": "healthcare",
            "decision_context": "Operates 2 community hospitals in Northern Ontario with chronic nursing shortages. 35% of physicians are within 5 years of retirement. Dependent on federal rural health supplements.",
            "primary_lever": "comply_absorb_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "labour": [
        {
            "agent_id": "inst_employer_midsize",
            "institution_type": "employer",
            "label": "Mid-size employer (manufacturing, 150 employees, Ontario)",
            "city": "Hamilton",
            "sector": "manufacturing",
            "decision_context": "Manufactures auto parts. Labour costs are 38% of operating costs. Currently at minimum wage floor; a $3/hr increase would reduce margins from 6% to ~2%.",
            "primary_lever": "absorb_automate_or_reduce_headcount",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_employer_large",
            "institution_type": "employer",
            "label": "Large employer (retail chain, 3,000 employees, national)",
            "city": "Toronto",
            "sector": "retail",
            "decision_context": "National grocery chain. Unionized workforce in Quebec; non-unionized elsewhere. Labour is the single largest operating cost. Has accelerated self-checkout rollout over last 3 years.",
            "primary_lever": "automate_or_lobbying_or_comply",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_gig_platform",
            "institution_type": "gig_platform",
            "label": "Gig platform operator (rideshare/delivery, national)",
            "city": "Toronto",
            "sector": "platform_economy",
            "decision_context": "Operates nationally with ~80,000 active gig workers. Platform model is premised on workers being classified as independent contractors. Reclassification would increase labour costs by an estimated 30–40%.",
            "primary_lever": "lobby_or_restructure_or_exit_market",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "fiscal": [
        {
            "agent_id": "inst_corporate_midsize",
            "institution_type": "corporate_taxpayer",
            "label": "Mid-size corporation (professional services, $80M revenue)",
            "city": "Calgary",
            "sector": "professional_services",
            "decision_context": "Private corporation. 60% of profit retained in the corporation; owners draw income through dividends. Sensitive to passive income rules and small business deduction thresholds.",
            "primary_lever": "restructure_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_hnwi",
            "institution_type": "high_net_worth_individual",
            "label": "High-net-worth individual (investment portfolio, $5M+)",
            "city": "Vancouver",
            "sector": "investment",
            "decision_context": "Primary income from capital gains and eligible dividends. Holds significant real estate in BC. Capital gains inclusion rate changes and principal residence exemptions are the primary policy levers affecting after-tax wealth.",
            "primary_lever": "restructure_or_relocate",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_provincial_finance",
            "institution_type": "province",
            "label": "Provincial finance ministry (Quebec)",
            "city": "Quebec City",
            "sector": "public_administration",
            "decision_context": "Manages a $150B+ budget. Transfers from the federal government represent 22% of provincial revenues. Changes to federal fiscal transfers, equalization, or shared-cost programs have direct budget implications.",
            "primary_lever": "opt_in_negotiate_or_resist",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "climate": [
        {
            "agent_id": "inst_commercial_building_owner",
            "institution_type": "building_owner",
            "label": "Commercial building owner (office tower, Calgary)",
            "city": "Calgary",
            "sector": "commercial_real_estate",
            "decision_context": "Owns a 25-year-old downtown office tower. Retrofit to meet new energy standards estimated at $8M. Building currently 60% occupied post-pandemic. Lease structure means retrofit costs cannot easily be passed to tenants.",
            "primary_lever": "retrofit_sell_or_demolish",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_fossil_employer",
            "institution_type": "fossil_fuel_employer",
            "label": "Fossil fuel employer (oil sands operations, Alberta)",
            "city": "Fort McMurray",
            "sector": "energy_extraction",
            "decision_context": "Employs 2,200 workers directly; 6,000 indirectly through contractors. Break-even at ~$50 WTI. Carbon levy increases raise operating costs by an estimated $3–5/barrel.",
            "primary_lever": "lobby_automate_or_wind_down",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_utility",
            "institution_type": "utility",
            "label": "Provincial utility (grid operator, Ontario)",
            "city": "Toronto",
            "sector": "energy",
            "decision_context": "Operates provincial transmission and distribution grid. Electrification mandates (EVs, heat pumps) require ~$40B in grid upgrades by 2035. Rate increases require provincial regulator approval.",
            "primary_lever": "invest_defer_or_lobby_for_rate_relief",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "immigration": [
        {
            "agent_id": "inst_settlement_agency",
            "institution_type": "settlement_agency",
            "label": "Settlement agency (national, 40 offices)",
            "city": "Toronto",
            "sector": "social_services",
            "decision_context": "Provides language training, employment bridging, and housing navigation to ~60,000 newcomers/year. Funded through federal immigration settlement grants; a 10% grant cut would require service rationing.",
            "primary_lever": "scale_up_or_triage",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_credential_body",
            "institution_type": "credential_recognition_body",
            "label": "Professional credential body (engineering, national)",
            "city": "Ottawa",
            "sector": "professional_regulation",
            "decision_context": "Regulates engineering credentials across 12 provincial/territorial bodies. Foreign credential recognition is governed by provincial legislation. Federal pressure to accelerate recognition conflicts with liability concerns.",
            "primary_lever": "accelerate_or_maintain_standards",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_provincial_labour_min",
            "institution_type": "province",
            "label": "Provincial labour ministry (British Columbia)",
            "city": "Victoria",
            "sector": "public_administration",
            "decision_context": "Manages the provincial nominee program and enforces labour standards. BC receives ~18% of all economic immigrants. Increased immigration without commensurate housing creates political pressure on the provincial government.",
            "primary_lever": "absorb_invest_or_lobby_for_federal_support",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "education": [
        {
            "agent_id": "inst_school_board",
            "institution_type": "school_board",
            "label": "Large urban school board (Toronto District)",
            "city": "Toronto",
            "sector": "k12_education",
            "decision_context": "Operates 580 schools; serves 240,000 students. Collective agreements cover teachers, EA, and support staff. Policy changes to curriculum, special education, or funding formulas have direct operational implications.",
            "primary_lever": "implement_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_university",
            "institution_type": "post_secondary",
            "label": "Mid-size university (10,000 students, Ontario)",
            "city": "Kingston",
            "sector": "post_secondary_education",
            "decision_context": "Domestic tuition is frozen by provincial policy. International students represent 28% of revenue. Any international enrollment cap or tuition regulation directly threatens financial stability.",
            "primary_lever": "restructure_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_employer_credential_user",
            "institution_type": "employer",
            "label": "Tech employer (credential-dependent hiring, Vancouver)",
            "city": "Vancouver",
            "sector": "technology",
            "decision_context": "Hires 300+ software engineers/year. Uses degree credentials as a hiring filter. Changes to post-secondary funding, curriculum, or credential recognition affect the talent pipeline and time-to-hire.",
            "primary_lever": "adapt_or_lobby_standards",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "ai": [
        {
            "agent_id": "inst_tech_employer",
            "institution_type": "employer",
            "label": "AI-intensive tech employer (national, 500 employees)",
            "city": "Toronto",
            "sector": "technology",
            "decision_context": "Builds ML-powered products for financial services clients. Compliance costs for AI governance regulation estimated at $2–4M annually. May relocate AI development teams to US if regulatory burden is disproportionate.",
            "primary_lever": "comply_restructure_or_relocate",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_data_broker",
            "institution_type": "data_broker",
            "label": "Data analytics firm (consumer profiles, national)",
            "city": "Ottawa",
            "sector": "data_services",
            "decision_context": "Aggregates consumer data from retail loyalty programs, public records, and third-party sources. Sells enriched profiles to advertisers and insurers. Stricter data governance or consent requirements threaten the core business model.",
            "primary_lever": "lobby_or_restructure_model",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_federal_procurement",
            "institution_type": "crown_corp",
            "label": "Federal AI procurement agency (Shared Services Canada)",
            "city": "Ottawa",
            "sector": "public_administration",
            "decision_context": "Manages federal government IT and AI procurement. AI governance requirements add compliance layers to existing procurement timelines, which already average 18–24 months for major contracts.",
            "primary_lever": "implement_or_delay",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "transit": [
        {
            "agent_id": "inst_transit_authority",
            "institution_type": "transit_authority",
            "label": "Regional transit authority (Metro Vancouver, TransLink)",
            "city": "Vancouver",
            "sector": "public_transit",
            "decision_context": "Operates bus, SkyTrain, and SeaBus across 21 municipalities. Capital budget requires federal/provincial cost-sharing. Operating deficit funded through property tax levy and fare revenue.",
            "primary_lever": "expand_or_defer",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_municipal_gov",
            "institution_type": "municipality",
            "label": "Mid-size municipality (City of Hamilton)",
            "city": "Hamilton",
            "sector": "public_administration",
            "decision_context": "Manages local transit, roads, and development approvals. Transit-oriented development zoning changes affect local tax base. Federal transit funding is conditional on meeting density targets.",
            "primary_lever": "zone_invest_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
    "other": [
        {
            "agent_id": "inst_generic_actor",
            "institution_type": "generic_institutional",
            "label": "Generic institutional actor (national)",
            "city": "Ottawa",
            "sector": "public_administration",
            "decision_context": "Operates within the federal-provincial policy ecosystem. Primary concern is implementation feasibility, administrative burden, and funding certainty.",
            "primary_lever": "implement_or_lobby",
            "population_weight": 1.0,
            "is_institutional": True,
        },
        {
            "agent_id": "inst_municipal_generic",
            "institution_type": "municipality",
            "label": "Municipal government (mid-size city, Prairie region)",
            "city": "Regina",
            "sector": "public_administration",
            "decision_context": "Population of ~230,000. Dependent on provincial transfers for ~30% of operating revenue. Policy implementation capacity is constrained by staff size and procurement rules.",
            "primary_lever": "implement_or_advocate",
            "population_weight": 1.0,
            "is_institutional": True,
        },
    ],
}


def get_institutional_personas(domain: str, policy_classification: dict | None = None) -> list[dict]:
    """Return the hardcoded institutional personas for a given domain (fallback only)."""
    # Map classifier domains to institutional panel domains
    _domain_map = {
        "environment": "climate",
        "corrections": "other",
        "supply": "housing",
        "demand": "housing",
        "tax": "fiscal",
    }
    domain = (domain or "other").lower()
    domain = _domain_map.get(domain, domain)
    personas = _DOMAIN_PERSONAS.get(domain, _DOMAIN_PERSONAS["other"])
    return list(personas)


async def generate_institutional_personas(
    client,
    asst_id: str,
    policy_text: str,
    policy_classification: dict,
    llm_provider: str,
    llm_model: str,
    n: int = 4,
) -> list[dict]:
    """Generate policy-specific institutional actors via LLM. Falls back to hardcoded lookup."""
    prompt = f"""You are designing an institutional actor panel for a Canadian policy risk simulation.

Policy: {policy_text}
Classification: {json.dumps(policy_classification)}

Generate exactly {n} institutional actors (organizations, not individuals) that will be most directly affected by or must respond to this specific policy.

Choose actors that have clear structural decision-making responses — they can comply, resist, lobby, adapt, exit, or pass costs through.
Include a mix of: private sector actors, public/government bodies, and civil society/advocacy organizations.
Do NOT include generic actors. Every actor must have a direct stake in this specific policy's mechanism.

Return only valid JSON with no markdown:
{{
  "actors": [
    {{
      "agent_id": "inst_unique_snake_case_id",
      "institution_type": "employer|province|insurer|municipality|crown_corp|advocacy|regulator|industry_assoc|ngo",
      "label": "Descriptive label (type, location, scale) e.g. 'Large platform operator (national, 80k gig workers)'",
      "city": "Toronto",
      "sector": "sector_name",
      "decision_context": "2-3 sentences: what is this institution, what are their financial/operational stakes, what specifically threatens or benefits them in this policy",
      "primary_lever": "what_they_can_do_e.g._lobby_or_comply_or_exit"
    }}
  ]
}}

city must be one of: Toronto, Ottawa, Hamilton, Montreal, Vancouver, Calgary, Edmonton, Halifax, Winnipeg, Saskatoon, Regina, Victoria, Kelowna, Sudbury, Quebec City"""

    try:
        thread = await client.create_thread(asst_id)
        response = await client.add_message(
            thread_id=thread.thread_id,
            content=prompt,
            llm_provider=llm_provider,
            model_name=llm_model,
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        actors = parsed.get("actors", [])
        if len(actors) >= 2:
            for a in actors:
                a["population_weight"] = 1.0
                a["is_institutional"] = True
            return actors
    except Exception as e:
        pass  # Fall through to hardcoded lookup

    domain = (policy_classification or {}).get("type", "other")
    return get_institutional_personas(domain, policy_classification)


async def _call_institutional_validator(
    client,
    asst_id: str,
    persona: dict,
    policy_text: str,
    risks_json: str,
    llm_provider: str,
    llm_model: str,
) -> dict:
    """Run one institutional persona through a validation pass."""
    prompt = f"""You are simulating an institutional actor's response to a Canadian policy.

Actor: {persona['label']}
Context: {persona['decision_context']}
Primary decision lever: {persona['primary_lever']}

Policy: {policy_text}

IMPORTANT — STANCE LOGIC:
Your overall_stance must reflect this institution's position toward the POLICY ITSELF, not just toward the risk list.
- A regulator or government agency that ADMINISTERS or ENFORCES this policy should be SUPPORTIVE, even if risks exist in implementation
- An industry association whose members face cost increases should be RESISTANT
- An NGO that lobbied for this policy and benefits from it should be SUPPORTIVE
- A company that must comply with new costs but also gains competitive advantage should be NEUTRAL
Do not default to RESISTANT just because the risk list is long — assess whether this institution WANTS this policy to succeed.

The following risks have been identified by policy specialists. For each risk, assess:
1. Does this risk apply to your institution? (use true/false for applies)
2. If yes: what is your likely institutional response? (comply | resist | exit | pass_through | delay | lobby | adapt | absorb)
3. Severity of impact on your institution (1=minor, 2=significant, 3=existential)
4. One sentence of reasoning.

Risks to assess:
{risks_json}

Return only valid JSON with no markdown:
{{
  "validations": [
    {{
      "risk_index": 1,
      "applies": true,
      "institutional_response": "pass_through",
      "severity": 2,
      "reasoning": "one sentence"
    }}
  ],
  "overall_stance": "resistant",
  "key_concern": "one sentence — the single biggest issue for this institution given its specific role"
}}

overall_stance must be one of: resistant | neutral | supportive"""

    try:
        thread = await client.create_thread(asst_id)
        response = await client.add_message(
            thread_id=thread.thread_id,
            content=prompt,
            llm_provider=llm_provider,
            model_name=llm_model,
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        result = dict(persona)
        result["validations"] = parsed.get("validations", [])
        result["overall_stance"] = parsed.get("overall_stance", "neutral")
        result["key_concern"] = parsed.get("key_concern", "")
        return result
    except Exception as e:
        result = dict(persona)
        result["validations"] = []
        result["overall_stance"] = "neutral"
        result["key_concern"] = f"[error: {e}]"
        return result


async def run_institutional_validation(
    client,
    asst_id: str,
    policy_text: str,
    institutional_personas: list[dict],
    specialist_risks: list[dict],
    llm_provider: str = "openai",
    llm_model: str = "gpt-4o-mini",
) -> list[dict]:
    """Run all institutional personas concurrently against the specialist risks."""
    risks_for_prompt = [
        {
            "risk_index": i + 1,
            "risk": r.get("risk", ""),
            "mechanism": r.get("mechanism", ""),
            "severity": r.get("severity", 1),
            "category": r.get("category", ""),
        }
        for i, r in enumerate(specialist_risks)
    ]
    risks_json = json.dumps(risks_for_prompt, indent=2)

    tasks = [
        _call_institutional_validator(
            client, asst_id, persona, policy_text, risks_json, llm_provider, llm_model
        )
        for persona in institutional_personas
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    clean = []
    for persona, result in zip(institutional_personas, results):
        if isinstance(result, Exception):
            stub = dict(persona)
            stub["validations"] = []
            stub["overall_stance"] = "neutral"
            stub["key_concern"] = f"[error: {result}]"
            clean.append(stub)
        else:
            clean.append(result)
    return clean


def build_institutional_summary_block(institutional_results: list[dict]) -> str:
    """Build a compact text block for injection into the coordinator prompt."""
    if not institutional_results:
        return ""

    lines = [f"INSTITUTIONAL ACTOR SIGNALS ({len(institutional_results)} actors):"]
    for actor in institutional_results:
        responses = [v.get("institutional_response", "") for v in actor.get("validations", []) if v.get("applies")]
        most_common = max(set(responses), key=responses.count) if responses else "n/a"
        lines.append(
            f"  [{actor['label']}] "
            f"stance={actor.get('overall_stance', 'neutral')} | "
            f"key_concern={actor.get('key_concern', '')} | "
            f"response_pattern={most_common}"
        )
    return "\n".join(lines)
