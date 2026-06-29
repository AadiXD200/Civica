"""
domain_context.py — Provides domain-specific Canadian statistics for validator prompts.

Domains supported: transit, healthcare, climate, labour, housing, corrections,
                   fiscal, education, immigration, ai (and common aliases).

Files loaded (lazy, cached):
    data/transit_stats.json
    data/healthcare_stats.json
    data/climate_stats.json
    data/labour_stats.json
    data/ai_policy_stats.json
    data/city_profiles.json  (housing/demographic context)
"""

import inspect
import json
import os
from functools import lru_cache
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


@lru_cache(maxsize=None)
def _load_json(filename: str) -> dict:
    """Lazy-load and cache a JSON file from the data directory."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _transit_stats(city: Optional[str] = None) -> str:
    data = _load_json("transit_stats.json")
    if not data:
        return ""

    national = data.get("national", {})
    lines = [
        "=== CANADIAN TRANSIT STATISTICS ===",
        f"National transit mode share: {national.get('transit_commuters_pct', 'N/A')}% of commuters",
        f"Car commuters: {national.get('car_commuters_pct', 'N/A')}%",
        f"Active transport (walk/cycle): {national.get('active_transport_pct', 'N/A')}%",
        f"Average commute: {national.get('avg_commute_minutes', 'N/A')} minutes",
        f"Source: {national.get('source', 'StatsCan NHS 2021')}",
    ]

    if city:
        city_data = data.get("by_city", {}).get(city)
        if city_data:
            lines.append(f"\n--- {city} Transit ---")
            lines.append(f"Transit mode share: {city_data.get('transit_mode_share_pct', 'N/A')}%")
            lines.append(f"Average commute: {city_data.get('avg_commute_min', 'N/A')} minutes")
            lines.append(f"Car ownership per household: {city_data.get('car_ownership_per_hh', 'N/A')}")
            lines.append(f"Active transport: {city_data.get('active_transport_pct', 'N/A')}%")
            src = city_data.get("source") or city_data.get("notes", "")
            if src:
                lines.append(f"Source: {src}")

    infra = data.get("infrastructure", {})
    if infra:
        lines.append("\n--- Federal Transit Context ---")
        lines.append(f"Canada Public Transit Fund: ${infra.get('federal_transit_fund_billions', 'N/A')}B")
        lines.append(f"Zero-emission bus target: {infra.get('zero_emission_bus_target_year', 'N/A')}")
        lines.append(f"Ridership recovery (% of 2019): {infra.get('transit_ridership_recovery_pct_of_2019', 'N/A')}%")

    return "\n".join(lines)


def _healthcare_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    data = _load_json("healthcare_stats.json")
    if not data:
        return ""

    national = data.get("national", {})
    lines = [
        "=== CANADIAN HEALTHCARE STATISTICS ===",
        f"Without a family doctor (national): {national.get('without_family_doctor_pct', 'N/A')}%",
        f"Rural without a doctor: {national.get('rural_without_doctor_pct', 'N/A')}%",
        f"Median ER wait time: {national.get('median_er_wait_hours', 'N/A')} hours",
        f"Physicians per 1,000: {national.get('physicians_per_1000', 'N/A')}",
        f"Nurses per 1,000: {national.get('nurses_per_1000', 'N/A')}",
        f"LTC wait median: {national.get('long_term_care_wait_days_median', 'N/A')} days",
        f"Unmet mental health needs: {national.get('mental_health_unmet_needs_pct', 'N/A')}%",
        f"Source: {national.get('source', 'CIHI 2023')}",
    ]

    if province:
        prov_data = data.get("by_province", {}).get(province)
        if prov_data:
            lines.append(f"\n--- {province} Healthcare ---")
            lines.append(f"Without family doctor: {prov_data.get('without_family_doctor_pct', 'N/A')}%")
            lines.append(f"Median ER wait: {prov_data.get('median_er_wait_hours', 'N/A')} hours")
            lines.append(f"Physicians per 1,000: {prov_data.get('physicians_per_1000', 'N/A')}")
            lines.append(f"Health spending per capita: ${prov_data.get('public_health_spending_per_capita', 'N/A')}")
            lines.append(f"LTC wait median: {prov_data.get('ltc_wait_days_median', 'N/A')} days")
            src = prov_data.get("source") or prov_data.get("notes", "")
            if src:
                lines.append(f"Note: {src}")

    mh = data.get("mental_health", {})
    if mh:
        lines.append("\n--- Mental Health ---")
        lines.append(f"Reporting excellent mental health: {mh.get('reported_excellent_mental_health_pct', 'N/A')}%")
        lines.append(f"Youth in high distress (15-24): {mh.get('youth_mental_health_crisis_pct', 'N/A')}%")
        lines.append(f"Severe mental illness: {mh.get('severe_mental_illness_pct', 'N/A')}%")
        src = mh.get("source") or mh.get("notes", "")
        if src:
            lines.append(f"Source: {src}")

    return "\n".join(lines)


def _climate_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    data = _load_json("climate_stats.json")
    if not data:
        return ""

    national = data.get("national", {})
    emissions_by_sector = national.get("emissions_by_sector_pct", {})
    lines = [
        "=== CANADIAN CLIMATE & ENERGY STATISTICS ===",
        f"Carbon price (2024): ${national.get('carbon_price_per_tonne_2024', 'N/A')}/tonne",
        f"Carbon price target (2030): ${national.get('carbon_price_per_tonne_2030_target', 'N/A')}/tonne",
        f"Average household carbon cost: ${national.get('avg_household_carbon_cost_annual', 'N/A')}/year",
        f"Average carbon rebate: ${national.get('carbon_rebate_avg_annual', 'N/A')}/year",
        f"Net benefit for average household: ${national.get('net_benefit_avg_household', 'N/A')}/year",
        f"Total GHG emissions (2022): {national.get('ghg_emissions_mt_co2e_2022', 'N/A')} Mt CO2e",
        f"2030 reduction target: {national.get('ghg_target_2030_pct_below_2005', 'N/A')}% below 2005",
        f"Clean electricity share: {national.get('clean_electricity_pct_2023', 'N/A')}%",
        f"EV sales share (2023): {national.get('ev_sales_share_pct_2023', 'N/A')}%",
    ]

    if emissions_by_sector:
        lines.append("Emissions by sector: " + ", ".join(
            f"{k}: {v}%" for k, v in emissions_by_sector.items()
        ))
    lines.append(f"Source: {national.get('source', 'ECCC 2024')}")

    if province:
        prov_data = data.get("by_province", {}).get(province)
        if prov_data:
            lines.append(f"\n--- {province} Climate Profile ---")
            lines.append(f"Emissions per capita: {prov_data.get('emissions_per_capita_tco2e', 'N/A')} tCO2e")
            if "oil_gas_employment_pct" in prov_data:
                lines.append(f"Oil & gas employment: {prov_data['oil_gas_employment_pct']}%")
            if "clean_electricity_pct" in prov_data:
                lines.append(f"Clean electricity: {prov_data['clean_electricity_pct']}%")
            if "coal_power_pct" in prov_data:
                lines.append(f"Coal power share: {prov_data['coal_power_pct']}%")
            src = prov_data.get("source") or prov_data.get("notes", "")
            if src:
                lines.append(f"Note: {src}")

        rebate_data = data.get("carbon_rebate_by_province", {}).get(province)
        if rebate_data:
            lines.append(f"\n--- {province} Carbon Rebate ---")
            lines.append(f"Single adult: ${rebate_data.get('single_adult', 'N/A')}/year")
            lines.append(f"Family of four: ${rebate_data.get('family_of_four', 'N/A')}/year")

    clean_econ = data.get("clean_economy", {})
    if clean_econ:
        lines.append("\n--- Clean Economy ---")
        lines.append(f"Clean tech jobs (2022): {clean_econ.get('clean_tech_jobs_2022', 'N/A'):,}")
        lines.append(f"Federal clean economy investment: ${clean_econ.get('federal_clean_economy_investment_ira_response_billions', 'N/A')}B")

    return "\n".join(lines)


def _labour_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    data = _load_json("labour_stats.json")
    if not data:
        return ""

    national = data.get("national", {})
    lines = [
        "=== CANADIAN LABOUR MARKET STATISTICS ===",
        f"Overall unemployment rate: {national.get('overall_unemployment_pct', 'N/A')}%",
        f"Youth unemployment: {national.get('youth_unemployment_pct', 'N/A')}%",
        f"Participation rate: {national.get('participation_rate_pct', 'N/A')}%",
        f"Median hourly wage: ${national.get('median_hourly_wage', 'N/A')}",
        f"Average hourly wage: ${national.get('avg_hourly_wage', 'N/A')}",
        f"Union coverage: {national.get('union_coverage_pct', 'N/A')}%",
        f"Gig/platform workers: {national.get('gig_workers_pct', 'N/A')}%",
        f"Self-employed: {national.get('self_employed_pct', 'N/A')}%",
        f"Part-time: {national.get('part_time_pct', 'N/A')}%",
        f"Gender wage ratio (women/men): {national.get('women_wage_gap_pct', 'N/A')}%",
        f"Federal minimum wage: ${national.get('federal_minimum_wage', 'N/A')}/hr",
        f"Source: {national.get('source', 'StatsCan LFS 2024')}",
    ]

    if city:
        city_data = data.get("by_city", {}).get(city)
        if city_data:
            lines.append(f"\n--- {city} Labour Market ---")
            lines.append(f"Unemployment rate: {city_data.get('unemployment_rate', 'N/A')}%")
            lines.append(f"Median hourly wage: ${city_data.get('median_hourly_wage', 'N/A')}")
            lines.append(f"Public sector share: {city_data.get('public_sector_pct', 'N/A')}%")
            lines.append(f"Union coverage: {city_data.get('union_coverage_pct', 'N/A')}%")
            for extra_key in ["tech_employment_pct", "oil_gas_employment_pct", "manufacturing_pct", "federal_government_pct"]:
                if extra_key in city_data:
                    label = extra_key.replace("_pct", "").replace("_", " ").title()
                    lines.append(f"{label}: {city_data[extra_key]}%")
            src = city_data.get("source") or city_data.get("notes", "")
            if src:
                lines.append(f"Note: {src}")

    if province:
        min_wages = data.get("minimum_wages_by_province", {})
        prov_min = min_wages.get(province)
        if prov_min:
            lines.append(f"\n{province} minimum wage: ${prov_min}/hr")
            lines.append(f"Source: {min_wages.get('source', 'Provincial Labour Ministries 2024')}")

    sectors = data.get("by_sector", {})
    if sectors:
        lines.append("\n--- Union Coverage by Sector (national) ---")
        for sector, sdata in sectors.items():
            if sector == "source":
                continue
            cov = sdata.get("union_coverage_pct", "N/A")
            wage = sdata.get("median_wage", "N/A")
            label = sector.replace("_", " ").title()
            lines.append(f"  {label}: {cov}% union coverage, ${wage}/hr median")

    return "\n".join(lines)


def _housing_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    """Pull housing context from city_profiles.json."""
    data = _load_json("city_profiles.json")
    if not data:
        return ""

    lines = ["=== CANADIAN HOUSING STATISTICS ==="]

    if city and city in data:
        profile = data[city]
        lines.append(f"\n--- {city} Housing Profile ---")
        if "avg_rent_1br" in profile:
            lines.append(f"Average 1BR rent: ${profile['avg_rent_1br']:,.0f}/month")
        if "avg_rent_2br" in profile:
            lines.append(f"Average 2BR rent: ${profile['avg_rent_2br']:,.0f}/month")
        if "vacancy_rate" in profile:
            lines.append(f"Vacancy rate: {profile['vacancy_rate']}%")
        if "median_household_income" in profile:
            lines.append(f"Median household income: ${profile['median_household_income']:,.0f}")
        if "shelter_cost_to_income_ratio" in profile:
            lines.append(f"Shelter cost-to-income ratio: {profile['shelter_cost_to_income_ratio']:.1%}")
        if "unemployment_rate" in profile:
            lines.append(f"Unemployment rate: {profile['unemployment_rate']}%")
        if "population" in profile:
            lines.append(f"Population: {profile['population']:,.0f}")
        if "housing_starts_annual" in profile:
            lines.append(f"Housing starts (annual): {profile['housing_starts_annual']:,.0f}")
        if "transit_mode_share_pct" in profile:
            lines.append(f"Transit mode share: {profile['transit_mode_share_pct']}%")
    else:
        # Summarize a few cities
        for c, profile in list(data.items())[:5]:
            rent = profile.get("avg_rent_1br", "N/A")
            vacancy = profile.get("vacancy_rate", "N/A")
            lines.append(f"  {c}: 1BR ${rent}/mo, vacancy {vacancy}%")

    return "\n".join(lines)


def _corrections_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    lines = [
        "Corrections and reintegration policy context (Statistics Canada, CSC Annual Report, PBO 2023):",
        "- ~24,000 adults in federal custody on any given day; ~87,000 under federal supervision (incl. conditional release)",
        "- Recidivism rate within 2 years of release: ~33% for any reoffending, ~14% for violent reoffending",
        "- Indigenous people: 32% of federal inmates vs 5% of Canadian population — most severe over-representation",
        "- Women represent 7% of federal inmates; Indigenous women are 50% of the women's incarcerated population",
        "- ~70% of released federal offenders access social assistance within 6 months of release",
        "- Average annual cost per federal inmate: ~$119,000 (PBO 2023); community supervision: ~$40,000",
        "- Transitional housing demand exceeds supply in all major CMAs; average wait for halfway house placement: 4–8 weeks post-release",
        "- Ban the Box policies (removing criminal record questions from job applications) show 3–7% increase in call-back rates for affected groups (Decker et al., comparable US studies)",
        "- Employment Tax Credits for hiring justice-involved workers: uptake typically 15–25% of eligible employers in first 3 years",
        "- Healing lodges (Indigenous corrections model): 10 federally operated; capacity ~200; waitlist typically 6–12 months",
        "- Parole eligibility reform: early release on earned remission vs statutory release — affects ~18,000 federal cases/year",
    ]
    if province:
        if province == "ON":
            lines.append("- Ontario: ~7,800 under federal supervision; Toronto has highest concentration of halfway houses (38 CRF units)")
        elif province == "BC":
            lines.append("- BC: ~3,200 under federal supervision; Vancouver Downtown Eastside concentrates reintegration services")
        elif province == "AB":
            lines.append("- Alberta: ~3,100 under federal supervision; Edmonton and Calgary account for 80% of provincial reintegration placements")
        elif province == "QC":
            lines.append("- Quebec: ~4,400 under federal supervision; dual federal/provincial corrections system creates jurisdictional overlap")
    return "\n".join(lines)


def _fiscal_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    lines = [
        "Fiscal/income support policy context (Statistics Canada SHS 2022 / PBO):",
        "- Median household after-tax income: $68,400 nationally (2022 SHS)",
        "- Bottom quintile median after-tax income: ~$22,000; top quintile: ~$145,000",
        "- Federal income tax revenues: ~$243B (2022–23); corporate tax: ~$75B",
        "- GST/HST revenues: ~$62B annually",
        "- Federal transfers to persons (OAS, EI, CCB, GIS): ~$124B annually",
        "- Child poverty rate: 10.5% (2021 census); seniors poverty rate (LIM-AT): 7.4%",
        "- EI regular benefit take-up rate: ~40% of unemployed qualify in a given month",
        "- Canada Child Benefit average benefit: ~$6,800/year for eligible families",
    ]
    return "\n".join(lines)


def _education_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    lines = [
        "Education policy context (Statistics Canada PIAAC 2022 / CAUT):",
        "- Post-secondary attainment: 68% of Canadians 25–64 have post-secondary credentials",
        "- University tuition average: $6,900/year (2023–24); up 40% in inflation-adjusted terms since 2000",
        "- Student debt: ~50% of graduates carry debt; median debt at graduation ~$17,500",
        "- Indigenous post-secondary attainment gap: 48% vs 68% national average",
        "- Rural-urban access gap: 22% of rural youth enrol in university vs 38% urban",
        "- International student share: ~25% of university enrolment in major institutions",
        "- K-12 spending per pupil: $14,200 nationally; varies from $11,100 (ON) to $22,600 (NT)",
        "- Special education funding: growing demand outpacing provincial allocations in most provinces",
    ]
    return "\n".join(lines)


def _immigration_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    lines = [
        "Immigration/settlement policy context (IRCC 2023 / Statistics Canada IMDB):",
        "- Annual permanent resident admissions: 465,000 (2023 target); ~60% economic class",
        "- Temporary resident population: ~2.5M study/work permit holders (2023)",
        "- Median employment income gap: recent immigrants earn ~72 cents per dollar of Canadian-born workers",
        "- 3-month provincial health coverage gap: affects ~30% of new arrivals in provinces with waiting periods",
        "- Credential recognition barriers: 35% of internationally trained professionals working in unrelated fields",
        "- Settlement service capacity: IRCC-funded orgs serve ~250,000 clients/year; waitlists common in high-intake cities",
        "- Refugee processing backlog: ~180,000 asylum claims pending as of 2023 (IRB)",
        "- Language training: LINC serves ~100,000 learners/year; demand estimated 3× capacity in Toronto/Vancouver",
    ]
    if province in ("ON", "BC", "QC", "AB"):
        prov_note = {
            "ON": "Ontario: ~45% of all permanent residents; settlement services concentrated in GTA",
            "BC": "British Columbia: ~16% of permanent residents; high cost-of-living amplifies settlement challenges",
            "QC": "Quebec: operates separate selection system (Quebec Skilled Worker); French-language requirement affects integration",
            "AB": "Alberta: high labour demand drives temporary foreign worker volumes; rural settlement underserviced",
        }
        lines.append(f"- {prov_note[province]}")
    return "\n".join(lines)


def _ai_stats(city: Optional[str] = None, province: Optional[str] = None) -> str:
    data = _load_json("ai_policy_stats.json")
    if data:
        lines = ["AI/technology policy context (Statistics Canada AI Adoption Survey 2024 / OECD):"]
        national = data.get("national", {})
        if national:
            lines.append(f"- AI adoption rate (Canadian firms): {national.get('ai_adoption_rate_pct', 6.1)}%")
            lines.append(f"- High-AI-adoption sectors: finance ({national.get('finance_adoption_pct', 34)}%), tech ({national.get('tech_adoption_pct', 28)}%), professional services ({national.get('professional_services_adoption_pct', 19)}%)")
            lines.append(f"- Workers in routine cognitive roles at near-term displacement risk: ~{national.get('routine_cognitive_worker_pct', 18)}% of workforce")
        lines += [
            "- Digital divide: 15% of Canadians lack adequate home internet (CRTC 2022); concentrated in rural/remote",
            "- Algorithmic decision-making: 40% of employment platforms use AI screening tools (OECD 2023)",
            "- Indigenous data sovereignty: FNIGC First Nations Principles of OCAP govern research data use",
        ]
        return "\n".join(lines)
    return (
        "AI/technology policy context (Statistics Canada AI Adoption Survey 2024 / OECD): "
        "6.1% of Canadian firms have adopted AI. High-adoption sectors: finance (34%), tech (28%), "
        "professional services (19%). Routine cognitive workers face highest near-term displacement risk. "
        "Digital divide: ~15% of Canadians lack adequate home internet."
    )


# Domain name aliases
_DOMAIN_HANDLERS = {
    "transit": _transit_stats,
    "transportation": _transit_stats,
    "commute": _transit_stats,
    "healthcare": _healthcare_stats,
    "health": _healthcare_stats,
    "mental_health": _healthcare_stats,
    "climate": _climate_stats,
    "environment": _climate_stats,
    "energy": _climate_stats,
    "carbon": _climate_stats,
    "labour": _labour_stats,
    "labor": _labour_stats,
    "employment": _labour_stats,
    "wages": _labour_stats,
    "housing": _housing_stats,
    "rent": _housing_stats,
    "corrections": _corrections_stats,
    "parole": _corrections_stats,
    "criminal_justice": _corrections_stats,
    "justice": _corrections_stats,
    "fiscal": _fiscal_stats,
    "tax": _fiscal_stats,
    "taxation": _fiscal_stats,
    "income_support": _fiscal_stats,
    "benefits": _fiscal_stats,
    "education": _education_stats,
    "school": _education_stats,
    "postsecondary": _education_stats,
    "immigration": _immigration_stats,
    "refugee": _immigration_stats,
    "settlement": _immigration_stats,
    "ai": _ai_stats,
    "technology": _ai_stats,
    "digital": _ai_stats,
    "automation": _ai_stats,
}


def get_domain_stats(
    domain: str,
    city: Optional[str] = None,
    province: Optional[str] = None,
) -> str:
    """
    Return a formatted text block of Canadian statistics for the given domain.

    Args:
        domain: One of 'transit', 'healthcare', 'climate', 'labour', 'housing', 'corrections',
                'fiscal', 'education', 'immigration', 'ai'
                (and common aliases like 'transportation', 'health', 'environment', etc.)
        city:   Optional city name (e.g. "Toronto") for city-level context
        province: Optional 2-letter province code (e.g. "ON") for province-level context

    Returns:
        Multi-line string ready for injection into a specialist system prompt.
        Returns empty string if domain is unrecognized or data files are missing.
    """
    handler = _DOMAIN_HANDLERS.get(domain.lower().strip())
    if handler is None:
        # Fall back: try to return everything if domain is 'all'
        if domain.lower() == "all":
            parts = []
            for fn in [_transit_stats, _healthcare_stats, _climate_stats, _labour_stats]:
                parts.append(fn(city=city if fn != _climate_stats else None,
                                province=province if fn != _transit_stats else None))
            return "\n\n".join(p for p in parts if p)
        return ""

    # Call with supported kwargs
    sig = inspect.signature(handler)
    kwargs = {}
    if "city" in sig.parameters:
        kwargs["city"] = city
    if "province" in sig.parameters:
        kwargs["province"] = province

    return handler(**kwargs)


if __name__ == "__main__":
    for _domain, _kwargs in [
        ("transit",     {"city": "Toronto"}),
        ("healthcare",  {"province": "QC"}),
        ("climate",     {"province": "AB"}),
        ("labour",      {"city": "Ottawa"}),
        ("housing",     {"city": "Vancouver"}),
        ("corrections", {"province": "ON"}),
        ("fiscal",      {}),
        ("education",   {}),
        ("immigration", {"province": "BC"}),
        ("ai",          {}),
    ]:
        print(f"=== {_domain} ===")
        print(get_domain_stats(_domain, **_kwargs))
        print()
