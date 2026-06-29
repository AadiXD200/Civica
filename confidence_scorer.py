DOMAIN_DATA_FIELDS = {
    "housing":     "avg_rent_1br",
    "transit":     "transit_mode_share_pct",
    "healthcare":  "unemployment_rate",
    "climate":     "unemployment_rate",
    "labour":      "unemployment_rate",
    "fiscal":      "median_household_income",
    "education":   "median_household_income",
    "immigration": "unemployment_rate",
    "ai":          "unemployment_rate",
    "corrections": "unemployment_rate",
    "other":       "unemployment_rate",
}

DOMAIN_DATA_QUALITY = {
    "housing":     "pass",   # richest StatsCan/CMHC data
    "transit":     "pass",   # NHS 2021 mode share data available
    "labour":      "pass",   # LFS data available by CMA
    "climate":     "warn",   # provincial-level only
    "healthcare":  "warn",   # CIHI provincial only
    "fiscal":      "warn",   # national aggregates
    "immigration": "warn",   # IMDB has gaps
    "education":   "warn",   # partial CMA coverage
    "ai":          "warn",   # limited StatsCan coverage
    "corrections": "warn",   # CSC/Correctional Investigator aggregate data only
    "other":       "warn",
}


def calculate_confidence(
    policy_classification: dict,
    city_profiles: dict,
    specialist_results: list,
    validator_results: list,
    domain: str = "housing",
) -> dict:
    """
    Calculates simulation confidence score with a structured breakdown.
    Zero runtime cost — pure math over existing results.
    """
    checks = []
    score = 0
    max_score = 0

    # ── Data coverage ─────────────────────────────────────────────────────────

    # Use the domain-appropriate field to assess city data coverage
    domain_field = DOMAIN_DATA_FIELDS.get(domain, "unemployment_rate")
    cities_with_data = sum(1 for v in city_profiles.values() if v.get(domain_field))
    total_cities = len(city_profiles)
    max_score += 2
    if cities_with_data >= 18:
        score += 2
        checks.append({"status": "pass", "label": f"City data coverage: {cities_with_data}/{total_cities} cities have full StatsCan data ({domain_field})"})
    elif cities_with_data >= 12:
        score += 1
        checks.append({"status": "warn", "label": f"Partial city data: {cities_with_data}/{total_cities} cities have StatsCan data ({domain_field})"})
    else:
        checks.append({"status": "fail", "label": f"Thin city data: only {cities_with_data}/{total_cities} cities have StatsCan data ({domain_field})"})

    domain_quality = DOMAIN_DATA_QUALITY.get(domain, "warn")
    max_score += 1
    if domain_quality == "pass":
        score += 1
        checks.append({"status": "pass", "label": f"Policy domain: {domain} — strong StatsCan data coverage available"})
    else:
        checks.append({"status": "warn", "label": f"Policy domain: {domain} — StatsCan data coverage is partial for this domain (provincial or aggregate level only)"})

    # ── Specialist signal ─────────────────────────────────────────────────────

    specialists_responded = len([sr for sr in specialist_results if sr.get("risks")])
    total_specialists = len(specialist_results)
    max_score += 2
    if specialists_responded >= 7:
        score += 2
        checks.append({"status": "pass", "label": f"Specialist coverage: {specialists_responded}/{total_specialists} specialists returned findings"})
    elif specialists_responded >= 5:
        score += 1
        checks.append({"status": "warn", "label": f"Partial specialist coverage: {specialists_responded}/{total_specialists} specialists returned findings"})
    else:
        checks.append({"status": "fail", "label": f"Low specialist coverage: only {specialists_responded}/{total_specialists} specialists returned findings"})

    total_risks = sum(len(sr.get("risks", [])) for sr in specialist_results)
    max_score += 1
    if total_risks >= 8:
        score += 1
        checks.append({"status": "pass", "label": f"Risk diversity: {total_risks} risks identified across specialist domains"})
    elif total_risks >= 4:
        score += 1
        checks.append({"status": "warn", "label": f"Moderate risk signal: {total_risks} risks identified (more detail may improve accuracy)"})
    else:
        checks.append({"status": "fail", "label": f"Weak risk signal: only {total_risks} risks identified by specialists"})

    # Check if risks span multiple categories (not all from one domain)
    categories = set()
    for sr in specialist_results:
        for r in sr.get("risks", []):
            categories.add(r.get("category"))
    categories.discard("none")
    max_score += 1
    if len(categories) >= 4:
        score += 1
        checks.append({"status": "pass", "label": f"Specialist agreement: risks identified across {len(categories)} independent domains"})
    else:
        checks.append({"status": "warn", "label": f"Narrow specialist signal: risks concentrated in {len(categories)} domain(s) — consider policy scope"})

    # ── Validator confirmation ────────────────────────────────────────────────

    validators_responded = len([v for v in validator_results if v.get("validations")])
    total_validators = len(validator_results)
    no_response = total_validators - validators_responded
    max_score += 2
    if no_response == 0:
        score += 2
        checks.append({"status": "pass", "label": f"Validator response: all {total_validators} demographic agents responded"})
    elif no_response <= 3:
        score += 1
        checks.append({"status": "warn", "label": f"Near-full validator response: {validators_responded}/{total_validators} agents responded"})
    else:
        checks.append({"status": "fail", "label": f"Low validator response: only {validators_responded}/{total_validators} agents responded"})

    validators_confirming = sum(
        1 for v in validator_results
        if any(val.get("applies") for val in v.get("validations", []))
    )
    max_score += 2
    if validators_confirming >= 30:
        score += 2
        checks.append({"status": "pass", "label": f"Demographic confirmation: {validators_confirming}/{total_validators} validators confirmed at least one risk"})
    elif validators_confirming >= 15:
        score += 1
        checks.append({"status": "warn", "label": f"Moderate demographic confirmation: {validators_confirming}/{total_validators} validators confirmed risks"})
    else:
        checks.append({"status": "fail", "label": f"Low demographic confirmation: only {validators_confirming}/{total_validators} validators confirmed any risk"})

    risk_counts = [len(v.get("validations", [])) for v in validator_results if v.get("validations")]
    if risk_counts:
        min_risks = min(risk_counts)
        max_risks = max(risk_counts)
        if max_risks - min_risks > 2:
            checks.append({"status": "info", "label": f"Validator scope variance: validators assessed {min_risks}–{max_risks} risks (geographic scoping excluded out-of-area validators from some risks)"})

    # ── Demographic diversity of confirmations ────────────────────────────────

    confirming_validators = [
        v for v in validator_results
        if any(val.get("applies") for val in v.get("validations", []))
    ]
    tenures_confirming = {v["tenure"] for v in confirming_validators if v.get("tenure")}
    cities_confirming = {v["city"] for v in confirming_validators if v.get("city")}
    max_score += 1
    if len(tenures_confirming) >= 2 and len(cities_confirming) >= 5:
        score += 1
        checks.append({"status": "pass", "label": f"Confirmation diversity: risks confirmed across {len(cities_confirming)} cities and both tenure types"})
    elif len(cities_confirming) >= 3:
        checks.append({"status": "warn", "label": f"Moderate confirmation diversity: {len(cities_confirming)} cities represented in confirmations"})
    else:
        checks.append({"status": "warn", "label": "Low geographic diversity in confirmations — findings may be city-specific"})

    # ── Blind spots (scored — real gaps deduct from confidence) ──────────────

    # Indigenous / remote representation
    indigenous_validators = [
        v for v in validator_results
        if "Reserve" in v.get("city", "") or "Nunavut" in v.get("city", "")
    ]
    indigenous_confirmed = any(
        any(val.get("applies") for val in v.get("validations", []))
        for v in indigenous_validators
    )
    max_score += 1
    if indigenous_confirmed:
        score += 1
        checks.append({"status": "pass", "label": f"Indigenous & remote representation: validators from {len(indigenous_validators)} remote/reserve communities confirmed risks"})
    else:
        checks.append({"status": "fail", "label": "Blind spot: Indigenous and remote community validators confirmed no risks — findings may not reflect the most housing-vulnerable Canadians"})

    # Rural coverage — policies with geography != rural should still have rural validators responding
    rural_validators = [
        v for v in validator_results
        if any(kw in v.get("city", "") for kw in ["Rural", "Remote", "Reserve", "Nunavut", "PEI", "Northern"])
    ]
    rural_confirming = sum(
        1 for v in rural_validators
        if any(val.get("applies") for val in v.get("validations", []))
    )
    max_score += 1
    rural_rate = rural_confirming / max(len(rural_validators), 1)
    if rural_rate >= 0.5:
        score += 1
        checks.append({"status": "pass", "label": f"Rural coverage: {rural_confirming}/{len(rural_validators)} rural/remote validators confirmed risks"})
    elif rural_rate > 0:
        checks.append({"status": "warn", "label": f"Partial rural coverage: only {rural_confirming}/{len(rural_validators)} rural/remote validators confirmed risks"})
    else:
        checks.append({"status": "fail", "label": f"Rural blind spot: none of the {len(rural_validators)} rural/remote validators confirmed any risk — policy may structurally exclude these communities"})

    # ── Persona calibration coverage ─────────────────────────────────────────

    calibrated = sum(
        1 for v in validator_results
        if v.get("behavioral_profile") and v["behavioral_profile"].get("financial_fragility")
    )
    max_score += 1
    if calibrated >= 45:
        score += 1
        checks.append({"status": "pass", "label": f"Persona calibration: {calibrated}/{total_validators} validators grounded in CHS 2022 microdata profiles"})
    elif calibrated >= 25:
        score += 1
        checks.append({"status": "warn", "label": f"Partial persona calibration: {calibrated}/{total_validators} validators had microdata-grounded profiles"})
    else:
        checks.append({"status": "warn", "label": f"Low persona calibration: only {calibrated}/{total_validators} validators had microdata profiles — persona layer may not have run"})

    # ── Primary population coverage ──────────────────────────────────────────
    # For non-housing domains, check whether domain-injected personas are present.
    # A panel of 50 housing-tenure validators measuring spillover effects on a corrections
    # or healthcare policy cannot claim the same coverage quality as one with domain personas.
    _housing_domains = {"housing", "rent_control", "zoning", "supply", "tenant_protection", "environment"}
    _is_housing = domain.lower() in _housing_domains
    domain_persona_count = sum(1 for v in validator_results if v.get("domain_persona"))
    max_score += 1
    if _is_housing:
        score += 1
        checks.append({"status": "pass", "label": "Primary population coverage: housing domain — panel is drawn from the directly affected tenure population"})
    elif domain_persona_count >= 10:
        score += 1
        checks.append({"status": "pass", "label": f"Primary population coverage: {domain_persona_count}/50 domain-specific personas injected — primary affected group represented"})
    elif domain_persona_count > 0:
        checks.append({"status": "warn", "label": f"Partial primary population coverage: only {domain_persona_count}/50 domain-specific personas injected — panel skews toward housing-tenure bystanders, not primary affected group"})
    else:
        checks.append({"status": "fail", "label": f"Primary population gap: no domain-specific personas for this {domain} policy — panel measures housing-tenure spillover only, not effects on the primary affected group"})

    # ── Jurisdiction / feasibility ───────────────────────────────────────────
    # Flag when policy appears to require provincial cooperation.
    # This is a WARN-only check (no max_score contribution) — it doesn't reduce
    # confidence mechanically, but surfaces the gap for the analyst.
    _JURISDICTION_CRITICAL_DOMAINS_CS = {
        "housing", "healthcare", "transit", "education", "labour", "immigration",
    }
    _JURISDICTION_TRIGGERS_CS = [
        "provincial", "health authority", "federal-provincial", "opt-out", "opt out",
        "canada health act", "hospital", "school board", "municipal", "crown land",
        "section 92", "natural resources",
    ]
    if domain in _JURISDICTION_CRITICAL_DOMAINS_CS:
        # Infer policy text from specialist findings (we don't have direct access here)
        # Check if the Policy Critic raised jurisdiction concerns in their analysis
        critic_raised_jurisdiction = False
        for sr in specialist_results:
            if sr.get("specialist") in ("policy_critic", "Policy Critic"):
                analysis = (sr.get("analysis") or "").lower()
                if any(t in analysis for t in ["provincial", "jurisdiction", "federal-provincial", "opt-out", "opt out", "province refuse"]):
                    critic_raised_jurisdiction = True
                    break
        if critic_raised_jurisdiction:
            checks.append({"status": "warn", "label": f"Jurisdiction risk: Policy Critic identified federal-provincial boundary issues for this {domain} policy — provincial opt-out or non-cooperation could reduce effective coverage"})
        else:
            checks.append({"status": "info", "label": f"Jurisdiction note: {domain} policies often require provincial cooperation — confirm Policy Critic assessment covered this dimension"})

    # ── Demographic tension detection ─────────────────────────────────────────

    fragile_high = sum(
        1 for v in validator_results
        if v.get("behavioral_profile", {}).get("financial_fragility") == "high"
    )
    if fragile_high > 0:
        checks.append({"status": "info", "label": f"Vulnerability signal: {fragile_high} validators flagged as high financial fragility by CHS microdata"})

    # ── Prior outcome data ────────────────────────────────────────────────────

    checks.append({"status": "info", "label": "No prior outcome data for this policy type yet — forward validation pending"})

    # ── Final score ───────────────────────────────────────────────────────────

    # Deduct 0.5 per WARN, 1.0 per FAIL — FAILs represent structural gaps that
    # cannot be partially compensated by other passing checks.
    warn_deductions = sum(0.5 for c in checks if c["status"] == "warn")
    fail_deductions = sum(1.0 for c in checks if c["status"] == "fail")
    score = max(0, score - warn_deductions - fail_deductions)

    final_score = round(max(1, min(max_score, score)))
    pct = final_score / max_score

    if pct >= 0.80:
        summary = "High confidence — strong data coverage, full specialist and validator participation"
    elif pct >= 0.60:
        summary = "Moderate confidence — most checks passed, some data or coverage gaps"
    else:
        summary = "Lower confidence — significant gaps in data coverage or validator participation"

    return {
        "score": final_score,
        "out_of": max_score,
        "checks": checks,
        "summary": summary,
        "caveat": "This is a hypothesis generation tool. Findings should be validated against real survey data before informing policy decisions.",
        # Legacy fields kept for backward compatibility
        "reason": summary,
    }
