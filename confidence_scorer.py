def calculate_confidence(
    policy_classification: dict,
    city_profiles: dict,
    specialist_results: list,
    validator_results: list
) -> dict:
    """
    Calculates simulation confidence score with a structured breakdown.
    Zero runtime cost — pure math over existing results.
    """
    checks = []
    score = 0
    max_score = 0

    # ── Data coverage ─────────────────────────────────────────────────────────

    cities_with_data = sum(1 for v in city_profiles.values() if v.get("avg_rent_1br"))
    total_cities = len(city_profiles)
    max_score += 2
    if cities_with_data >= 18:
        score += 2
        checks.append({"status": "pass", "label": f"City data coverage: {cities_with_data}/{total_cities} cities have full StatsCan data"})
    elif cities_with_data >= 12:
        score += 1
        checks.append({"status": "warn", "label": f"Partial city data: {cities_with_data}/{total_cities} cities have StatsCan data"})
    else:
        checks.append({"status": "fail", "label": f"Thin city data: only {cities_with_data}/{total_cities} cities have StatsCan data"})

    is_housing = policy_classification.get("market") != "non_housing"
    max_score += 1
    if is_housing:
        score += 1
        checks.append({"status": "pass", "label": "Policy type: housing/urban — strongest StatsCan data coverage"})
    else:
        checks.append({"status": "warn", "label": "Policy type: non-housing — StatsCan data coverage is thinner for this domain"})

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

    final_score = max(1, min(max_score, score))
    pct = final_score / max_score

    if pct >= 0.85:
        summary = "High confidence — strong data coverage, full specialist and validator participation"
    elif pct >= 0.65:
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
