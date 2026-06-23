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
}


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
        from backboard import BackboardClient
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

    # Net impact scoring — primary signal is the validator's own policy_stance,
    # secondary signal is risk burden (confirmed severities).
    # Stance encoding: supportive=+2, indifferent=0, skeptical=-1, opposed=-2
    # Net = stance_score - normalised_risk_burden
    STANCE_SCORE = {
        "supportive": 2.0,
        "indifferent": 0.0,
        "skeptical_of_benefit": -1.0,
        "opposed": -2.0,
    }

    net_impacts = []
    for v in validator_results:
        # Risk burden: avg severity of confirmed risks (0–3 scale → 0–1 normalised)
        confirmed_sevs = [
            val["severity_for_me"]
            for val in v.get("validations", [])
            if val.get("applies") and val.get("severity_for_me", 0) > 0
        ]
        risk_score = sum(confirmed_sevs) / max(len(confirmed_sevs), 1) if confirmed_sevs else 0.0

        # Benefit signal: validator's own stance is the strongest ground-truth signal
        stance = v.get("behavioral_profile", {}).get("policy_stance", "indifferent") if v.get("behavioral_profile") else "indifferent"
        stance_val = STANCE_SCORE.get(stance, 0.0)

        # Secondary: keyword match from benefit items boosts benefit_score
        benefit_score = max(stance_val, 0.0)  # floor at 0 — negative stance ≠ negative benefit
        matched_benefits = []
        profile_text = " ".join([
            v.get("tenure", ""),
            v.get("income_bracket", ""),
            v.get("age_bracket", ""),
            v.get("immigration_status", ""),
            v.get("employment_type", ""),
        ]).lower()

        # Expand profile_text to include family_size
        family_text = v.get("family_size", "").lower().replace("_", " ")
        full_profile_text = profile_text + " " + family_text

        for b in benefit_items:
            beneficiary_text = (b.get("primary_beneficiaries", "") or "").lower()
            matches = 0
            for keyword in ["renter", "owner", "low-income", "low income", "high income",
                           "young", "senior", "immigrant", "indigenous", "rural", "urban",
                           "worker", "first-time", "first time", "unemployed", "gig",
                           "family", "parent", "child", "household", "couple", "single",
                           "small family", "large family"]:
                if keyword in beneficiary_text and keyword in full_profile_text:
                    matches += 1
            if matches > 0:
                benefit_score = max(benefit_score, b.get("magnitude", 1) * min(matches, 2) * 0.5)
                matched_benefits.append(b["benefit"][:60])

        # Net: stance-driven benefit minus risk burden, bounded [-3, +3]
        # risk_score weight 0.3 — risk burden is real but stance is the primary signal
        # Indifferent validators with low risk scores should land near 0, not slightly negative
        net = stance_val - (risk_score * 0.3)
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

    # Summary counts
    net_positive = sum(1 for ni in net_impacts if ni["net_impact"] > 0.3)
    net_negative = sum(1 for ni in net_impacts if ni["net_impact"] < -0.3)
    net_neutral = len(net_impacts) - net_positive - net_negative

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
            "total_benefit_items": len(benefit_items),
        },
    }
