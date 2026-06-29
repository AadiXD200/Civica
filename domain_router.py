"""
domain_router.py — Classifies policy domain and generates a specialist manifest
tailored to that domain for each simulation run.
"""

import json

VALID_DOMAINS = frozenset([
    "housing", "transit", "healthcare", "climate", "immigration",
    "labour", "fiscal", "education", "ai", "other",
])

VALID_CATEGORIES = frozenset([
    "affordability", "geographic", "timeline", "displacement",
    "equity", "fiscal", "infrastructure", "employment", "none",
])

# Policy type → domain mapping (fast path before LLM call)
_TYPE_TO_DOMAIN = {
    "supply": "housing",
    "demand": "housing",
    "tax": "fiscal",
    "healthcare": "healthcare",
    "transit": "transit",
    "labour": "labour",
    "immigration": "immigration",
    "environment": "climate",
    "education": "education",
    "ai": "ai",
    "other": "other",
}

# Hardcoded domain → base specialist configs (non-devil-advocate, non-equity roles)
# These are used as context hints in the LLM prompt, not returned directly.
_DOMAIN_SPECIALIST_HINTS = {
    "housing": "Labor Economist, Urban Planner, Fiscal Policy Analyst, Housing Market Economist, Regional Development Analyst, Construction Industry Analyst, Demographic Economist",
    "transit": "Transport Economist, Urban Mobility Planner, Fiscal Policy Analyst, Regional Accessibility Analyst, Infrastructure Engineer, Demographic Economist, Environmental Impact Analyst",
    "healthcare": "Health Economist, Public Health Epidemiologist, Fiscal Policy Analyst, Rural Health Access Analyst, Health Workforce Analyst, Mental Health Policy Analyst, Pharmaceutical Policy Analyst",
    "climate": "Environmental Economist, Energy Transition Analyst, Fiscal Policy Analyst, Regional Climate Impact Analyst, Green Jobs Economist, Agricultural Impact Analyst, Carbon Market Specialist",
    "immigration": "Immigration Economist, Labour Market Integration Analyst, Fiscal Policy Analyst, Regional Settlement Analyst, Education & Skills Recognition Analyst, Housing Demand Analyst, Social Services Analyst",
    "labour": "Labor Economist, Industrial Relations Analyst, Fiscal Policy Analyst, Regional Employment Analyst, Skills & Training Policy Analyst, Automation & Technology Analyst, Wage & Benefits Analyst",
    "fiscal": "Fiscal Policy Analyst, Tax Policy Economist, Debt & Deficit Analyst, Regional Fiscal Equity Analyst, Public Services Impact Analyst, Macroeconomic Analyst, Intergenerational Equity Analyst",
    "education": "Education Economist, Curriculum & Pedagogy Analyst, Fiscal Policy Analyst, Regional Education Access Analyst, Labour Market Outcomes Analyst, Early Childhood Development Specialist, Post-Secondary Policy Analyst",
    "ai": "AI Policy Economist, Technology & Labour Analyst, Fiscal Policy Analyst, Digital Equity Analyst, Data Governance Specialist, Algorithmic Accountability Analyst, Innovation & Productivity Analyst",
    "other": "Policy Generalist, Fiscal Policy Analyst, Regional Impact Analyst, Stakeholder Engagement Analyst, Implementation & Governance Analyst, Risk & Compliance Analyst, Behavioural Economics Analyst",
}

_EQUITY_FOCUS_BY_DOMAIN: dict[str, str] = {
    "housing":     "Distributional impacts: who benefits vs who bears housing costs, gentrification, displacement of vulnerable communities, access barriers, income inequality effects, Indigenous housing impacts",
    "fiscal":      "Distributional impacts of fiscal policy: who bears the tax burden vs who receives transfers, regressive vs progressive effects, income inequality outcomes, impacts on low-income households and Indigenous communities",
    "labour":      "Distributional impacts on workers: who gains vs loses from labour market changes, gig worker protections, union effects, wage inequality, impacts on racialized workers and Indigenous employment",
    "transit":     "Distributional impacts on mobility: who can access transit vs who is car-dependent, fare equity, impacts on low-income commuters, rural transit deserts, Indigenous community connectivity",
    "healthcare":  "Distributional impacts on health access: who gains vs loses drug/care coverage, rural vs urban access gaps, impacts on racialized communities, Indigenous health equity, chronic illness burden by income",
    "climate":     "Distributional impacts of climate policy: who bears energy transition costs vs who benefits, fossil-fuel-dependent workers, low-income household carbon cost burden, Indigenous land and resource impacts",
    "immigration": "Distributional impacts on newcomers: who gains vs loses from immigration changes, refugee vs economic immigrant treatment, language and credential barriers, settlement service access, racialized immigration patterns",
    "education":   "Distributional impacts on learners: who gains vs loses access to education, income-based barriers, Indigenous education gaps, rural school access, disability accommodations, outcomes by socioeconomic group",
    "ai":          "Distributional impacts of AI policy: who bears algorithmic bias risks, digital divide by income and age, racialized surveillance impacts, gig worker algorithmic control, Indigenous data sovereignty",
    "other":       "Distributional impacts: who benefits vs who bears costs, effects on marginalized and vulnerable communities, access barriers, income inequality effects, Indigenous community impacts, intersectional analysis",
}

_CRITIC_FOCUS_BY_DOMAIN: dict[str, str] = {
    "housing":     "Challenge specialist findings on housing policy: question assumed supply elasticity, gentrification claims, and whether displacement risks are overstated or understated",
    "fiscal":      "Challenge specialist findings on fiscal/income policy: question inflationary assumptions, labour supply elasticity, and whether fiscal cost estimates account for multiplier effects",
    "labour":      "Challenge specialist findings on labour policy: question wage pass-through assumptions, union density effects, and whether automation displacement timelines are realistic",
    "transit":     "Challenge specialist findings on transit policy: question ridership projections, cost overrun assumptions, and whether induced demand effects are accounted for",
    "healthcare":  "Challenge specialist findings on healthcare policy: question whether the policy's stated mechanism actually delivers the claimed benefit (e.g. interoperability does not equal improved outcomes), provincial implementation capacity, equity of access across income groups, and whether transition costs or friction are understated. Only cite drug cost savings if the policy explicitly covers pharmaceuticals — do NOT raise drug cost issues for healthcare IT, scope-of-practice, or administrative reform policies.",
    "climate":     "Challenge specialist findings on climate policy: question technology readiness assumptions, job transition timelines, and whether carbon leakage effects are accounted for",
    "immigration": "Challenge specialist findings on immigration policy: question labour market integration timelines, fiscal cost assumptions, and whether social cohesion concerns are evidence-based",
    "education":   "Challenge specialist findings on education policy: question credential value assumptions, labour market absorption rates, and whether access improvements reach the most disadvantaged",
    "ai":          "Challenge specialist findings on AI policy: question regulatory compliance burden estimates, innovation chilling effect assumptions, and whether bias audit mechanisms are technically feasible",
    "other":       "Find the strongest case against the other specialists' expected findings: challenge optimistic assumptions, identify second-order harms, surface implementation risks and unintended consequences",
}


def _make_equity_specialist(domain: str) -> dict:
    focus = _EQUITY_FOCUS_BY_DOMAIN.get(domain, _EQUITY_FOCUS_BY_DOMAIN["other"])
    return {
        "id": "social_equity_researcher",
        "title": "Social Equity Researcher",
        "focus": focus,
        "categories": ["equity", "displacement"],
    }


# Domains where federal-provincial jurisdiction is typically material
_JURISDICTION_CRITICAL_DOMAINS = frozenset([
    "housing", "healthcare", "transit", "education", "labour", "immigration",
])

# Keywords in policy text that suggest provincial cooperation is required
_JURISDICTION_TRIGGERS = [
    "provincial", "provincial government", "provincial authority", "health authority",
    "federal-provincial", "opt-out", "opt out", "section 96", "section 92", "section 91",
    "canada health act", "hospital", "school", "school board", "municipal",
    "crown land", "zoning", "planning act", "natural resources",
]

_JURISDICTION_ADDENDUM = (
    "\n\nJURISDICTION FEASIBILITY (mandatory sub-question): This policy appears to require "
    "provincial cooperation or touches an area of provincial jurisdiction. In addition to your "
    "main critique, explicitly assess: (1) Can the federal government implement this without "
    "provincial consent, or does it require a federal-provincial agreement? (2) What is the "
    "realistic risk that one or more provinces opt out, refuse, or impose conditions that "
    "materially change the policy's reach? (3) If a major province (e.g. Ontario or Quebec) "
    "refuses, what fraction of the target population is excluded? Be specific — this is a "
    "distinct risk axis from financial risk."
)


def _make_critic(domain: str, policy_text: str = "") -> dict:
    focus = _CRITIC_FOCUS_BY_DOMAIN.get(domain, _CRITIC_FOCUS_BY_DOMAIN["other"])
    # Inject jurisdiction feasibility sub-question when domain and policy text warrant it
    if domain in _JURISDICTION_CRITICAL_DOMAINS:
        text_lower = policy_text.lower()
        if any(trigger in text_lower for trigger in _JURISDICTION_TRIGGERS):
            focus = focus + _JURISDICTION_ADDENDUM
    return {
        "id": "policy_critic",
        "title": "Policy Critic",
        "focus": focus,
        "categories": ["none"],
    }


async def route_domain(policy_text: str, policy_classification: dict) -> str:
    """
    Returns the policy domain string from the fixed taxonomy.
    Uses the classification type as a fast path; returns 'other' on failure.
    """
    policy_type = policy_classification.get("type", "other")
    domain = _TYPE_TO_DOMAIN.get(policy_type)
    if domain and domain in VALID_DOMAINS:
        return domain

    # Fallback: keyword scan of policy text
    text_lower = policy_text.lower()
    keyword_map = [
        (["housing", "rent", "mortgage", "zoning", "tenant", "landlord"], "housing"),
        (["transit", "bus", "train", "subway", "transport", "commut"], "transit"),
        (["health", "hospital", "clinic", "medical", "pharma", "care"], "healthcare"),
        (["climate", "carbon", "emission", "green", "renewable", "energy"], "climate"),
        (["immigr", "refugee", "newcomer", "asylum", "visa"], "immigration"),
        (["labour", "labor", "worker", "wage", "employ", "union", "strike"], "labour"),
        (["fiscal", "budget", "deficit", "debt", "tax", "revenue", "spend"], "fiscal"),
        (["education", "school", "university", "college", "tuition", "student"], "education"),
        (["artificial intelligence", "ai ", "algorithm", "automation", "digital", "data governance"], "ai"),
    ]
    for keywords, candidate_domain in keyword_map:
        if any(kw in text_lower for kw in keywords):
            return candidate_domain

    return "other"


async def generate_specialist_manifest(
    client,
    asst_id,
    policy_text: str,
    policy_classification: dict,
    domain: str,
) -> list[dict]:
    """
    Returns a specialist list (7-8 dicts) for this run, tailored to the domain.
    Always includes one Social Equity Researcher and one Policy Critic (devil's advocate).
    Uses a fast LLM call to generate the remaining 5-6 domain-specific roles.
    Falls back to a minimal hardcoded set on any error.
    """
    hints = _DOMAIN_SPECIALIST_HINTS.get(domain, _DOMAIN_SPECIALIST_HINTS["other"])
    valid_cats = ", ".join(sorted(VALID_CATEGORIES))

    thread = await client.create_thread(asst_id)
    prompt = f"""You are designing a specialist panel for a Canadian government policy simulation.

Policy domain: {domain}
Policy summary: {policy_text[:600]}
Policy classification: {json.dumps(policy_classification)}

Generate exactly 6 specialist roles (not including a devil's advocate or equity researcher — those are added separately).

Suggested roles for this domain (adapt as needed): {hints}

Return a JSON array of exactly 6 objects, each with this shape:
{{
  "id": "snake_case_identifier",
  "title": "Human-Readable Title",
  "focus": "One sentence describing what this specialist analyzes for THIS specific policy",
  "categories": ["cat1", "cat2"]
}}

Rules:
- "id" must be unique snake_case, no spaces
- "focus" must be specific to the policy domain, not generic boilerplate
- "categories" must only contain values from: {valid_cats}
- Each specialist must cover a DISTINCT focus area — no overlapping analysis scope
- No specialist should duplicate the Social Equity Researcher (equity/displacement lens) or a devil's advocate role
- Return ONLY the JSON array, no other text"""

    try:
        response = await client.add_message(
            thread_id=thread.thread_id,
            content=prompt,
            llm_provider="openai",
            model_name="gpt-4o-mini",
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        generated = json.loads(raw)

        if not isinstance(generated, list):
            raise ValueError("LLM did not return a list")

        # Validate and sanitise each specialist
        seen_ids = set()
        seen_focuses = []
        clean = []
        for spec in generated:
            if not isinstance(spec, dict):
                continue
            sid = str(spec.get("id", "")).strip().replace(" ", "_").lower()
            if not sid or sid in seen_ids:
                continue
            # Deduplicate by focus similarity (simple word-overlap check)
            focus = str(spec.get("focus", "")).strip()
            if not focus:
                continue
            focus_words = set(focus.lower().split())
            too_similar = False
            for prev_focus in seen_focuses:
                prev_words = set(prev_focus.lower().split())
                overlap = len(focus_words & prev_words) / max(len(focus_words | prev_words), 1)
                if overlap > 0.6:
                    too_similar = True
                    break
            if too_similar:
                continue

            cats = [c for c in spec.get("categories", []) if c in VALID_CATEGORIES]
            if not cats:
                cats = ["none"]

            clean.append({
                "id": sid,
                "title": str(spec.get("title", sid.replace("_", " ").title())).strip(),
                "focus": focus,
                "categories": cats,
            })
            seen_ids.add(sid)
            seen_focuses.append(focus)

            if len(clean) == 6:
                break

        # Pad with generic roles if we got fewer than 4 domain-specific ones
        while len(clean) < 4:
            fallback_id = f"policy_generalist_{len(clean)}"
            clean.append({
                "id": fallback_id,
                "title": "Policy Generalist",
                "focus": f"Broad policy impact analysis for {domain} domain",
                "categories": ["none"],
            })

        # Assemble final manifest: domain specialists + domain-aware equity + domain-aware critic
        manifest = clean + [_make_equity_specialist(domain), _make_critic(domain, policy_text)]
        return manifest

    except Exception as e:
        # Fallback: minimal safe manifest
        return [
            {
                "id": f"{domain}_analyst",
                "title": f"{domain.title()} Policy Analyst",
                "focus": f"Core policy impacts in the {domain} domain",
                "categories": ["none"],
            },
            {
                "id": "fiscal_analyst",
                "title": "Fiscal Policy Analyst",
                "focus": "Government finances, cost-benefit of public investment, budgetary implications",
                "categories": ["fiscal"],
            },
            {
                "id": "regional_impact_analyst",
                "title": "Regional Impact Analyst",
                "focus": "Geographic distribution of impacts: urban vs rural, provincial disparities, remote communities",
                "categories": ["geographic"],
            },
            _make_equity_specialist(domain),
            _make_critic(domain, policy_text),
        ]
