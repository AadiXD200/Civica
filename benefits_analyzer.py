"""
benefits_analyzer.py

Runs a parallel benefits analysis pass after Round 1 specialists.
Each specialist identifies WHO GAINS from the policy, how much, and why.
Produces structured benefit items that feed into net-impact scoring per cohort.
"""

import json
import asyncio

BENEFIT_CATEGORIES = [
    "affordability",   # direct cost reduction / savings
    "income",          # wage gains, employment, income support
    "access",          # improved access to services, housing, healthcare
    "equity",          # distributional improvement for underserved groups
    "fiscal",          # government revenue / program funding
    "productivity",    # economic efficiency, output gains
    "environment",     # emissions reduction, sustainability
    "protection",      # legal / regulatory protection gained
]

# Which specialist domains are most relevant for identifying benefits
BENEFIT_RELEVANCE = {
    "labor_economist":              ["income", "productivity", "affordability"],
    "urban_planner":                ["access", "affordability", "environment"],
    "fiscal_analyst":               ["fiscal", "affordability", "income"],
    "housing_economist":            ["affordability", "access"],
    "social_equity_researcher":     ["equity", "access", "protection"],
    "regional_development_analyst": ["equity", "access", "income"],
    "construction_industry_analyst":["productivity", "income"],
    "demographic_economist":        ["income", "equity", "access"],
    "policy_critic":                ["equity", "fiscal", "access"],
}

# Benefit keyword → (validator_attribute, attribute_values_or_fn, weight)
# Used to match benefit primary_beneficiaries text against validator profiles
_BENEFIT_KEYWORD_RULES = [
    # keyword          attr              match_values_or_fn                          weight
    ("renter",         "tenure",         {"renter"},                                 2.0),
    ("homeowner",      "tenure",         {"owner"},                                  2.0),
    ("owner",          "tenure",         {"owner"},                                  2.0),
    ("low-income",     "income_bracket", {"very_low", "low"},                        2.0),
    ("low income",     "income_bracket", {"very_low", "low"},                        2.0),
    ("young",          "age_bracket",    {"18-24", "25-34"},                         1.5),
    ("youth",          "age_bracket",    {"18-24", "25-34"},                         1.5),
    ("senior",         "age_bracket",    {"65+"},                                    2.0),
    ("elderly",        "age_bracket",    {"65+"},                                    2.0),
    ("immigrant",      "immigration_status", {"recent_immigrant", "refugee"},        2.0),
    ("newcomer",       "immigration_status", {"recent_immigrant", "refugee"},        2.0),
    ("indigenous",     "_city_contains", ["Reserve"],                                2.0),
    ("rural",          "_city_contains", ["Rural", "Northern", "Remote", "Nunavut"], 2.0),
    ("worker",         "employment_type",{"salaried", "gig", "self_employed"},       1.0),
    ("employed",       "employment_type",{"salaried", "gig", "self_employed"},       1.0),
    ("student",        "employment_type",{"student"},                                2.0),
    ("family",         "family_size",    {"small_family", "large_family"},           1.5),
    ("parent",         "family_size",    {"small_family", "large_family"},           1.5),
    ("transit",        "_city_major_cma",None,                                       1.0),
    ("commuter",       "_city_major_cma",None,                                       1.0),
    # Healthcare / public health domain
    ("patient",        "employment_type",{"retired", "unemployed"},                  1.5),
    ("patient",        "income_bracket", {"very_low", "low"},                        1.0),
    ("healthcare worker", "domain_role", {"healthcare_worker", "public_health_nurse","harm_reduction_worker","addictions_counsellor","rural_healthcare_worker"}, 2.5),
    ("nurse",          "domain_role",    {"public_health_nurse", "healthcare_worker"},2.5),
    ("caregiver",      "domain_role",    {"family_caregiver"},                       2.0),
    ("chronic",        "domain_role",    {"chronic_condition_patient", "disability_benefit_user"}, 2.0),
    ("chronic",        "employment_type",{"retired"},                                1.0),
    ("disability",     "domain_role",    {"disability_benefit_user"},                2.5),
    # Middle-income / universal coverage
    ("middle-income",  "income_bracket", {"medium"},                                  2.0),
    ("middle income",  "income_bracket", {"medium"},                                  2.0),
    ("middle-class",   "income_bracket", {"medium"},                                  2.0),
    ("household",      "income_bracket", {"very_low", "low"},                         0.5),
    ("households",     "income_bracket", {"very_low", "low"},                         0.5),
    ("canadian",       "income_bracket", {"very_low", "low"},                         0.5),
    ("canadians",      "income_bracket", {"very_low", "low"},                         0.5),
    # Medication / drug cost — regressive burden, low-income groups benefit most
    ("medication",     "income_bracket", {"very_low", "low"},                         1.5),
    ("prescription",   "income_bracket", {"very_low", "low"},                         1.5),
    ("drug coverage",  "income_bracket", {"very_low", "low"},                         1.5),
    # Age bracket rules
    ("older",          "age_bracket",    {"35-49", "50-64"},                          1.5),
    ("middle-aged",    "age_bracket",    {"35-49"},                                   1.5),
    # Drug / harm reduction domain
    ("substance user", "domain_role",    {"person_in_recovery","active_substance_user","youth_substance_user","indigenous_substance_user","parent_substance_user","neighbourhood_peer_worker"}, 3.0),
    ("substance",      "domain_role",    {"person_in_recovery","active_substance_user","youth_substance_user","indigenous_substance_user","parent_substance_user"}, 2.5),
    ("harm reduction", "domain_role",    {"harm_reduction_worker","neighbourhood_peer_worker","public_health_nurse"}, 2.5),
    ("overdose",       "domain_role",    {"person_in_recovery","active_substance_user","harm_reduction_worker","public_health_nurse"}, 2.0),
    ("decriminaliz",   "domain_role",    {"person_in_recovery","active_substance_user","prior_possession_charge","racialized_prior_charge","youth_substance_user","indigenous_substance_user"}, 2.5),
    ("possession",     "domain_role",    {"prior_possession_charge","racialized_prior_charge"}, 3.0),
    ("criminali",      "domain_role",    {"prior_possession_charge","racialized_prior_charge","formerly_incarcerated","indigenous_formerly_incarcerated"}, 2.0),
    ("marginali",      "domain_role",    {"indigenous_substance_user","racialized_prior_charge","neighbourhood_peer_worker","person_in_recovery"}, 1.5),
    # Criminal justice domain
    ("formerly incarcerated", "domain_role", {"formerly_incarcerated","indigenous_formerly_incarcerated"}, 3.0),
    ("incarcerat",     "domain_role",    {"formerly_incarcerated","indigenous_formerly_incarcerated","prison_system_administrator"}, 2.0),
    ("racialized",     "domain_role",    {"racialized_stop_and_search","racialized_prior_charge","indigenous_formerly_incarcerated"}, 2.0),
    ("victim",         "domain_role",    {"victim_advocate","victim_services_worker"}, 2.0),
    ("community",      "domain_role",    {"community_corrections_worker","neighbourhood_peer_worker","victim_services_worker"}, 1.0),
    # Labour / employment domain
    ("gig worker",     "domain_role",    {"gig_platform_worker","gig_tax_filer","temp_agency_worker"}, 3.0),
    ("gig",            "domain_role",    {"gig_platform_worker","gig_tax_filer"},    2.0),
    ("precarious",     "domain_role",    {"precarious_worker","temp_agency_worker","migrant_worker"}, 2.5),
    ("minimum wage",   "domain_role",    {"student_part_time_worker","gig_platform_worker","precarious_worker"}, 2.5),
    ("unemployed",     "employment_type",{"unemployed"},                             1.5),
    ("displaced",      "domain_role",    {"displaced_manufacturing","long_term_unemployed"}, 2.5),
    # Taxation / fiscal domain
    ("high-income",    "income_bracket", {"high","very_high"},                       2.0),
    ("high income",    "income_bracket", {"high","very_high"},                       2.0),
    ("investor",       "domain_role",    {"real_estate_investor","capital_gains_holder"}, 2.5),
    ("retiree",        "domain_role",    {"retiree_fixed_income"},                   2.0),
    ("self-employed",  "employment_type",{"self_employed"},                          1.5),
    ("incorporated",   "domain_role",    {"professional_incorporated","business_owner_tax","small_employer"}, 2.0),
    # Education domain
    ("post-secondary", "domain_role",    {"undergraduate_student","international_student","recent_graduate_debt"}, 2.0),
    ("tuition",        "domain_role",    {"undergraduate_student","international_student","student_low_income"}, 2.5),
    ("educator",       "domain_role",    {"k12_teacher","early_childhood_educator","college_instructor"}, 2.5),
    ("childcare",      "domain_role",    {"early_childhood_educator","parent_school_age_children","new_parent_healthcare"}, 2.0),
]

# domain_role → benefit keyword fragments that signal this persona is a primary beneficiary
# Used for the direct primary-affected bonus — bypasses keyword matching entirely
_DOMAIN_ROLE_PRIMARY_MATCH: dict[str, list[str]] = {
    "person_in_recovery":         ["substance", "harm reduction", "decriminaliz", "overdose", "health"],
    "active_substance_user":      ["substance", "harm reduction", "decriminaliz", "overdose", "health"],
    "youth_substance_user":       ["substance", "harm reduction", "decriminaliz", "youth", "health"],
    "indigenous_substance_user":  ["substance", "harm reduction", "indigenous", "equity", "health"],
    "parent_substance_user":      ["substance", "harm reduction", "decriminaliz", "family"],
    "harm_reduction_worker":      ["harm reduction", "health", "workforce", "funding"],
    "public_health_nurse":        ["health", "workforce", "nurse", "overdose"],
    "addictions_counsellor":      ["health", "treatment", "funding", "workforce"],
    "neighbourhood_peer_worker":  ["harm reduction", "community", "substance", "equity"],
    "prior_possession_charge":    ["decriminaliz", "legal", "possession", "criminali", "equity"],
    "racialized_prior_charge":    ["decriminaliz", "equity", "racialized", "criminali"],
    "formerly_incarcerated":      ["reintegration", "record", "equity", "criminali"],
    "indigenous_formerly_incarcerated": ["indigenous", "equity", "criminali", "justice"],
    "gig_platform_worker":        ["gig", "precarious", "minimum wage", "labour", "worker"],
    "temp_agency_worker":         ["precarious", "labour", "worker", "minimum wage"],
    "precarious_worker":          ["precarious", "labour", "worker", "income"],
    "migrant_worker":             ["migrant", "worker", "labour", "equity"],
    "displaced_manufacturing":    ["displaced", "retraining", "worker", "income"],
    "chronic_condition_patient":  ["health", "drug", "coverage", "patient"],
    "disability_benefit_user":    ["disability", "health", "access", "coverage"],
    "elderly_patient":            ["health", "senior", "drug", "coverage"],
    "uninsured_patient":          ["health", "coverage", "drug", "patient"],
    "undergraduate_student":      ["tuition", "student", "education", "bursary"],
    "international_student":      ["tuition", "student", "education"],
    "recent_graduate_debt":       ["student", "repayment", "debt", "education"],
}

_MAJOR_CMAS = {
    "Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton", "Ottawa",
    "Winnipeg", "Quebec City", "Hamilton", "Kitchener", "London", "Halifax",
    "Victoria", "Saskatoon", "Regina", "Windsor", "Oshawa", "Barrie",
}


def _score_benefit_for_validator(benefit: dict, v: dict) -> float:
    """
    Score how much a single benefit item matches a validator's demographic profile.
    Returns a raw weight sum (0 = no match). Uses magnitude as a multiplier.

    For domain persona agents: also checks domain_role directly against keyword
    rules and applies a primary-affected bonus when the role maps to the benefit text.
    """
    beneficiary_text = (benefit.get("primary_beneficiaries", "") or "").lower()
    if not beneficiary_text:
        return 0.0

    city = v.get("city", "") or ""
    domain_role = v.get("domain_role", "") or ""
    total_weight = 0.0

    for rule in _BENEFIT_KEYWORD_RULES:
        keyword, attr, match_values, weight = rule
        if keyword not in beneficiary_text:
            continue

        # Special pseudo-attributes
        if attr == "_city_contains":
            if any(fragment in city for fragment in match_values):
                total_weight += weight
        elif attr == "_city_major_cma":
            if any(cma in city for cma in _MAJOR_CMAS):
                total_weight += weight
        elif attr == "domain_role":
            # Direct domain_role match — only fires for domain persona agents
            if domain_role and domain_role in match_values:
                total_weight += weight
        else:
            val = v.get(attr, "") or ""
            if val in match_values:
                total_weight += weight

    # City name direct match (weight 3)
    policy_cities = benefit.get("cities_most_affected") or []
    if isinstance(policy_cities, list):
        for pc in policy_cities:
            if pc and pc.lower() in city.lower():
                total_weight += 3.0
                break

    # Primary-affected bonus: if this validator's domain_role maps to the benefit text,
    # add a flat +2.0 bonus. This ensures the people the policy is directly about
    # register meaningful benefit scores even when keyword matching is imprecise.
    if domain_role and domain_role in _DOMAIN_ROLE_PRIMARY_MATCH:
        triggers = _DOMAIN_ROLE_PRIMARY_MATCH[domain_role]
        if any(t in beneficiary_text for t in triggers):
            total_weight += 2.0

    # Universal policy bonus: if benefit explicitly covers all Canadians/households
    beneficiary_lower = beneficiary_text.lower()
    if any(kw in beneficiary_lower for kw in ("universal", "all canadian", "every canadian", "all household", "national coverage")):
        total_weight += 1.0

    return total_weight


async def call_benefits_specialist(client, thread_id, specialist, policy_text, policy_classification):
    """
    Ask one specialist: who benefits from this policy and how much?
    Runs in parallel with the risk round — separate thread.
    """
    relevant_cats = BENEFIT_RELEVANCE.get(specialist["id"], ["affordability", "income"])
    cats_str = ", ".join(relevant_cats)

    prompt = f"""You are a {specialist["title"]} analyzing a Canadian government policy.

Your domain: {specialist["focus"]}

Policy: {policy_text}
Policy classification: {json.dumps(policy_classification)}

Your task: identify WHO BENEFITS from this policy and HOW MUCH.

Before identifying benefits, state the policy's direct mechanism in one sentence.
Then identify 1-3 genuine benefits that this policy CREATES or MATERIALLY IMPROVES — not pre-existing conditions, not hoped-for outcomes with no causal link.

For each benefit:
- Name the specific group that gains
- Quantify the gain if possible (dollar amounts, % changes, people affected)
- Explain the direct causal mechanism from policy to benefit
- Rate magnitude: 1=minor, 2=moderate, 3=substantial
- Identify if the benefit is offset or limited by a countervailing risk

Focus on benefits in these categories relevant to your domain: {cats_str}

If this policy produces no genuine benefits in your domain, return an empty array.

Return only valid JSON:
{{
    "specialist": "{specialist["id"]}",
    "policy_mechanism": "one sentence — what this policy specifically does",
    "benefits": [
        {{
            "benefit": "one sentence — the specific benefit",
            "mechanism": "2 sentences — causal chain from policy action to benefit",
            "magnitude": 1|2|3,
            "category": "one of: {"|".join(BENEFIT_CATEGORIES)}",
            "primary_beneficiaries": "which demographic groups gain and why",
            "cities_most_affected": ["list", "of", "cities"],
            "caveat": "one sentence — what limits or offsets this benefit, or null"
        }}
    ]
}}

magnitude: 1=minor benefit for a narrow group, 2=moderate benefit for a meaningful segment, 3=substantial benefit broadly felt or deeply felt by a vulnerable group.
Only use magnitude 3 if you can defend it with population data."""

    try:
        response = await client.add_message(
            thread_id=thread_id,
            content=prompt,
            llm_provider="openai",
            model_name="gpt-4o",
            stream=False,
        )
        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        benefits = parsed.get("benefits", [])
        mechanism = parsed.get("policy_mechanism", "")
        # Validate each benefit
        valid = []
        for b in benefits:
            if (
                isinstance(b.get("benefit"), str) and len(b["benefit"]) > 10
                and isinstance(b.get("mechanism"), str)
                and b.get("magnitude") in (1, 2, 3)
                and b.get("category") in BENEFIT_CATEGORIES
            ):
                valid.append(b)
        return {
            "specialist": specialist["id"],
            "policy_mechanism": mechanism,
            "benefits": valid,
        }
    except Exception as e:
        return {
            "specialist": specialist["id"],
            "policy_mechanism": "",
            "benefits": [],
        }


async def run_benefits_analysis(client, asst_id, specialists, policy_text, policy_classification):
    """
    Run benefits analysis for all specialists in parallel.
    Returns list of specialist benefit results.
    """
    threads = await asyncio.gather(*[client.create_thread(asst_id) for _ in specialists])
    results = await asyncio.gather(*[
        call_benefits_specialist(client, t.thread_id, s, policy_text, policy_classification)
        for s, t in zip(specialists, threads)
    ])
    return list(results)


def aggregate_benefits(benefit_results: list, validator_results: list) -> dict:
    """
    Aggregate specialist benefits into:
    - benefit_items: flat list of all benefits with source
    - net_impact_by_group: per-demographic net score combining benefit gains vs risk burden
    - top_beneficiaries: ranked groups who gain most
    - benefit_coverage: how many validators are in primarily-benefiting groups
    """
    benefit_items = []
    for br in benefit_results:
        for b in br.get("benefits", []):
            benefit_items.append({
                **b,
                "source_specialist": br["specialist"],
            })

    # ── Deduplication pass ────────────────────────────────────────────────────
    # 1. Semantic dedup: within the same category, keep only the highest-magnitude
    #    item when two benefits share >50% of their non-stopword words.
    _STOPWORDS = {
        "a","an","the","and","or","of","in","to","for","is","are","that","this",
        "which","with","by","as","on","at","from","its","their","it","be","will",
        "can","may","has","have","been","more","than","who","what","how","policy",
    }

    def _content_words(text: str) -> set:
        return {w for w in text.lower().split() if w not in _STOPWORDS and len(w) > 2}

    def _overlap_ratio(a: str, b: str) -> float:
        wa, wb = _content_words(a), _content_words(b)
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / min(len(wa), len(wb))

    deduped: list = []
    for item in benefit_items:
        merged = False
        for existing in deduped:
            overlap = _overlap_ratio(existing["benefit"], item["benefit"])
            # Same category: dedup at 45% overlap; cross-category: dedup at 70% (near-identical wording)
            threshold = 0.45 if existing["category"] == item["category"] else 0.70
            if overlap >= threshold:
                if item.get("magnitude", 1) > existing.get("magnitude", 1):
                    deduped[deduped.index(existing)] = item
                merged = True
                break
        if not merged:
            deduped.append(item)
    benefit_items = deduped

    # 2. Cap per specialist: keep at most 2 benefits per source_specialist (highest magnitude)
    from collections import defaultdict
    specialist_buckets: dict = defaultdict(list)
    for item in benefit_items:
        specialist_buckets[item["source_specialist"]].append(item)
    benefit_items = []
    for items in specialist_buckets.values():
        items_sorted = sorted(items, key=lambda b: b.get("magnitude", 1), reverse=True)
        benefit_items.extend(items_sorted[:2])

    # 3. Cap per category: keep at most 3 benefits per category (highest magnitude)
    category_buckets: dict = defaultdict(list)
    for item in benefit_items:
        category_buckets[item["category"]].append(item)
    benefit_items = []
    for items in category_buckets.values():
        items_sorted = sorted(items, key=lambda b: b.get("magnitude", 1), reverse=True)
        benefit_items.extend(items_sorted[:3])
    # ── End deduplication ─────────────────────────────────────────────────────

    # Net impact scoring — primary signal is direct demographic matching between
    # each benefit's primary_beneficiaries text and the validator's actual profile.
    # This works for any policy domain (transit, healthcare, climate, etc.) not
    # just housing where policy_stance would be meaningful.

    net_impacts = []
    for v in validator_results:
        # Risk burden: avg severity of confirmed risks (0–3 scale)
        confirmed_sevs = [
            val["severity_for_me"]
            for val in v.get("validations", [])
            if val.get("applies") and val.get("severity_for_me", 0) > 0
        ]
        risk_score = sum(confirmed_sevs) / max(len(confirmed_sevs), 1) if confirmed_sevs else 0.0

        # Benefit signal: direct keyword/attribute matching against validator profile
        # For each benefit item, compute a match weight; if any attribute matches,
        # scale by magnitude and accumulate. Final benefit_score = avg over matched items.
        matched_benefits = []
        matched_scores = []

        for b in benefit_items:
            raw_weight = _score_benefit_for_validator(b, v)
            if raw_weight > 0.0:
                magnitude = b.get("magnitude", 1) or 1
                # Scale: weight * magnitude / 3.0, cap per-item at 3.0
                item_score = min(raw_weight * magnitude / 3.0, 3.0)
                matched_scores.append(item_score)
                matched_benefits.append(b["benefit"][:60])

        benefit_score = (
            sum(matched_scores) / len(matched_scores) if matched_scores else 0.0
        )
        # Cap overall benefit score at 3.0
        benefit_score = min(benefit_score, 3.0)

        # Net: benefit minus risk burden, bounded [-3, +3].
        # Validators who confirmed NO risks and matched NO benefits are truly
        # unaffected — score them neutral (0.0), not positive.
        # A low benefit_score from generic keyword noise (e.g. universal policy bonus)
        # should not push an unaffected validator into "net gain" territory.
        has_confirmed_risk = len(confirmed_sevs) > 0
        has_matched_benefit = len(matched_scores) > 0 and benefit_score >= 0.5
        if not has_confirmed_risk and not has_matched_benefit:
            net = 0.0
        else:
            net = benefit_score - risk_score
        net = max(-3.0, min(3.0, net))

        net_impacts.append({
            "agent_id": v["agent_id"],
            "city": v["city"],
            "tenure": v["tenure"],
            "age_bracket": v["age_bracket"],
            "income_bracket": v["income_bracket"],
            "risk_score": round(risk_score, 2),
            "benefit_score": round(benefit_score, 2),
            "net_impact": round(net, 2),
            "matched_benefits": matched_benefits[:3],
        })

    # Group net impact by demographic
    def group_net(dimension, key_fn):
        groups = {}
        for ni in net_impacts:
            k = key_fn(ni)
            if k not in groups:
                groups[k] = {"net_sum": 0, "count": 0, "risk_sum": 0, "benefit_sum": 0}
            groups[k]["net_sum"] += ni["net_impact"]
            groups[k]["risk_sum"] += ni["risk_score"]
            groups[k]["benefit_sum"] += ni["benefit_score"]
            groups[k]["count"] += 1
        return {
            k: {
                "avg_net": round(v["net_sum"] / v["count"], 2),
                "avg_risk": round(v["risk_sum"] / v["count"], 2),
                "avg_benefit": round(v["benefit_sum"] / v["count"], 2),
                "count": v["count"],
            }
            for k, v in groups.items()
        }

    net_by_tenure = group_net("tenure", lambda x: x["tenure"])
    net_by_income = group_net("income", lambda x: {
        "very_low": "low", "low": "low", "medium": "medium",
        "high": "high", "very_high": "high"
    }.get(x["income_bracket"], x["income_bracket"]))
    net_by_age = group_net("age", lambda x: {
        "18-24": "young (18-34)", "25-34": "young (18-34)",
        "35-49": "middle (35-49)", "50-64": "older (50-64)", "65+": "senior (65+)"
    }.get(x["age_bracket"], x["age_bracket"]))

    # Top beneficiaries — benefits with highest magnitude
    top_benefits = sorted(benefit_items, key=lambda b: b.get("magnitude", 0), reverse=True)[:5]

    # Summary counts — both raw (for display) and population-weighted (for accuracy)
    net_positive = sum(1 for ni in net_impacts if ni["net_impact"] > 0.2)
    net_negative = sum(1 for ni in net_impacts if ni["net_impact"] < -0.2)
    net_neutral = len(net_impacts) - net_positive - net_negative

    # Population-weighted equivalents: each validator counts by their population_weight
    # rather than 1 vote. Rural/remote validators have lower weight; domain personas
    # inherit the average weight of the agents they replaced.
    total_pop_weight = sum(v.get("population_weight", 1.0) for v in validator_results)
    net_positive_weighted = sum(
        v.get("population_weight", 1.0) for v, ni in zip(validator_results, net_impacts)
        if ni["net_impact"] > 0.2
    )
    net_negative_weighted = sum(
        v.get("population_weight", 1.0) for v, ni in zip(validator_results, net_impacts)
        if ni["net_impact"] < -0.2
    )
    net_neutral_weighted = total_pop_weight - net_positive_weighted - net_negative_weighted
    # Express as population-share fractions (0–1) for downstream use
    _w = max(total_pop_weight, 1.0)
    net_positive_pct = round(net_positive_weighted / _w, 3)
    net_negative_pct = round(net_negative_weighted / _w, 3)

    return {
        "benefit_items": benefit_items,
        "net_impacts": net_impacts,
        "net_by_tenure": net_by_tenure,
        "net_by_income": net_by_income,
        "net_by_age": net_by_age,
        "top_benefits": top_benefits,
        "summary": {
            "net_positive_validators": net_positive,
            "net_negative_validators": net_negative,
            "net_neutral_validators": net_neutral,
            "net_positive_weighted_pct": net_positive_pct,
            "net_negative_weighted_pct": net_negative_pct,
            "total_benefit_items": len(benefit_items),
        },
    }
