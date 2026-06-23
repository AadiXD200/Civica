# specialist_calibrator.py
"""
Generates policy-specific analytical lenses for domain specialists before Round 1.
One lightweight call per specialist to sharpen their focus given the policy type.
"""

# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

_RELEVANCE_MAPS = {
    "supply": {
        "housing_economist": 1.0,
        "construction_industry_analyst": 0.9,
        "urban_planner": 0.8,
        "demographic_economist": 0.8,
        "labor_economist": 0.7,
        "social_equity_researcher": 0.7,
        "fiscal_analyst": 0.6,
        "regional_development_analyst": 0.6,
    },
    "tax": {
        "fiscal_analyst": 1.0,
        "housing_economist": 0.8,
        "social_equity_researcher": 0.7,
        "labor_economist": 0.6,
        "demographic_economist": 0.5,
    },
    "immigration": {
        "demographic_economist": 1.0,
        "labor_economist": 0.9,
        "regional_development_analyst": 0.8,
        "housing_economist": 0.8,
        "social_equity_researcher": 0.7,
        "urban_planner": 0.6,
        "fiscal_analyst": 0.5,
        "construction_industry_analyst": 0.4,
    },
    "labour": {
        "labor_economist": 1.0,
        "fiscal_analyst": 0.7,
        "social_equity_researcher": 0.7,
        "construction_industry_analyst": 0.6,
        "demographic_economist": 0.6,
    },
    "transit": {
        "urban_planner": 1.0,
        "regional_development_analyst": 0.8,
        "fiscal_analyst": 0.7,
    },
    "healthcare": {
        "social_equity_researcher": 0.8,
        "demographic_economist": 0.8,
        "fiscal_analyst": 0.7,
        "regional_development_analyst": 0.7,
        "labor_economist": 0.5,
    },
}

_DEFAULT_RELEVANCE = 0.6
_DEFAULT_POLICY_TYPES = {"demand", "environment", "education", "other"}

# AI/tech policy relevance — who actually matters for these
_RELEVANCE_MAPS["ai"] = {
    "labor_economist": 1.0,            # employment displacement + wage effects
    "social_equity_researcher": 0.9,   # algorithmic bias, access barriers
    "fiscal_analyst": 0.8,             # compliance costs, enforcement office
    "demographic_economist": 0.7,      # which cohorts are most AI-exposed
    "regional_development_analyst": 0.7,  # urban/rural AI access gap
    "housing_economist": 0.3,          # mostly irrelevant
    "urban_planner": 0.3,
    "construction_industry_analyst": 0.2,
}
_RELEVANCE_MAPS["technology"] = _RELEVANCE_MAPS["ai"]
_RELEVANCE_MAPS["digital"] = _RELEVANCE_MAPS["ai"]


def get_specialist_relevance(specialist: dict, policy_classification: dict) -> float:
    """
    Returns a relevance score (0.0-1.0) for a specialist given the policy type.
    Pure Python, no LLM calls.
    """
    policy_type = policy_classification.get("type", "other")
    specialist_id = specialist["id"]

    if policy_type in _DEFAULT_POLICY_TYPES:
        return _DEFAULT_RELEVANCE

    mapping = _RELEVANCE_MAPS.get(policy_type, {})
    return mapping.get(specialist_id, _DEFAULT_RELEVANCE)


# ---------------------------------------------------------------------------
# Lens construction helpers
# ---------------------------------------------------------------------------

def _geography_framing(geography: str) -> str:
    if geography == "urban":
        return "Focus on dense urban markets where infrastructure pressure and land constraints amplify effects."
    if geography == "rural":
        return "Pay particular attention to rural and remote communities where service access is already constrained."
    if geography == "regional":
        return "Consider regional variation: outcomes in mid-sized cities and resource towns may diverge significantly from major metros."
    if geography == "provincial":
        return "Examine provincial-level variation, since implementation capacity and housing markets differ substantially across provinces."
    # national
    return "This policy operates nationally; note where impacts are likely to be uneven across urban, suburban, and rural contexts."


def _time_framing(time_horizon: str) -> str:
    if time_horizon == "immediate":
        return "The effects are expected to manifest immediately — prioritize near-term shocks over structural transitions."
    if time_horizon == "short_term":
        return "The policy horizon is short-term (1-3 years); focus on transition frictions rather than long-run equilibrium effects."
    if time_horizon == "long_term":
        return "With a long-term horizon, emphasize structural and compounding effects that may not appear in the first few years."
    return ""


def _demographic_framing(primary_affected: str, key_attributes: list) -> str:
    group_label = {
        "renters": "renters",
        "owners": "homeowners",
        "all": "all households",
        "low_income": "low-income households",
        "immigrants": "immigrant and newcomer households",
        "seniors": "seniors and fixed-income households",
        "youth": "young adults and first-time market entrants",
        "indigenous": "Indigenous communities",
        "workers": "workers and labour market participants",
    }.get(primary_affected, primary_affected)

    attrs = ", ".join(key_attributes[:4]) if key_attributes else ""
    base = f"The primary affected group is {group_label}."
    if attrs:
        base += f" Key demographic attributes to track: {attrs}."
    return base


def _specialist_subangle(specialist_id: str, policy_type: str, geography: str, policy_classification: dict | None = None) -> str:
    """Returns the most activated sub-angle for this specialist × policy combination."""
    angles = {
        ("housing_economist", "supply"): "Assess how new supply interacts with existing vacancy rates and price-to-rent ratios across markets.",
        ("housing_economist", "tax"): "Examine how tax changes alter investment incentives, speculative demand, and effective affordability.",
        ("housing_economist", "immigration"): "Model the demand-side pressure that accelerated immigration targets place on absorption capacity.",
        ("housing_economist", "demand"): "Evaluate demand-side stimulus risks: price inflation, bidding wars, and erosion of affordability gains.",
        ("construction_industry_analyst", "supply"): "Identify bottlenecks in labour, materials, and permitting that could delay or dilute supply targets.",
        ("construction_industry_analyst", "labour"): "Assess construction workforce capacity constraints and how labour policy changes affect build rates.",
        ("construction_industry_analyst", "immigration"): "Evaluate whether immigration streams adequately target the skilled trades needed to meet housing targets.",
        ("urban_planner", "supply"): "Analyse infrastructure strain from rapid densification — transit, utilities, schools, and healthcare facility capacity.",
        ("urban_planner", "transit"): "Evaluate transit network capacity, last-mile connectivity, and how service gaps affect housing location decisions.",
        ("urban_planner", "demand"): "Consider how demand pressure accelerates sprawl versus infill, and the service cost implications of each pattern.",
        ("labor_economist", "supply"): "Examine construction-sector employment demand, wage pressure, and skills gaps that constrain delivery timelines.",
        ("labor_economist", "labour"): "Assess direct wage, benefits, and employment-structure effects on household affordability and housing cost inputs.",
        ("labor_economist", "immigration"): "Analyse how immigration-driven labour supply changes affect wages in housing-critical sectors.",
        ("fiscal_analyst", "supply"): "Quantify the municipal infrastructure investment required to support new supply and the revenue implications of densification.",
        ("fiscal_analyst", "tax"): "Model revenue effects, tax expenditure efficiency, and distributional implications of the tax instrument.",
        ("fiscal_analyst", "transit"): "Evaluate capital cost, operating cost, and financing structure of transit investments relative to expected ridership.",
        ("fiscal_analyst", "healthcare"): "Project health system demand shifts, facility investment requirements, and long-run fiscal sustainability.",
        ("social_equity_researcher", "supply"): "Investigate whether new supply reaches households in the bottom two income quintiles or primarily serves market-rate demand.",
        ("social_equity_researcher", "tax"): "Examine whether the tax measure has progressive, regressive, or neutral distributional effects across income and tenure groups.",
        ("social_equity_researcher", "immigration"): "Assess barriers faced by newcomers: documentation requirements, credit history gaps, and language access in housing markets.",
        ("social_equity_researcher", "healthcare"): "Focus on access equity: which communities gain or lose service proximity, and how this interacts with housing stability.",
        ("regional_development_analyst", "supply"): "Map where new supply is concentrated and identify regions chronically under-served by current pipeline projections.",
        ("regional_development_analyst", "immigration"): "Evaluate settlement patterns and whether immigration flows are matched to regional labour and housing capacity.",
        ("regional_development_analyst", "transit"): "Assess regional connectivity gaps and whether transit investment reduces or reinforces spatial inequality.",
        ("demographic_economist", "supply"): "Project household formation rates by cohort and assess whether supply pipeline aligns with demographic demand curves.",
        ("demographic_economist", "immigration"): "Model the long-run demographic dividend and near-term demand shock from immigration targets.",
        ("demographic_economist", "healthcare"): "Examine how population aging shifts housing-adjacent service demand, particularly for assisted and accessible units.",

    }

    # ── AI / technology policy angles — dynamic by AI policy subtype ─────────
    # Determined from key_attributes in policy_classification
    key_attrs = set(a.lower() for a in (policy_classification.get("key_attributes") or []))
    primary_affected = policy_classification.get("primary_affected", "all").lower()

    # Detect AI policy subtype from key_attributes
    _is_gov_deployment = any(x in key_attrs for x in ["government", "benefits", "public service", "eligibility", "automated", "deployment", "social services"])
    _is_hiring_hr = any(x in key_attrs for x in ["hiring", "hr", "performance", "recruitment"]) or ("employment" in key_attrs and "technology" in key_attrs)
    _is_compute_infra = (
        any(x in key_attrs for x in ["compute", "infrastructure", "investment", "sovereignty", "research", "academic_industry_collaboration", "canadian_researchers", "startups"])
        or ("long_term" == (policy_classification or {}).get("time_horizon") and "academic" in str(key_attrs))
    )
    _is_content = any(x in key_attrs for x in ["content", "media", "labelling", "disclosure", "generated", "content_creators", "digital_platform_users", "general_public"])
    _is_liability = any(x in key_attrs for x in ["liability", "accountability", "damages", "legal"])
    # Default: corporate disclosure/regulation
    _is_corporate_disclosure = not any([_is_gov_deployment, _is_hiring_hr, _is_compute_infra, _is_content, _is_liability])

    def _ai_angle(specialist_id: str) -> str:
        if _is_gov_deployment:
            angles = {
                "labor_economist": "This policy automates government benefit screening. Assess: does automation create new demand for human reviewers (net employment gain) or eliminate frontline service jobs? Does mandatory human review for denials create processing bottlenecks that delay income support to vulnerable Canadians? Flag the risk of appeals backlogs.",
                "social_equity_researcher": "Government AI in benefit screening carries documented bias risks: algorithmic systems trained on historical data perpetuate systemic discrimination against Indigenous peoples, visible minorities, and persons with disabilities. Assess whether the right to request human review is meaningful (is it accessible, free, timely?) or a nominal safeguard that most vulnerable claimants won't exercise.",
                "fiscal_analyst": "Model the government's cost of implementing AI screening: system procurement, human review capacity, appeals handling, and liability if wrongful denials are challenged. Compare to current processing costs. Assess whether efficiency gains are realised or offset by appeals volume.",
                "regional_development_analyst": "Rural and remote communities face digital access barriers that may make AI-mediated benefit applications structurally harder to complete. Assess whether the system design assumes broadband access and digital literacy that are unevenly distributed.",
                "demographic_economist": "Older applicants, recent immigrants, and persons with disabilities are disproportionately represented among benefit claimants and disproportionately disadvantaged by automated systems that assume digital fluency. Quantify which cohorts are most likely to receive incorrect automated denials.",
                "housing_economist": "Delayed or wrongful denial of EI or disability benefits directly affects rent payment capacity. In high-cost cities, even a 2-week processing delay can trigger eviction proceedings for households already in core housing need.",
                "urban_planner": "Centralised AI processing replaces distributed Service Canada offices. Assess whether office closures leave service gaps in mid-sized cities and rural towns where in-person assistance was the primary access point.",
                "construction_industry_analyst": "Limited direct relevance. Only flag a risk if there is a direct causal line from this policy's mechanism to your domain. If none exists, return empty risks.",
            }
        elif _is_hiring_hr:
            angles = {
                "labor_economist": "AI in hiring creates measurable chilling effects: firms using AI screening tools have documented lower callback rates for non-European names, older workers, and those with employment gaps. Assess whether liability for discriminatory outcomes changes firm behaviour (more careful AI use) or creates compliance theatre.",
                "social_equity_researcher": "Hiring AI bias is the best-documented AI harm in Canada: resume screening tools systematically disadvantage women in technical roles, Indigenous applicants, and visible minorities. Liability framework shifts incentives but may drive firms to use less transparent third-party tools to diffuse liability.",
                "fiscal_analyst": "Model litigation costs and compliance audit costs for firms. Assess whether liability exposure is large enough to deter use of discriminatory AI tools or small enough to be treated as a cost of doing business.",
                "regional_development_analyst": "Rural employers and small-city businesses are less likely to use AI hiring tools — liability framework creates compliance burden for the small share that do while large urban firms have legal teams to absorb costs.",
                "demographic_economist": "Older workers and recent immigrants face the highest documented AI hiring bias. Liability framework should theoretically reduce this — assess whether it does in practice or whether firms simply document AI decisions better without changing outcomes.",
                "housing_economist": "Indirect: if AI hiring liability reduces discriminatory AI screening, employment rates for vulnerable groups may improve, with downstream effects on housing affordability. This is 3+ causal steps — only flag if you can name the specific chain.",
                "urban_planner": "Limited direct relevance. Only flag if direct causal link exists.",
                "construction_industry_analyst": "Construction sector has low AI hiring penetration. Only flag if direct causal link exists.",
            }
        elif _is_compute_infra:
            angles = {
                "labor_economist": "National AI compute investment creates high-skill research and engineering jobs concentrated in Toronto, Montreal, and Edmonton. Assess whether this widens the skills gap between AI-hub cities and the rest of Canada, and whether the investment accelerates AI adoption in ways that displace mid-skill workers.",
                "social_equity_researcher": "Sovereign AI infrastructure concentrates economic benefits in already-advantaged institutions. Assess whether small universities, community colleges, and Indigenous-serving institutions get access to compute resources, or whether the investment entrenches existing inequalities.",
                "fiscal_analyst": "Model the fiscal case for $2B investment: what does Canada get in return (domestic AI capacity, reduced dependence on US/China hyperscalers, research output)? Assess the risk of investing in infrastructure that becomes obsolete within a hardware generation cycle.",
                "regional_development_analyst": "AI compute infrastructure requires significant power and cooling. Assess where data centres will be sited and whether this creates regional economic benefits (jobs, tax base) or environmental costs concentrated in specific provinces.",
                "demographic_economist": "Young Canadians with STEM degrees benefit most from domestic AI compute investment. Assess whether this creates a two-tier labour market between AI-adjacent and non-AI workers.",
                "housing_economist": "Data centre clusters drive commercial real estate demand and can affect surrounding residential markets. In cities like Calgary or Brantford, large compute installations have measurable effects on local housing demand.",
                "urban_planner": "Data centre power requirements and cooling loads affect municipal infrastructure planning. Large-scale compute facilities require grid upgrades and water cooling that have real urban planning implications.",
                "construction_industry_analyst": "Data centre construction is a specialised segment. Assess whether Canadian construction capacity exists for the scale of investment, and whether procurement will favour Canadian contractors.",
            }
        elif _is_content:
            angles = {
                "labor_economist": "Mandatory content labelling creates a new compliance role: content moderators and technical staff who implement watermarking. Assess whether the 100,000-user threshold creates a cliff that causes platforms to cap users to avoid compliance. Does labelling requirement change the economics of Canadian content creation — do Canadian creators face higher costs than foreign competitors?",
                "social_equity_researcher": "AI content labelling affects who can participate in digital media. Indigenous and minority content creators who use AI tools for accessibility (translation, audio description) may face labelling stigma. Assess whether the policy's definition of 'AI-generated' captures tools used for accessibility vs tools used for deception.",
                "fiscal_analyst": "Model compliance costs for mid-tier Canadian platforms (100k–10M users). CRTC enforcement requires new audit capacity. Assess whether the fine structure ($500k/violation) is calibrated to deter large platforms or punish small Canadian ones. The 24-month watermarking deadline may be technically infeasible for some platforms.",
                "regional_development_analyst": "Canadian digital platforms are concentrated in Toronto, Vancouver, and Montreal. Small-city and rural content creators who rely on AI tools for production may face labelling stigma that disadvantages them relative to professional studios. Assess geographic asymmetry in compliance burden.",
                "demographic_economist": "Older Canadians who rely on AI-assisted tools for communication (text-to-speech, translation) may have their content labelled as 'AI-generated', stigmatising accessibility tools. Assess which demographic cohorts are most affected by the labelling regime's definitional boundaries.",
                "housing_economist": "Very limited direct relevance. Only flag if compliance costs affect digital-sector employment in tech-hub cities with measurable housing demand effects.",
                "urban_planner": "Limited direct relevance. Only flag if there is a direct mechanism from this policy to urban planning outcomes.",
                "construction_industry_analyst": "No relevance. Return empty risks.",
            }
        elif _is_liability:
            angles = {
                "labor_economist": "Liability for AI outcomes changes incentive structure: firms may over-document or de-adopt AI tools to reduce liability exposure. Assess whether liability shifts AI development jobs from Canada to jurisdictions with lower liability regimes.",
                "social_equity_researcher": "Liability frameworks can be protective (holding AI harms accountable) or regressive (only large firms can afford compliance, driving out smaller players who serve niche communities). Assess who actually benefits from liability protection and who is excluded.",
                "fiscal_analyst": "Model litigation costs, insurance markets, and regulatory enforcement costs. Assess whether liability regime creates sustainable deterrence or drives activity to less-regulated jurisdictions.",
                "regional_development_analyst": "AI liability may concentrate AI development in cities with specialised legal infrastructure, widening the gap between AI hubs and the rest of Canada.",
                "demographic_economist": "Liability for discriminatory AI outcomes should protect vulnerable cohorts. Assess whether the liability mechanism is accessible to individual claimants or primarily usable by well-resourced organisations.",
                "housing_economist": "Limited relevance. Only flag if liability regime affects AI sector employment with measurable downstream housing effects.",
                "urban_planner": "Limited relevance.",
                "construction_industry_analyst": "No relevance.",
            }
        else:
            # Default: corporate disclosure/regulation
            angles = {
                "labor_economist": "This policy's mechanism is mandatory AI disclosure and human review requirements. Focus on: does mandatory human review create new labour demand, or does compliance burden cause firms to defer AI adoption? Does an employee threshold create a cliff where firms restructure to avoid compliance?",
                "social_equity_researcher": "Investigate who bears compliance costs vs who benefits from AI accountability. A disclosure regime may protect high-adoption sector workers (tech, finance) while providing little protection in low-adoption sectors (agriculture 0.7%, accommodation 0.9%).",
                "fiscal_analyst": "Model compliance cost burden on SMEs (99.8% of Canadian businesses). Benchmark against EU AI Act: €193,000+ per foundation model, €6,000-10,000 per high-risk system. Assess whether costs widen the adoption gap between large firms and SMEs.",
                "regional_development_analyst": "Disclosure policy applies uniformly but AI economic exposure is urban and sector-specific. Assess whether compliance infrastructure exists outside major cities. Flag Indigenous community impact.",
                "demographic_economist": "Assess which cohorts bear unintended costs of compliance requirements. Does mandatory human review slow hiring pipelines in ways that disadvantage non-standard applicants?",
                "housing_economist": "Limited direct relevance. Only flag if compliance costs suppress SME hiring with measurable downstream effects on household income in specific cities.",
                "urban_planner": "Flag digital infrastructure access gaps between urban AI hubs and underserved regions only if directly caused by this policy.",
                "construction_industry_analyst": "Very limited relevance. Return empty risks unless there is a direct causal line.",
            }

        return angles.get(specialist_id, "Apply your domain expertise only to risks directly caused by this policy's specific mechanism.")

    # For AI/technology policies, use dynamic subtype-aware angles
    if policy_type in ("ai", "technology", "digital"):
        return _ai_angle(specialist_id)

    key = (specialist_id, policy_type)
    if key in angles:
        return angles[key]

    # Generic fallback by specialist
    generic = {
        "housing_economist": "Evaluate price, vacancy, and affordability dynamics as the primary mechanism.",
        "construction_industry_analyst": "Focus on delivery capacity, supply-chain risk, and regulatory friction.",
        "urban_planner": "Consider land use, density, and infrastructure service delivery implications.",
        "labor_economist": "Examine employment, wage, and skills-gap effects most activated by this policy.",
        "fiscal_analyst": "Analyse the fiscal cost, revenue impact, and efficiency of the policy instrument.",
        "social_equity_researcher": "Identify which groups bear disproportionate costs or are excluded from benefits.",
        "regional_development_analyst": "Map geographic variation in impact and flag regions at risk of being left behind.",
        "demographic_economist": "Track household formation, migration, and cohort-demand patterns most relevant to this policy.",
    }
    return generic.get(specialist_id, "Apply your domain expertise to the most policy-relevant risks.")


def _relevant_cities(geography: str, policy_type: str) -> str:
    urban_centres = "Toronto, Vancouver, Montreal, Calgary, Edmonton, Ottawa, and Hamilton"
    mid_cities = "Kitchener-Waterloo, Halifax, Victoria, London, and Saskatoon"
    rural_regions = "Northern Ontario, Northern BC, PEI, Indigenous Reserves, and Nunavut"

    if geography == "urban":
        return f"Prioritise data from high-growth urban centres: {urban_centres}."
    if geography == "rural":
        return f"Prioritise data from rural and remote regions: {rural_regions}."
    if geography == "regional":
        return f"Prioritise mid-sized and regional markets: {mid_cities}, alongside larger metros for contrast."
    # national / provincial
    return (
        f"Draw on the full national data range: major metros ({urban_centres}), "
        f"mid-sized cities ({mid_cities}), and rural/remote regions ({rural_regions})."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_specialist_lens_prompt(
    specialist: dict,
    policy_classification: dict,
    city_profiles_summary: str,
) -> str:
    """
    Returns a focused 3-5 sentence lens paragraph for the specialist.
    Pure Python — no LLM calls.
    """
    policy_type = policy_classification.get("type", "other")
    geography = policy_classification.get("geography", "national")
    time_horizon = policy_classification.get("time_horizon", "short_term")
    primary_affected = policy_classification.get("primary_affected", "all")
    key_attributes = policy_classification.get("key_attributes", [])
    specialist_id = specialist["id"]

    sentences = []

    # Sentence 1: policy context + specialist sub-angle
    subangle = _specialist_subangle(specialist_id, policy_type, geography, policy_classification)
    _DOMAIN_LABEL = {
        "ai": "AI and technology governance",
        "technology": "technology governance",
        "digital": "digital economy",
        "healthcare": "healthcare",
        "immigration": "immigration",
        "labour": "labour market",
        "transit": "transit and infrastructure",
        "supply": "housing supply",
        "tax": "housing tax",
        "demand": "housing demand",
    }
    domain = _DOMAIN_LABEL.get(policy_type, "government")
    sentences.append(
        f"This is a {policy_type}-type {domain} policy with a {geography} geographic scope "
        f"and a {time_horizon.replace('_', '-')} time horizon. {subangle}"
    )

    # Sentence 2: demographics
    sentences.append(_demographic_framing(primary_affected, key_attributes))

    # Sentence 3: geography framing
    sentences.append(_geography_framing(geography))

    # Sentence 4: time horizon framing
    time_sentence = _time_framing(time_horizon)
    if time_sentence:
        sentences.append(time_sentence)

    # Sentence 5: city data pointer
    sentences.append(_relevant_cities(geography, policy_type))

    return " ".join(sentences)


def calibrate_specialist_prompt(
    base_prompt: str,
    specialist: dict,
    policy_classification: dict,
    city_profiles_summary: str,
) -> str:
    """
    Injects a POLICY-SPECIFIC FOCUS DIRECTIVE block into the specialist system prompt,
    right after the 'Your domain:' line.
    Pure Python — no LLM calls.
    """
    lens = build_specialist_lens_prompt(specialist, policy_classification, city_profiles_summary)

    directive_block = (
        "\n\nPOLICY-SPECIFIC FOCUS DIRECTIVE:\n"
        f"{lens}\n"
    )

    # Try to insert after "Your domain:" line
    domain_marker = "Your domain:"
    if domain_marker in base_prompt:
        # Find end of that line
        idx = base_prompt.index(domain_marker)
        newline_idx = base_prompt.find("\n", idx)
        if newline_idx == -1:
            # domain line is the last line
            return base_prompt + directive_block
        insert_at = newline_idx
        return base_prompt[:insert_at] + directive_block + base_prompt[insert_at:]

    # Fallback: prepend
    return directive_block.lstrip("\n") + "\n\n" + base_prompt
