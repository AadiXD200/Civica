"""
ai_policy_context.py

Loads AI policy statistics from data/ai_policy_stats.json (derived from
Canada's AI for All Strategy 2026, Statistics Canada Q2 2024 AI Adoption Survey,
and CIFAR Impact Report 2023-2024) and formats them for specialist prompts.

Mirrors the role that citations.py + survey_stats.json play for housing policy.
"""

import json
import os

_AI_STATS = None


def _load_ai_stats() -> dict:
    global _AI_STATS
    if _AI_STATS is None:
        path = os.path.join(os.path.dirname(__file__), "data", "ai_policy_stats.json")
        try:
            with open(path) as f:
                _AI_STATS = json.load(f)
        except Exception:
            _AI_STATS = {}
    return _AI_STATS


def is_ai_policy(policy_classification: dict) -> bool:
    """Returns True if the policy classification indicates an AI/tech policy."""
    policy_type = policy_classification.get("type", "").lower()
    key_attrs = [a.lower() for a in policy_classification.get("key_attributes", [])]
    policy_text_hint = policy_classification.get("summary", "").lower()

    ai_keywords = {"ai", "artificial intelligence", "technology", "digital", "tech",
                   "automation", "algorithm", "data", "compute", "sovereignty"}

    if policy_type in ("ai", "technology", "digital", "labour") and any(
        kw in " ".join(key_attrs) for kw in ai_keywords
    ):
        return True

    # Check if key attributes reference AI/tech
    if any(kw in " ".join(key_attrs) for kw in {"ai", "artificial_intelligence", "tech", "digital", "workers", "automation"}):
        return True

    return False


def format_ai_stats_for_specialist(
    specialist_categories: list[str],
    policy_classification: dict,
) -> str:
    """
    Returns a data block for AI policy specialist prompts.
    Selects the most relevant stats for the specialist's domain categories.
    """
    stats = _load_ai_stats()
    if not stats:
        return ""

    adoption = stats.get("adoption", {})
    workforce = stats.get("workforce", {})
    research = stats.get("research_talent", {})
    investment = stats.get("investment", {})
    risks = stats.get("risks_and_gaps", {})
    regulatory = stats.get("regulatory_context", {})

    lines = [
        "Canadian AI sector data (grounded in Statistics Canada, ISED, and CIFAR 2024-2026 sources):",
    ]

    # Core adoption stats — always relevant
    lines.append(
        f"  National AI adoption: {adoption.get('national_ai_adoption_pct')}% of Canadian businesses "
        f"currently use AI (StatsCan Q2 2024). Government target: {adoption.get('government_target_2034_pct')}% by 2034."
    )
    lines.append(
        f"  Adoption gap: {adoption.get('current_adoption_gap')}"
    )
    lines.append(
        f"  SMEs: {risks.get('sme_capacity', {}).get('sme_share_of_businesses_pct')}% of businesses are SMEs, "
        f"employing {risks.get('sme_capacity', {}).get('sme_employment_millions')}M workers. "
        f"{risks.get('adoption_gap', {}).get('barrier_pct_of_non_adopters')}% of non-adopters cite barriers to adoption."
    )

    # Domain-specific stats
    if any(c in specialist_categories for c in ["employment", "displacement"]):
        emp = workforce.get("employment_impact_of_adoption", {})
        pro = workforce.get("pro_worker_evidence", {})
        lines.append(
            f"  Employment impact: {emp.get('no_change_pct')}% of AI-adopting businesses reported NO change in "
            f"employee numbers (StatsCan Q2 2024). {emp.get('reduced_tasks_small_extent_pct')}% reported AI "
            f"reduced tasks by a small extent."
        )
        lines.append(
            f"  Pro-worker evidence: OECD survey across 7 countries incl. Canada — "
            f"{pro.get('oecd_survey_improved_performance_pct')}% of workers said AI improved their performance; "
            f"AI users 4× more likely to report job satisfaction gains."
        )
        lines.append(
            f"  Vulnerable sectors (lowest adoption, highest displacement risk if rapid scaling): "
            f"accommodation/food (0.9%), agriculture (0.7%), mining/oil & gas (1.6%)."
        )
        lines.append(
            f"  Government job targets: create up to {workforce.get('government_job_targets', {}).get('new_ai_related_jobs_target'):,} "
            f"AI-related jobs and {workforce.get('government_job_targets', {}).get('new_jobs_through_adoption_target'):,} "
            f"new jobs through adoption by 2031."
        )

    if any(c in specialist_categories for c in ["fiscal", "infrastructure"]):
        lines.append(
            f"  Public investment: $500M LIFT program, $500M Canadian Tech Fund, $200M health AI, "
            f"$1.75B in existing Budget 2025 commitments, $2B+ in compute infrastructure."
        )
        lines.append(
            f"  GDP potential: generative AI alone projected to add $187B to Canadian GDP; "
            f"strategy targets $200B in total GDP gains from labour productivity."
        )
        lines.append(
            f"  VC investment: Canada ranked globally with $3.1B VC invested in AI in 2025; "
            f"57% of all Canadian VC went to information/tech sector."
        )

    if any(c in specialist_categories for c in ["equity", "geographic"]):
        regional = risks.get("regional_disparity", {})
        lines.append(
            f"  Regional concentration: AI hubs in Toronto (Vector), Montreal (Mila), Edmonton (Amii). "
            f"Benefits concentrated in major urban centres; rural and remote communities face access barriers."
        )
        lines.append(
            f"  Indigenous impact: Documented disproportionate exposure to AI harms for Indigenous Peoples. "
            f"Canada's AI strategy explicitly commits to Indigenous leadership in AI governance."
        )
        lines.append(
            f"  AI adoption by industry: tech/cultural industries 20.9%, professional services 13.7%, "
            f"finance 10.9% — vs agriculture 0.7%, accommodation 0.9%. Rural/resource sector workers least affected currently but face structural risk."
        )

    if any(c in specialist_categories for c in ["affordability", "timeline"]):
        lines.append(
            f"  Adoption timeline: scaling from 6.1% to 60% adoption by 2034 requires 10× growth in 10 years. "
            f"No comparable economy has achieved this pace of enterprise AI adoption."
        )
        lines.append(
            f"  SME capacity gap: 78% of non-adopting firms cite barriers. "
            f"Compliance costs on SMEs could widen gap between large and small businesses."
        )

    if "geographic" in specialist_categories or "equity" in specialist_categories:
        sovereignty = risks.get("sovereignty", {})
        lines.append(
            f"  Sovereignty risk: {sovereignty.get('concern')}. {sovereignty.get('context')}."
        )

    # Regulatory context — always relevant for AI policy
    lines.append(
        f"  Regulatory gap: EU AI Act passed 2024. Canada has no equivalent. "
        f"AIDA (Bill C-27) proposed but not yet law. Treasury Board Directive applies only to federal government."
    )

    # Research talent
    lines.append(
        f"  Research strength: Canada ranks {research.get('canada_ai_research_rank_per_capita')}nd globally "
        f"in AI research per capita, {research.get('canada_global_ai_index_rank')}th in Global AI Index. "
        f"{research.get('active_canada_cifar_ai_chairs')} active Canada CIFAR AI Chairs across "
        f"{research.get('cifar_researcher_institutions')} institutions. "
        f"{research.get('actively_engaged_ai_professionals'):,} actively engaged AI professionals."
    )

    # Citations
    sources = stats.get("sources", [])
    if sources:
        lines.append("  Sources: " + " | ".join(
            f"{s['name']} ({s['year']}, {s['publisher']})" for s in sources
        ))

    return "\n".join(lines)


def get_ai_policy_documents() -> list[dict]:
    """
    Returns policy document entries for AI policy, formatted for citations.py.
    These are injected alongside housing policy documents when the policy type is AI/tech.
    """
    stats = _load_ai_stats()
    sources = stats.get("sources", [])

    docs = []
    for s in sources:
        docs.append({
            "id": s["id"],
            "title": s["name"],
            "url": s["url"],
            "topics": ["ai", "technology", "employment", "fiscal", "equity", "geographic", "infrastructure"],
            "snippet": _get_source_snippet(s["id"], stats),
        })
    return docs


def _get_source_snippet(source_id: str, stats: dict) -> str:
    """Returns a key finding snippet for each source document."""
    adoption = stats.get("adoption", {})
    workforce = stats.get("workforce", {})
    research = stats.get("research_talent", {})

    snippets = {
        "statscan_ai_adoption_2024": (
            f"Only {adoption.get('national_ai_adoption_pct')}% of Canadian businesses use AI in producing goods or "
            f"delivering services (Q2 2024). Adoption is highest in information and cultural industries "
            f"({adoption.get('by_industry', {}).get('information_and_cultural')}%) and lowest in agriculture "
            f"({adoption.get('by_industry', {}).get('agriculture_forestry_fishing')}%). "
            f"{workforce.get('employment_impact_of_adoption', {}).get('no_change_pct')}% of adopting businesses "
            f"report no change in employee numbers."
        ),
        "ai_strategy_2026": (
            f"Canada's digital sector employs ~800,000 workers and contributes $140B+ to GDP, with 150,000 jobs "
            f"directly in AI. Government targets: increase AI adoption from 12% to 60% by 2034, create 90,000 "
            f"AI-related jobs, unlock $200B in GDP gains. Canada lags Nordic countries (29-42% adoption) and "
            f"faces an SME adoption challenge — 99.8% of Canadian businesses are SMEs."
        ),
        "cifar_impact_2024": (
            f"Canada ranks 2nd globally in AI research papers per capita and 5th in the Global AI Index. "
            f"129 active Canada CIFAR AI Chairs across {research.get('cifar_researcher_institutions')} institutions. "
            f"140,418 actively engaged AI professionals. AI hubs in Toronto, Montreal, and Edmonton. "
            f"65% of CIFAR researchers contribute to top 1% most-cited papers worldwide."
        ),
    }
    return snippets.get(source_id, "")


if __name__ == "__main__":
    print("AI Policy Stats loaded:", bool(_load_ai_stats()))
    print()

    test_classification = {
        "type": "labour",
        "primary_affected": "workers",
        "geography": "national",
        "time_horizon": "long_term",
        "key_attributes": ["workers", "ai", "automation", "sme"],
        "summary": "AI disclosure and accountability requirements for businesses"
    }

    print("Is AI policy:", is_ai_policy(test_classification))
    print()
    print("=== EMPLOYMENT SPECIALIST BLOCK ===")
    block = format_ai_stats_for_specialist(["employment", "displacement"], test_classification)
    print(block)
    print()
    print("=== FISCAL SPECIALIST BLOCK ===")
    block2 = format_ai_stats_for_specialist(["fiscal", "infrastructure"], test_classification)
    print(block2)
