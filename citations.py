import json
import os

_DOCS = None
_SURVEY_STATS = None

from historical_outcomes import find_relevant_policies, format_historical_context_for_specialist
from ai_policy_context import is_ai_policy, format_ai_stats_for_specialist, get_ai_policy_documents

def _load_docs():
    global _DOCS
    if _DOCS is None:
        path = os.path.join(os.path.dirname(__file__), "data", "policy_documents.json")
        with open(path) as f:
            _DOCS = json.load(f)
    return _DOCS


_NON_HOUSING_DOMAINS = {
    "ai", "technology", "digital", "labour", "employment", "healthcare", "health",
    "pharma", "pharmacare", "environment", "climate", "carbon", "energy", "transit",
    "infrastructure", "transportation", "corrections", "justice", "criminal_justice",
    "education", "immigration", "fiscal",
}


def get_relevant_docs(specialist_categories: list[str], policy_classification: dict, max_docs: int = 4, include_ai: bool = True) -> list[dict]:
    """
    Returns the most relevant documents for a specialist given their domain
    categories and the policy classification.
    """
    docs = _load_docs()

    policy_domain = (policy_classification.get("domain") or "housing").lower()
    is_non_housing = policy_domain in _NON_HOUSING_DOMAINS

    # Build a relevance set: specialist categories + policy type topics
    relevant_topics = set(specialist_categories)
    domain = policy_classification.get("domain", "")
    if domain:
        relevant_topics.add(domain)
    if policy_classification.get("primary_affected"):
        affected = policy_classification["primary_affected"].lower()
        if "immigrant" in affected or "immigration" in affected:
            relevant_topics.add("equity")
        if "indigenous" in affected:
            relevant_topics.add("equity")
            relevant_topics.add("geographic")
        if "senior" in affected or "elder" in affected:
            relevant_topics.add("equity")
        if "youth" in affected or "young" in affected:
            relevant_topics.add("equity")
    if policy_classification.get("geography") in ("northern", "rural", "remote"):
        relevant_topics.add("geographic")

    # Score each doc by topic overlap
    scored = []
    for doc in docs:
        doc_topics = set(doc.get("topics", []))
        # For non-housing policies, exclude docs whose primary topic is housing
        # (i.e. "housing" is their only or first topic) — they'll contaminate findings.
        if is_non_housing and "housing" in doc_topics and len(doc_topics - {"housing"}) == 0:
            continue  # purely housing doc — irrelevant to this domain
        overlap = len(doc_topics & relevant_topics)
        if overlap > 0:
            scored.append((overlap, doc))

    # Sort by overlap desc, take top N
    scored.sort(key=lambda x: -x[0])
    result = [doc for _, doc in scored[:max_docs]]

    # Inject AI policy documents if this is an AI/tech policy
    if include_ai and is_ai_policy(policy_classification):
        ai_docs = get_ai_policy_documents()
        # Add AI docs not already in result (avoid duplicates by id)
        existing_ids = {d.get("id") for d in result}
        for d in ai_docs:
            if d["id"] not in existing_ids:
                result.append(d)

    return result


def format_docs_for_prompt(docs: list[dict]) -> str:
    """Format retrieved docs as a prompt-injectable reference block."""
    if not docs:
        return ""
    lines = ["Reference documents (cite these when making factual claims):"]
    for i, doc in enumerate(docs, 1):
        lines.append(f"\n[{i}] {doc['title']}")
        lines.append(f"    {doc['snippet']}")
    return "\n".join(lines)


def _load_survey_stats() -> dict:
    global _SURVEY_STATS
    if _SURVEY_STATS is None:
        path = os.path.join(os.path.dirname(__file__), "data", "survey_stats.json")
        if os.path.exists(path):
            with open(path) as f:
                _SURVEY_STATS = json.load(f)
        else:
            _SURVEY_STATS = {}
    return _SURVEY_STATS


def format_survey_stats_for_prompt(policy_classification: dict, specialist_categories: list[str] | None = None) -> str:
    """
    Returns survey statistics block tailored to the policy context.
    For AI/tech policies: injects AI sector stats from Canada's AI strategy + StatsCan.
    For housing policies: injects CHS 2022 microdata stats.
    For mixed policies: injects both.
    """
    # AI policy — swap in AI stats instead of (or in addition to) housing stats
    if is_ai_policy(policy_classification):
        cats = specialist_categories or []
        ai_block = format_ai_stats_for_specialist(cats, policy_classification)
        # Also include brief housing context if the policy touches housing
        market = policy_classification.get("market", "")
        if market in ("rental", "ownership", "both"):
            housing_block = _format_housing_stats_block(policy_classification)
            return ai_block + "\n\n" + housing_block if housing_block else ai_block
        return ai_block

    return _format_housing_stats_block(policy_classification)


def _format_housing_stats_block(policy_classification: dict) -> str:
    """Original housing stats block — extracted for reuse."""
    stats = _load_survey_stats()
    if not stats:
        return ""

    nat = stats.get("national", {})
    dem = stats.get("by_demographic", {})
    regional = stats.get("by_region", {})
    quintiles = stats.get("by_income_quintile", {})

    lines = [
        "Survey data — Statistics Canada, Canadian Housing Survey 2022 (n=37,102 weighted households):",
        f"  National: {nat.get('core_housing_need_pct')}% in core housing need | "
        f"{nat.get('shelter_cost_30pct_plus_pct')}% spend ≥30% income on shelter (PUMF: codes 2–3 of 3) | "
        f"{nat.get('renter_pct')}% renters | median income ${nat.get('median_household_income', 0):,}",
        "  Note: PUMF shelter cost uses 3-group recode — code 1=<30%, code 2=30–99%, code 3=≥100% of income",
    ]

    # Regional breakdown
    lines.append("  By region (core housing need % | shelter cost ≥30% | renters %):")
    for region, s in regional.items():
        lines.append(
            f"    {region}: {s.get('core_housing_need_pct')}% | "
            f"{s.get('shelter_cost_30pct_plus_pct')}% | {s.get('renter_pct')}% renters"
        )

    # Demographic breakdowns — always include the most policy-relevant ones
    affected = (policy_classification.get("primary_affected") or "").lower()
    geography = policy_classification.get("geography", "")

    lines.append("  Key demographic breakdowns (core housing need %):")
    lines.append(
        f"    Renters: {dem.get('renters', {}).get('core_housing_need_pct')}% | "
        f"Owners: {dem.get('owners', {}).get('core_housing_need_pct')}%"
    )
    lines.append(
        f"    Immigrants: {dem.get('immigrants', {}).get('core_housing_need_pct')}% "
        f"({dem.get('immigrants', {}).get('renter_pct')}% are renters) | "
        f"Non-immigrants: {dem.get('non_immigrants', {}).get('core_housing_need_pct')}%"
    )
    lines.append(
        f"    Visible minority HH: {dem.get('visible_minority_households', {}).get('core_housing_need_pct')}% | "
        f"Non-visible minority: {dem.get('non_visible_minority_households', {}).get('core_housing_need_pct')}%"
    )
    lines.append(
        f"    No employed person in HH: {dem.get('no_employed_person', {}).get('core_housing_need_pct')}%"
    )

    # Age breakdown
    by_age = dem.get("by_age", {})
    if by_age:
        age_parts = " | ".join(
            f"{age}: {s.get('core_housing_need_pct')}%" for age, s in by_age.items()
        )
        lines.append(f"    By age: {age_parts}")

    # Income quintile — always useful for affordability/displacement risks
    if quintiles:
        lines.append("  Core housing need by income quintile:")
        for q, s in quintiles.items():
            lines.append(f"    {q} ({s.get('income_range')}): {s.get('core_housing_need_pct')}%")

    lines.append(f"  Citation: {stats.get('citation', 'Statistics Canada CHS 2022')}")
    return "\n".join(lines)


def format_historical_precedents_for_specialist(
    specialist_categories: list[str],
    policy_classification: dict,
) -> str:
    """
    Returns a historical precedent block for a specialist prompt, matching
    real Canadian policies by type, geography, and specialist domain.
    Returns empty string if no relevant precedents found.
    """
    policy_type = policy_classification.get("type", "")
    geography   = policy_classification.get("geography", "")
    affected    = policy_classification.get("primary_affected", "")

    relevant = find_relevant_policies(policy_type, geography, affected, max_results=2)
    if not relevant:
        return ""

    return format_historical_context_for_specialist(relevant, specialist_categories)
