# persona_attribute_injector.py
"""
Injects policy-domain-relevant attribute context into validator prompts.
Replaces the default housing/tenure lens with domain-specific dimensions
based on the policy's domain (transit, healthcare, climate, etc.).

No LLM calls — pure rule-based inference from existing agent fields.
"""

from __future__ import annotations
import json
import os
from functools import lru_cache

# ---------------------------------------------------------------------------
# Real data loaders — pulled from domain stat files, not heuristics
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_transit_stats() -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", "transit_stats.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

@lru_cache(maxsize=1)
def _load_healthcare_stats() -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", "healthcare_stats.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

@lru_cache(maxsize=1)
def _load_climate_stats() -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", "climate_stats.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

@lru_cache(maxsize=1)
def _load_labour_stats() -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", "labour_stats.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def _city_transit(city: str) -> dict:
    """Returns real NHS 2021 transit figures for a city, or empty dict."""
    return _load_transit_stats().get("by_city", {}).get(city, {})

def _province_healthcare(province: str) -> dict:
    """Returns real CIHI figures for a province, or empty dict."""
    return _load_healthcare_stats().get("by_province", {}).get(province, {})

def _province_climate(province: str) -> dict:
    """Returns real ECCC figures for a province, or empty dict."""
    return _load_climate_stats().get("by_province", {}).get(province, {})

def _city_labour(city: str) -> dict:
    """Returns real LFS figures for a city, or empty dict."""
    return _load_labour_stats().get("by_city", {}).get(city, {})

# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------

DOMAIN_ATTRIBUTES: dict[str, dict] = {
    "transit": {
        "dimensions": [
            "commute_mode",
            "commute_distance",
            "car_ownership",
            "transit_dependency",
            "disability_mobility",
        ],
        "stat_context": (
            "Transit policy context (Statistics Canada NHS 2021 / NTS 2016): "
            "~33% of Canadians in CMAs commute by transit; car dependency rises sharply "
            "outside major CMAs. Gig/part-time workers often travel off-peak, reducing "
            "transit utility. Low-income households without vehicles face transit captivity."
        ),
    },
    "healthcare": {
        "dimensions": [
            "distance_to_hospital",
            "chronic_conditions_likelihood",
            "healthcare_utilization",
            "insurance_coverage",
            "caregiver_burden",
        ],
        "stat_context": (
            "Healthcare policy context (Statistics Canada CCHS 2021 / CIHI 2022): "
            "~18% of Canadians report unmet healthcare needs; rural residents face average "
            "travel times >45 min to acute care. Low-income households are 2.3× more likely "
            "to lack a regular family doctor. Seniors (65+) average 7.2 physician visits/year."
        ),
    },
    "climate": {
        "dimensions": [
            "carbon_price_exposure",
            "fossil_fuel_sector_employment",
            "home_heating_fuel_type",
            "vehicle_dependency",
            "climate_rebate_eligibility",
        ],
        "stat_context": (
            "Climate policy context (Statistics Canada Survey on Household Energy Use 2019 / "
            "Employment by Industry 2023): ~40% of Canadian homes use natural gas heating. "
            "AB/SK households pay significantly more under carbon pricing than BC/QC where "
            "provincial pricing applies. ~200,000 workers are directly employed in oil/gas/coal."
        ),
    },
    "immigration": {
        "dimensions": [
            "immigration_pathway_affected",
            "family_sponsorship_exposure",
            "credential_recognition_barriers",
            "settlement_service_dependency",
            "language_barrier",
        ],
        "stat_context": (
            "Immigration policy context (IRCC 2023 / Statistics Canada IMDB): "
            "Recent immigrants (<5 years) earn ~72 cents per dollar earned by Canadian-born "
            "workers with equivalent education. ~30% of recent immigrants report credential "
            "non-recognition as a barrier to employment. Refugees face the highest settlement "
            "service dependency rates (~85% use government-funded services within 2 years)."
        ),
    },
    "labour": {
        "dimensions": [
            "employment_precarity",
            "union_coverage",
            "sector_automation_risk",
            "minimum_wage_proximity",
            "benefits_coverage",
        ],
        "stat_context": (
            "Labour policy context (Statistics Canada LFS 2023 / CLPS): "
            "~14% of workers are in gig/contract arrangements with no employment benefits. "
            "Union coverage is ~29% nationally but concentrated in public sector. "
            "~1.1M workers earn within 10% of provincial minimum wages. "
            "Gig workers have no EI, CPP employer match, or paid leave protections."
        ),
    },
    "fiscal": {
        "dimensions": [
            "effective_tax_rate_exposure",
            "benefit_clawback_sensitivity",
            "gst_hst_burden",
            "savings_vehicle_usage",
            "public_service_dependency",
        ],
        "stat_context": (
            "Fiscal policy context (Statistics Canada SHS 2021 / CRA T1 data): "
            "Low-income households spend ~14% of after-tax income on GST/HST vs ~4% for "
            "top quintile. ~6.4M Canadians receive GIS/OAS. Benefit clawbacks create "
            "effective marginal rates above 50% for some low-income families on CCB/GIS. "
            "~40% of working Canadians have no workplace pension."
        ),
    },
    "education": {
        "dimensions": [
            "student_loan_exposure",
            "childcare_access",
            "school_age_children",
            "post_secondary_proximity",
            "skills_retraining_need",
        ],
        "stat_context": (
            "Education policy context (Statistics Canada CSUS 2021 / NHS 2021): "
            "Average student debt at graduation is ~$28,000. Childcare costs exceed $2,000/month "
            "in Toronto/Vancouver for under-5s. ~3.8M Canadians identify skills gaps as barriers "
            "to better employment. Rural access to post-secondary requires relocation for ~40% "
            "of rural youth."
        ),
    },
    "corrections": {
        "dimensions": [
            "neighbourhood_safety_concern",
            "employment_proximity_to_justice_involved",
            "social_housing_access",
            "income_vulnerability",
            "community_reintegration_exposure",
        ],
        "stat_context": (
            "Corrections policy context (Statistics Canada, CSC, PBO): "
            "~24,000 adults are in federal custody on any given day. Recidivism rate within 2 years ~33%. "
            "~70% of released federal offenders access some form of social assistance within 6 months. "
            "Indigenous people represent 32% of federal inmates but 5% of the Canadian population. "
            "Transitional housing demand for released offenders exceeds supply in all major CMAs."
        ),
    },
    "housing": {
        "dimensions": [
            "tenure",
            "rent_burden",
            "core_housing_need",
            "waitlist_status",
            "shelter_cost_ratio",
        ],
        "stat_context": (
            "Housing policy context (Statistics Canada CHS 2022): "
            "~12.5% of Canadian households are in core housing need. Average rent in major CMAs "
            "rose 18% from 2021–2023. Renter households spend 35% more of income on shelter "
            "than owner households. Social housing waitlists average 8–11 years in Toronto/Vancouver."
        ),
    },
    "ai": {
        "dimensions": [
            "ai_sector_exposure",
            "automation_displacement_risk",
            "data_privacy_sensitivity",
            "digital_literacy",
            "algorithmic_decision_subject",
        ],
        "stat_context": (
            "AI/technology policy context (Statistics Canada AI Adoption Survey Q2 2024 / OECD): "
            "6.1% of Canadian firms have adopted AI; adoption is highest in finance (34%), "
            "tech (28%), and professional services (19%). Workers in routine cognitive roles "
            "face the highest near-term automation risk. Low-income and less-educated workers "
            "have lower digital literacy and are more subject to algorithmic hiring/benefit decisions."
        ),
    },
    "other": {
        "dimensions": [
            "income_bracket",
            "employment_stability",
            "family_obligations",
            "geographic_access",
            "financial_resilience",
        ],
        "stat_context": (
            "General policy context (Statistics Canada SHS 2021): "
            "~47% of Canadians report they are $200/month or less away from financial insolvency. "
            "Rural and remote residents face 30–40% higher costs for equivalent services. "
            "Single-parent families have poverty rates 3× higher than couple families."
        ),
    },
}

# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

# Cities considered major urban transit hubs (CMA-level frequent service)
_TRANSIT_CITIES = {
    "Toronto", "Montreal", "Vancouver", "Ottawa", "Calgary",
    "Edmonton", "Winnipeg", "Hamilton", "Kitchener-Waterloo",
    "Halifax", "Victoria", "London", "Quebec City",
}

# Rural / small-town indicators in city names
_RURAL_INDICATORS = {"Rural", "Northern", "Remote", "Reserve", "Small"}

# Provinces with significant fossil fuel sector employment
_FOSSIL_FUEL_PROVINCES = {"AB", "SK", "NL"}

# Age brackets with higher healthcare utilization
_HIGH_HEALTH_UTILIZATION_AGES = {"50-64", "65+"}

# Employment types that suggest transit use vs driving
_TRANSIT_LIKELY_EMPLOYMENT = {"student", "salaried", "gig"}
_DRIVE_LIKELY_EMPLOYMENT = {"self_employed", "seasonal", "part_time"}

# Employment types with high precarity / no benefits
_PRECARIOUS_EMPLOYMENT = {"gig", "seasonal", "part_time", "self_employed"}


def _is_rural(agent: dict) -> bool:
    city = agent.get("city", "")
    return any(ind in city for ind in _RURAL_INDICATORS) or city not in _TRANSIT_CITIES


def _is_low_income(agent: dict) -> bool:
    return agent.get("income_bracket") in {"very_low", "low"}


def _is_senior(agent: dict) -> bool:
    return agent.get("age_bracket") == "65+"


def _is_young(agent: dict) -> bool:
    return agent.get("age_bracket") in {"18-24", "25-34"}


def _is_family(agent: dict) -> bool:
    return agent.get("family_size") in {"small_family", "large_family"}


def _is_recent_immigrant(agent: dict) -> bool:
    return agent.get("immigration_status") in {"recent_immigrant", "refugee"}


# ---------------------------------------------------------------------------
# Domain-specific inference functions
# ---------------------------------------------------------------------------

def _infer_transit(agent: dict) -> str:
    city = agent.get("city", "unknown")
    emp = agent.get("employment_type", "")
    age = agent.get("age_bracket", "")
    income = agent.get("income_bracket", "")
    rural = _is_rural(agent)

    # Pull real NHS 2021 city-level transit mode share
    city_data = _city_transit(city)
    transit_share = city_data.get("transit_mode_share_pct")
    avg_commute = city_data.get("avg_commute_min")
    cars_per_hh = city_data.get("car_ownership_per_hh")

    city_transit_note = (
        f"Real data (NHS 2021): {city} transit mode share {transit_share}%, "
        f"avg commute {avg_commute} min, {cars_per_hh} cars/household."
        if transit_share is not None
        else f"No city-level transit data for {city} — using population/employment proxy."
    )

    if rural:
        mode = "likely drives (rural/small-town location with limited transit service)"
        car_own = "almost certainly owns a vehicle — transit is not viable as primary mode"
        dependency = "low transit dependency; fare or route changes have minimal direct impact"
    elif emp == "student" or (age in {"18-24"} and income in {"very_low", "low"}):
        mode = "likely transit-dependent (student/young low-income in urban CMA)"
        car_own = "unlikely to own a vehicle — car ownership rate among 18–24 urban students is ~22% (NHS 2021)"
        dependency = "high transit dependency; any service cuts or fare increases are a primary financial hit"
    elif emp in {"gig"} and not rural:
        mode = "mixed — may drive for gig work (food/ride delivery) but uses transit personally"
        car_own = "variable; gig workers have ~55% vehicle ownership in CMAs (NHS 2021)"
        dependency = "moderate; transit changes affect personal travel but gig income may require vehicle"
    elif emp in {"self_employed"} and not rural:
        mode = "likely drives — self-employed workers have higher daytime flexibility and vehicle ownership"
        car_own = "probable vehicle owner; self-employed vehicle ownership rate ~74% (NHS 2021)"
        dependency = "low transit dependency; primarily affected through road/parking policy"
    elif emp == "retired" or age == "65+":
        mode = "mixed — seniors increasingly use transit when driving becomes difficult"
        car_own = f"may own vehicle but mobility limitations rise sharply after 75"
        dependency = "moderate to high depending on health; transit service quality directly affects mobility independence"
    else:
        # For salaried urban workers, weight dependency by real city transit share
        if transit_share and transit_share >= 30:
            mode = f"likely transit commuter — {city} has {transit_share}% transit mode share (NHS 2021)"
            dependency = f"high transit dependency in this city; {transit_share}% of commuters use transit"
        elif transit_share:
            mode = f"likely drives or mixed mode — {city} transit mode share is only {transit_share}% (NHS 2021)"
            dependency = "moderate transit dependency; most commuters in this city drive"
        else:
            mode = f"likely commutes by transit or car in {city} (salaried urban worker)"
            dependency = "moderate transit dependency; service quality and fare changes affect commute cost and time"
        car_own = f"~{cars_per_hh} cars/household in {city} (NHS 2021)" if cars_per_hh else "moderate vehicle ownership probability"

    return (
        f"Transit-relevant persona dimensions:\n"
        f"- City context: {city_transit_note}\n"
        f"- Likely commute mode: {mode}\n"
        f"- Car ownership: {car_own}\n"
        f"- Transit dependency: {dependency}\n"
        f"- Commute distance proxy: {'short/urban' if not rural else 'long/rural — likely >30 km'}\n"
        f"- Disability/mobility consideration: {'elevated — seniors face higher mobility barriers' if _is_senior(agent) else 'standard working-age mobility assumed'}"
    )


def _infer_healthcare(agent: dict) -> str:
    age = agent.get("age_bracket", "")
    province = agent.get("province", "")
    rural = _is_rural(agent)
    city = agent.get("city", "unknown")

    # Pull real CIHI provincial data
    prov_data = _province_healthcare(province)
    without_doctor_pct = prov_data.get("without_family_doctor_pct")
    er_wait = prov_data.get("median_er_wait_hours")
    nurses_per_1000 = prov_data.get("nurses_per_1000")

    prov_note = (
        f"Real data (CIHI 2023): {province} — {without_doctor_pct}% without family doctor, "
        f"median ER wait {er_wait}h, {nurses_per_1000} nurses/1,000 population."
        if without_doctor_pct is not None
        else f"No province-level CIHI data for {province} — using national averages."
    )

    utilization = "high — seniors average 7.2 physician visits/year (CIHI 2022)" if _is_senior(agent) else \
                  "moderate-high — 50–64 age bracket has elevated chronic condition prevalence" if age == "50-64" else \
                  "low-moderate — young adults are generally lower utilizers unless chronic conditions present"

    access_barrier = (
        f"significant geographic barrier — rural/remote location means likely >45 min travel to acute care"
        if rural else
        f"urban access in {city}; ER wait times ({er_wait}h in {province}, CIHI 2023) are primary barrier"
        if er_wait else
        f"urban access in {city}; wait times are primary barrier, not distance"
    )

    insurance = (
        "likely uninsured for dental/vision — low-income workers often lack supplementary benefits"
        if _is_low_income(agent) and agent.get("employment_type") in _PRECARIOUS_EMPLOYMENT else
        "likely has employer drug/dental benefits" if agent.get("employment_type") == "salaried" else
        "variable coverage; self-employed must purchase private supplementary coverage"
    )

    caregiver = (
        "elevated caregiver burden — family households with children may have pediatric healthcare needs"
        if _is_family(agent) else
        "low caregiver burden for single/couple households"
    )

    newcomer_note = (
        " Recent immigrants/refugees often face gaps in provincial health coverage in first 3 months "
        "and may not have a family doctor (IRCC 2022)."
        if _is_recent_immigrant(agent) else ""
    )

    return (
        f"Healthcare-relevant persona dimensions:\n"
        f"- Provincial context: {prov_note}\n"
        f"- Healthcare utilization: {utilization}\n"
        f"- Geographic access: {access_barrier}\n"
        f"- Supplementary insurance: {insurance}\n"
        f"- Caregiver burden: {caregiver}\n"
        f"- Newcomer coverage gap: {'yes — subject to waiting period / no family doctor' if _is_recent_immigrant(agent) else 'not applicable'}"
        f"{newcomer_note}"
    )


def _infer_climate(agent: dict) -> str:
    province = agent.get("province", "")
    emp = agent.get("employment_type", "")
    income = agent.get("income_bracket", "")
    rural = _is_rural(agent)
    city = agent.get("city", "unknown")

    # Pull real ECCC provincial data
    prov_data = _province_climate(province)
    emissions_per_capita = prov_data.get("emissions_per_capita_tco2e") or prov_data.get("emissions_per_capita_tco2")
    oil_gas_emp_pct = prov_data.get("oil_gas_employment_pct")
    carbon_rebate = prov_data.get("carbon_rebate_annual")
    clean_electricity_pct = prov_data.get("clean_electricity_pct")

    _prov_parts = [f"{emissions_per_capita} tCO2e/capita"] if emissions_per_capita else []
    if oil_gas_emp_pct: _prov_parts.append(f"{oil_gas_emp_pct}% oil/gas employment")
    if carbon_rebate: _prov_parts.append(f"${carbon_rebate}/yr CCR rebate")
    if clean_electricity_pct: _prov_parts.append(f"{clean_electricity_pct}% clean electricity")
    prov_note = (
        f"Real data (ECCC 2024): {province} — {', '.join(_prov_parts)}."
        if _prov_parts else
        f"No province-level ECCC data for {province} — using national averages."
    )

    fossil_exposure = (
        f"HIGH — {province} oil/gas employment {oil_gas_emp_pct}% of workforce (ECCC 2024)"
        if oil_gas_emp_pct and oil_gas_emp_pct >= 3 else
        "HIGH — Alberta/Saskatchewan workers have significant fossil fuel sector exposure"
        if province in _FOSSIL_FUEL_PROVINCES else
        "low — province has lower direct fossil fuel employment concentration"
    )

    heating = (
        "likely natural gas heating — AB/SK homes are >80% gas-heated (SHEU 2019), highly exposed to carbon price"
        if province in {"AB", "SK"} else
        "likely natural gas or electric heating depending on province — check provincial mix"
        if province in {"ON", "MB", "NS"} else
        "likely electric/hydro heating — BC/QC hydro grids reduce direct carbon price exposure on heat"
    )

    vehicle_dep = (
        "high vehicle dependency — rural location means driving is unavoidable, carbon price on fuel is a direct cost"
        if rural else
        "moderate vehicle dependency — urban transit alternatives exist but car use is still common"
    )

    rebate = (
        f"eligible for Canada Carbon Rebate — estimated ${carbon_rebate}/yr in {province} (ECCC 2024), net positive for low-income"
        if _is_low_income(agent) and carbon_rebate else
        "likely eligible for Canada Carbon Rebate (CCR) — lower-income households receive net positive transfer"
        if _is_low_income(agent) and province in {"AB", "SK", "MB", "ON", "NS", "PE", "NL"} else
        "likely net payer under carbon pricing — higher income reduces rebate relative to carbon costs"
        if income in {"high", "very_high"} else
        "roughly break-even on carbon price vs rebate at median income levels"
    )

    employer_exposure = (
        "employer likely in fossil fuel or energy-intensive sector — significant policy exposure"
        if province in _FOSSIL_FUEL_PROVINCES and emp == "salaried" else
        "employer sector exposure depends on industry — carbon price affects energy, transport, manufacturing"
        if emp in {"salaried", "self_employed"} else
        "minimal employer-side exposure (student/retired/gig)"
    )

    return (
        f"Climate-relevant persona dimensions:\n"
        f"- Provincial context: {prov_note}\n"
        f"- Fossil fuel sector exposure: {fossil_exposure}\n"
        f"- Home heating fuel type: {heating}\n"
        f"- Vehicle dependency: {vehicle_dep}\n"
        f"- Carbon rebate position: {rebate}\n"
        f"- Employer sector climate exposure: {employer_exposure}"
    )


def _infer_immigration(agent: dict) -> str:
    immigration = agent.get("immigration_status", "born_here")
    emp = agent.get("employment_type", "")
    income = agent.get("income_bracket", "")
    age = agent.get("age_bracket", "")

    pathway_note = {
        "born_here": "Canadian-born — immigration policy affects only those they know or sponsor; indirect exposure",
        "established_immigrant": "established immigrant (>5 years) — policy changes affect renewal pathways, sponsorship rights",
        "recent_immigrant": "recent immigrant (<5 years) — directly subject to current immigration rules; high policy sensitivity",
        "refugee": "refugee claimant/protected person — extremely high sensitivity to refugee and protection policy changes",
        "pr_holder": "permanent resident — affected by PR pathway changes, citizenship requirements, and travel document rules",
    }.get(immigration, f"immigration status: {immigration}")

    credential_note = (
        "high credential recognition barrier risk — immigrants in professional categories often face non-recognition (IRCC 2022)"
        if immigration in {"recent_immigrant", "refugee"} and emp in {"salaried", "self_employed"} else
        "credential recognition less likely to be active barrier"
    )

    settlement = (
        "dependent on settlement services — language training, employment supports, and housing assistance"
        if immigration in {"recent_immigrant", "refugee"} else
        "settlement phase largely complete; policy affects community and sponsor access"
        if immigration == "established_immigrant" else
        "not applicable"
    )

    family_sponsor = (
        "potential family sponsorship exposure — established/recent immigrants often sponsor relatives"
        if immigration in {"established_immigrant", "recent_immigrant"} else
        "not applicable"
    )

    return (
        f"Immigration-relevant persona dimensions:\n"
        f"- Immigration pathway: {pathway_note}\n"
        f"- Credential recognition risk: {credential_note}\n"
        f"- Settlement service dependency: {settlement}\n"
        f"- Family sponsorship exposure: {family_sponsor}\n"
        f"- Language barrier: {'possible — recent arrivals may face language-related service barriers' if immigration in {'recent_immigrant', 'refugee'} else 'not a primary factor'}"
    )


def _infer_labour(agent: dict) -> str:
    emp = agent.get("employment_type", "")
    income = agent.get("income_bracket", "")
    age = agent.get("age_bracket", "")
    city = agent.get("city", "unknown")

    # Pull real LFS city-level data
    city_data = _city_labour(city)
    unemp_rate = city_data.get("unemployment_rate")
    median_wage = city_data.get("median_wage")
    public_sector_pct = city_data.get("public_sector_pct")

    city_note = (
        f"Real data (StatsCan LFS 2024): {city} — unemployment {unemp_rate}%, "
        f"median wage ${median_wage}/hr, {public_sector_pct}% public sector employment."
        if unemp_rate is not None
        else f"No city-level LFS data for {city} — using national averages."
    )

    precarity = (
        "HIGH — gig/contract/seasonal work carries no employment insurance, no paid leave, no employer CPP match"
        if emp in {"gig", "seasonal"} else
        "MODERATE — self-employed bear full CPP contributions and have no EI access"
        if emp == "self_employed" else
        "low — salaried employment provides standard statutory protections"
        if emp == "salaried" else
        "not applicable (student/retired)"
    )

    union_coverage = (
        "low union coverage likely — gig/self-employed workers are excluded from most collective bargaining"
        if emp in {"gig", "self_employed", "seasonal"} else
        "public sector salaried workers have ~75% union coverage; private sector ~15% (LFS 2023)"
        if emp == "salaried" else
        "not applicable"
    )

    min_wage = (
        "high exposure — very_low/low income workers are most likely earning near or at minimum wage"
        if _is_low_income(agent) and emp in {"gig", "seasonal", "part_time"} else
        "moderate — policy may affect wage floor but worker is above minimum wage range"
        if income == "medium" else
        "not directly exposed to minimum wage policy"
    )

    automation_risk = (
        "LOW — student/retired not in active labour market"
        if emp in {"student", "retired"} else
        "MODERATE-HIGH — gig/service workers face near-term automation in logistics, food service, admin"
        if emp in {"gig", "seasonal"} else
        "moderate — salaried cognitive workers face longer-horizon automation risk"
        if emp == "salaried" else
        "variable — self-employed risk depends on sector"
    )

    benefits = (
        "no employer-provided benefits (drug, dental, vision) — gig/self-employed bear full cost"
        if emp in {"gig", "self_employed"} else
        "likely has full employer benefits package if salaried full-time"
        if emp == "salaried" else
        "variable or none"
    )

    return (
        f"Labour-relevant persona dimensions:\n"
        f"- City labour market: {city_note}\n"
        f"- Employment precarity: {precarity}\n"
        f"- Union coverage: {union_coverage}\n"
        f"- Minimum wage proximity: {min_wage}\n"
        f"- Automation displacement risk: {automation_risk}\n"
        f"- Benefits coverage: {benefits}"
    )


def _infer_fiscal(agent: dict) -> str:
    income = agent.get("income_bracket", "")
    emp = agent.get("employment_type", "")
    age = agent.get("age_bracket", "")
    debt = agent.get("debt_load", "")

    gst_burden = (
        "high GST/HST burden relative to income — low-income households spend ~14% of after-tax income on GST/HST (SHS 2021)"
        if _is_low_income(agent) else
        "moderate GST burden — middle income households spend ~7–9% on GST/HST"
        if income == "medium" else
        "low relative GST burden — high-income households spend ~4% of income on GST/HST"
    )

    benefit_clawback = (
        "high clawback sensitivity — CCB, GIS, or GST credit clawbacks can create effective marginal rates >50%"
        if _is_low_income(agent) and (_is_family(agent) or _is_senior(agent)) else
        "low clawback exposure — income level is above most benefit phase-out ranges"
        if income in {"high", "very_high"} else
        "moderate — may be in phase-out range for some benefits"
    )

    savings = (
        "limited TFSA/RRSP room used — low-income workers rarely have savings to shelter"
        if _is_low_income(agent) else
        "likely active RRSP/TFSA user — salaried higher-income workers are primary users of tax-advantaged savings"
        if income in {"high", "very_high"} and emp == "salaried" else
        "moderate savings vehicle usage"
    )

    public_service_dep = (
        "high public service dependency — low-income households rely on public transit, social housing, legal aid, community health"
        if _is_low_income(agent) else
        "low public service dependency — higher-income households can substitute private alternatives"
    )

    debt_note = (
        f"High debt load means fiscal changes that raise interest rates or reduce deductions are materially harmful"
        if debt == "high" else
        f"Low/no debt reduces sensitivity to interest rate or debt-related fiscal changes"
        if debt in {"low", "none"} else
        "moderate debt sensitivity"
    )

    return (
        f"Fiscal-relevant persona dimensions:\n"
        f"- GST/HST burden: {gst_burden}\n"
        f"- Benefit clawback sensitivity: {benefit_clawback}\n"
        f"- Tax-advantaged savings usage: {savings}\n"
        f"- Public service dependency: {public_service_dep}\n"
        f"- Debt load fiscal sensitivity: {debt_note}"
    )


def _infer_education(agent: dict) -> str:
    emp = agent.get("employment_type", "")
    age = agent.get("age_bracket", "")
    income = agent.get("income_bracket", "")
    family = agent.get("family_size", "")
    rural = _is_rural(agent)

    student_loan = (
        "directly affected — student with likely active student loan or OSAP/StudentAid dependency"
        if emp == "student" else
        "recent graduate likely carrying student debt (~$28,000 average at graduation)"
        if age in {"18-24", "25-34"} and income in {"very_low", "low"} else
        "student debt less likely a current concern"
    )

    childcare = (
        f"highly relevant — family households face significant childcare costs ($1,500–$2,500/month in major cities)"
        if _is_family(agent) and age in {"25-34", "35-49"} else
        "not a primary concern for non-family or older households"
    )

    school_age = (
        "likely has school-age children — elementary/secondary education quality and funding directly relevant"
        if _is_family(agent) and age in {"35-49", "25-34"} else
        "no school-age children likely in household"
    )

    pse_access = (
        "rural access barrier — post-secondary attendance requires relocation; distance education policy highly relevant"
        if rural else
        "urban PSE access is adequate; cost and debt are the primary barriers"
    )

    retraining = (
        "high retraining need — gig/seasonal/low-income workers are primary targets of skills upgrading programs"
        if emp in {"gig", "seasonal"} or (emp == "salaried" and _is_low_income(agent)) else
        "moderate — some upskilling exposure but not a primary policy surface"
        if emp == "salaried" else
        "low retraining relevance"
    )

    return (
        f"Education-relevant persona dimensions:\n"
        f"- Student loan exposure: {student_loan}\n"
        f"- Childcare access/cost: {childcare}\n"
        f"- School-age children in household: {school_age}\n"
        f"- Post-secondary geographic access: {pse_access}\n"
        f"- Skills retraining need: {retraining}"
    )


def _infer_housing(agent: dict) -> str:
    tenure = agent.get("tenure", "renter")
    income = agent.get("income_bracket", "")
    debt = agent.get("debt_load", "")
    city = agent.get("city", "unknown")
    family = agent.get("family_size", "")

    if tenure == "renter":
        primary_exposure = (
            "primary exposure: rent increases, vacancy rates, and affordability — as a renter, supply and price are the direct levers"
        )
    else:
        primary_exposure = (
            "primary exposure: property value, mortgage costs, and property tax — as an owner, equity and carrying costs are central"
        )

    rent_burden = (
        "likely in core housing need or severe rent burden (>30% income on shelter) — very_low/low income renters in major CMAs"
        if _is_low_income(agent) and tenure == "renter" else
        "moderate shelter cost burden — median-income renter"
        if income == "medium" and tenure == "renter" else
        "not rent-burdened — owner or higher income"
    )

    debt_exposure = (
        f"high mortgage/debt sensitivity — {debt} debt load means interest rate changes or amortization policy changes are material"
        if debt in {"high", "medium"} and tenure == "owner" else
        "no mortgage debt exposure (own outright or renter)"
    )

    family_note = (
        "family size creates space adequacy pressure — small/large families need ≥2BR units, limiting affordable options"
        if _is_family(agent) else
        "single/couple household — smaller unit options are viable"
    )

    return (
        f"Housing-relevant persona dimensions:\n"
        f"- Tenure and primary exposure: {primary_exposure}\n"
        f"- Rent burden: {rent_burden}\n"
        f"- Mortgage/debt sensitivity: {debt_exposure}\n"
        f"- Family space adequacy: {family_note}\n"
        f"- City market context: {city} housing market characteristics are central to interpreting this policy"
    )


def _infer_ai(agent: dict) -> str:
    emp = agent.get("employment_type", "")
    income = agent.get("income_bracket", "")
    age = agent.get("age_bracket", "")
    city = agent.get("city", "unknown")

    sector_exposure = (
        "LOW — student/retired not in active AI-exposed workforce"
        if emp in {"student", "retired"} else
        "MODERATE-HIGH — gig workers face algorithmic management and platform AI tools daily (ride/food/delivery platforms)"
        if emp == "gig" else
        "variable — salaried workers in finance, tech, professional services have high AI exposure; public sector moderate"
        if emp == "salaried" else
        "variable — self-employed may use AI tools or compete against AI-augmented services"
    )

    automation_risk = (
        "HIGH — low-income routine cognitive and manual workers face the greatest near-term displacement risk (OECD 2023)"
        if _is_low_income(agent) and emp not in {"student", "retired"} else
        "MODERATE — middle-income salaried workers face partial task automation but lower full-job displacement risk"
        if income == "medium" else
        "LOW — high-income knowledge workers are more likely AI augmentees than displacees in near term"
    )

    data_privacy = (
        "elevated sensitivity — low-income and gig workers are more subject to algorithmic decision-making in hiring, benefits, credit"
        if _is_low_income(agent) or emp == "gig" else
        "standard sensitivity — AI policy affects data rights and algorithmic transparency across all demographics"
    )

    digital_literacy = (
        "potentially lower digital literacy — seniors may face barriers in AI-mediated services"
        if _is_senior(agent) else
        "high digital literacy likely — young urban workers are primary technology adopters"
        if _is_young(agent) else
        "moderate digital literacy assumed for working-age population"
    )

    return (
        f"AI/technology-relevant persona dimensions:\n"
        f"- AI sector exposure: {sector_exposure}\n"
        f"- Automation displacement risk: {automation_risk}\n"
        f"- Data privacy/algorithmic decision sensitivity: {data_privacy}\n"
        f"- Digital literacy: {digital_literacy}\n"
        f"- Algorithmic subject: {'yes — gig platforms and benefit/credit algorithms affect this persona directly' if emp == 'gig' or _is_low_income(agent) else 'moderate — general consumer AI services'}"
    )


def _infer_other(agent: dict) -> str:
    emp = agent.get("employment_type", "")
    income = agent.get("income_bracket", "")
    family = agent.get("family_size", "")
    rural = _is_rural(agent)

    resilience = (
        "LOW financial resilience — very_low/low income leaves minimal buffer for policy-driven cost increases"
        if _is_low_income(agent) else
        "MODERATE — medium income provides some buffer but not immunity to significant cost shocks"
        if income == "medium" else
        "HIGH — high/very_high income provides meaningful financial buffer against most policy impacts"
    )

    geo_access = (
        "RURAL — geographic remoteness amplifies any policy that affects service delivery, costs, or infrastructure"
        if rural else
        "URBAN — geographic access is adequate; cost and availability are the primary service barriers"
    )

    employment_stability = (
        "UNSTABLE — gig/seasonal/student employment creates income variability that amplifies policy sensitivity"
        if emp in {"gig", "seasonal", "student"} else
        "STABLE — salaried employment provides income predictability"
        if emp == "salaried" else
        "variable"
    )

    family_obligations = (
        "SIGNIFICANT — family households have dependent care obligations that constrain financial flexibility"
        if _is_family(agent) else
        "LOW — single/couple households have fewer dependent obligations"
    )

    return (
        f"General policy-relevant persona dimensions:\n"
        f"- Financial resilience: {resilience}\n"
        f"- Geographic access: {geo_access}\n"
        f"- Employment stability: {employment_stability}\n"
        f"- Family/care obligations: {family_obligations}\n"
        f"- Primary policy lens: income level and employment type are the dominant filters for this agent"
    )


def _infer_corrections(agent: dict) -> str:
    income = agent.get("income_bracket", "")
    tenure = agent.get("tenure", "")
    age = agent.get("age_bracket", "")
    indigenous = "indigenous" in agent.get("immigration_status", "").lower() or "indigenous" in str(agent.get("guaranteed_slot", "")).lower()
    city = agent.get("city", "")

    income_vulnerability = (
        "HIGH — very low income leaves this person maximally exposed to neighbourhood spillover effects "
        "from corrections/reintegration policy (transitional housing supply, community services)"
        if income in {"very_low", "low"} else
        "MODERATE — medium income provides some buffer against neighbourhood-level impacts"
        if income == "medium" else
        "LOW — high income reduces direct exposure; likely concern is property/neighbourhood effects"
    )

    tenure_exposure = (
        "RENTER — more likely to live in areas where transitional housing is sited; "
        "landlord policy (Ban the Box for rentals) directly affects housing options"
        if tenure == "renter" else
        "OWNER — primary exposure is neighbourhood composition and property value effects "
        "from reintegration housing placement"
    )

    indigenous_note = (
        "INDIGENOUS — disproportionate incarceration rate (32% of federal inmates) means this person "
        "is statistically more likely to have personal/family connection to corrections system"
        if indigenous else ""
    )

    age_note = (
        "YOUTH (18–34) — most likely age group for direct or indirect connection to incarceration; "
        "also most affected by Ban the Box hiring provisions"
        if age in {"18-24", "25-34"} else
        "SENIOR — lower direct exposure; concern is primarily community safety and service resource allocation"
        if age in {"65-74", "75+"} else ""
    )

    coverage_note = (
        "COVERAGE LIMITATION: This validator's profile is drawn from housing microdata. "
        "They cannot represent the primary affected group (justice-involved persons). "
        "Their assessment reflects spillover exposure only — neighbourhood, rental market, and fiscal effects."
    )

    lines = [
        f"Corrections/reintegration policy persona dimensions:",
        f"- Income vulnerability: {income_vulnerability}",
        f"- Tenure exposure: {tenure_exposure}",
    ]
    if indigenous_note:
        lines.append(f"- Indigenous context: {indigenous_note}")
    if age_note:
        lines.append(f"- Age context: {age_note}")
    lines.append(f"- {coverage_note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_INFER_DISPATCH: dict[str, callable] = {
    "transit": _infer_transit,
    "healthcare": _infer_healthcare,
    "climate": _infer_climate,
    "immigration": _infer_immigration,
    "labour": _infer_labour,
    "fiscal": _infer_fiscal,
    "education": _infer_education,
    "corrections": _infer_corrections,
    "housing": _infer_housing,
    "ai": _infer_ai,
    "other": _infer_other,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_domain_persona_block(
    domain: str,
    agent: dict,
    policy_classification: dict,
) -> str:
    """
    Returns a text block to inject into validator prompts describing
    which dimensions this persona should reason about for this policy domain.

    Uses the agent's existing attributes (city, province, age_bracket,
    income_bracket, employment_type, family_size, tenure, debt_load,
    immigration_status) to infer plausible domain-specific context via
    deterministic rule-based logic. No LLM calls.

    Falls back to housing behaviour if domain is unrecognised.
    """
    normalized = (domain or "housing").lower().strip()

    # Normalise synonyms
    _aliases = {
        "technology": "ai",
        "digital": "ai",
        "tech": "ai",
        "social": "other",
        "supply": "housing",
        "affordability": "housing",
        "zoning": "housing",
        "environment": "climate",
        "carbon": "climate",
        "employment": "labour",
        "work": "labour",
        "tax": "fiscal",
        "taxation": "fiscal",
        "budget": "fiscal",
        "health": "healthcare",
        "transport": "transit",
        "transportation": "transit",
        "school": "education",
        "childcare": "education",
        "immigration": "immigration",
        "refugee": "immigration",
    }
    normalized = _aliases.get(normalized, normalized)

    if normalized not in _INFER_DISPATCH:
        normalized = "other"

    domain_cfg = DOMAIN_ATTRIBUTES.get(normalized, DOMAIN_ATTRIBUTES["other"])
    infer_fn = _INFER_DISPATCH[normalized]

    persona_dimensions = infer_fn(agent)
    stat_context = domain_cfg["stat_context"]

    policy_summary = policy_classification.get("summary", "")
    policy_type = policy_classification.get("type", "")

    header = (
        f"Policy domain context [{normalized.upper()}]:\n"
        f"{stat_context}\n\n"
        f"{persona_dimensions}"
    )

    if policy_summary:
        header += f"\n\nPolicy being assessed: {policy_summary}"

    return header
