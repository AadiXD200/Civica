# pumf_matcher.py
"""
Matches each synthetic agent to real CHS 2022 microdata respondents
and returns weighted cohort statistics for that demographic slice.
"""

import os
import numpy as np
import pandas as pd

CHS_PATH = os.path.join(os.path.dirname(__file__), "2022", "Chs2022ecl_pumf.csv")

# Module-level cache
_pumf_df: pd.DataFrame | None = None
_pumf_loaded: bool = False

# Income bracket thresholds (based on survey_stats.json quintiles)
INCOME_THRESHOLDS = {
    "very_low":   (None, 27000),
    "low":        (27000, 48000),
    "medium":     (48000, 77500),
    "high":       (77500, 130000),
    "very_high":  (130000, None),
}

# age_bracket → PAGEP1 code
AGE_TO_PAGEP1 = {
    "18-24": 1,
    "25-34": 1,
    "35-49": 2,
    "50-64": 3,
    "65+":   4,
}

# province → REGION code
PROVINCE_TO_REGION = {
    "ON":  3,
    "PEI": 3,   # mapped alongside ON per spec
    "QC":  2,
    "BC":  5,
    "AB":  4,
    "SK":  4,
    "MB":  4,
    "NS":  1,
    "NB":  1,
    "NL":  1,
    "PE":  1,
}


# ── Weighted stat helpers ──────────────────────────────────────────────────────

def wpct(mask: pd.Series, weight: pd.Series, denom_mask: pd.Series | None = None) -> float | None:
    """Weighted percentage of rows matching mask, over denom_mask rows."""
    if denom_mask is None:
        denom_mask = pd.Series(True, index=mask.index)
    denom = weight[denom_mask].sum()
    if denom == 0:
        return None
    return round(100.0 * weight[mask & denom_mask].sum() / denom, 1)


def wmedian(series: pd.Series, weight: pd.Series) -> int | None:
    """Weighted median."""
    valid = series.notna()
    if valid.sum() == 0:
        return None
    s = series[valid]
    w = weight[valid]
    sorted_idx = s.argsort()
    s_sorted = s.iloc[sorted_idx]
    w_sorted = w.iloc[sorted_idx]
    cumw = w_sorted.cumsum() / w_sorted.sum()
    idx = (cumw >= 0.5).idxmax()
    return int(s_sorted[idx])


# ── Data loading ───────────────────────────────────────────────────────────────

def load_pumf() -> pd.DataFrame | None:
    """
    Loads the CHS 2022 PUMF CSV once and caches the result at the module level.
    Returns None if the file does not exist.
    """
    global _pumf_df, _pumf_loaded
    if _pumf_loaded:
        return _pumf_df

    _pumf_loaded = True

    if not os.path.exists(CHS_PATH):
        _pumf_df = None
        return None

    df = pd.read_csv(CHS_PATH)
    # Keep only households examined for core housing need (PCHN = 1 or 2)
    df = df[df["PCHN"].isin([1, 2])].copy()
    # Sentinel income → NaN
    df.loc[df["PHHTTINC"] >= 99_999_999_000, "PHHTTINC"] = None

    _pumf_df = df
    return df


# ── Filter building ────────────────────────────────────────────────────────────

def agent_to_pumf_filters(agent: dict) -> dict:
    """
    Maps agent fields to PUMF column filter specs.
    Returns a dict of {filter_name: callable(df) -> boolean mask}.
    """
    filters = {}

    # Age
    age_code = AGE_TO_PAGEP1.get(agent.get("age_bracket"))
    if age_code is not None:
        filters["age"] = lambda df, c=age_code: df["PAGEP1"] == c

    # Tenure
    tenure = agent.get("tenure")
    if tenure == "renter":
        filters["tenure"] = lambda df: df["PDCT_05"] == 2
    elif tenure == "owner":
        filters["tenure"] = lambda df: df["PDCT_05"] == 1

    # Income
    bracket = agent.get("income_bracket")
    if bracket in INCOME_THRESHOLDS:
        lo, hi = INCOME_THRESHOLDS[bracket]
        def income_filter(df, lo=lo, hi=hi):
            mask = df["PHHTTINC"].notna()
            if lo is not None:
                mask = mask & (df["PHHTTINC"] >= lo)
            if hi is not None:
                mask = mask & (df["PHHTTINC"] < hi)
            return mask
        filters["income"] = income_filter

    # Immigration status
    imm = agent.get("immigration_status", "")
    if imm in ("recent_immigrant", "established_immigrant", "refugee"):
        filters["immigration"] = lambda df: df["PRSPIMST"] == 2
    elif imm == "born_here":
        filters["immigration"] = lambda df: df["PRSPIMST"] == 1

    # Region
    province = agent.get("province", "")
    region_code = PROVINCE_TO_REGION.get(province)
    if region_code is not None:
        filters["region"] = lambda df, c=region_code: df["REGION"] == c

    return filters


# ── Cohort statistics ──────────────────────────────────────────────────────────

def _compute_stats(sub: pd.DataFrame, w: pd.Series, filters_applied: list[str]) -> dict:
    """Compute the full cohort stats dict for a filtered sub-DataFrame.

    PSTIR_GR in the PUMF is recoded to 3 groups for privacy protection:
      1 = shelter cost <30% of income (affordable)
      2 = shelter cost 30–99% of income (unaffordable by CMHC standard)
      3 = shelter cost ≥100% of income (spending entire income or more on shelter)
    Codes 4 and 5 from the full master file do not exist in the PUMF.
    """
    # Core housing need
    chn_pct = wpct(sub["PCHN"] == 1, w)

    # Shelter cost ≥30%: PSTIR_GR in {2, 3}
    stir_valid = sub["PSTIR_GR"].isin([1, 2, 3])
    shelter_30 = wpct(sub["PSTIR_GR"].isin([2, 3]), w, denom_mask=stir_valid)

    # Shelter cost ≥100% (entire income on shelter): PSTIR_GR == 3
    shelter_100 = wpct(sub["PSTIR_GR"] == 3, w, denom_mask=stir_valid)

    # Median household income
    med_inc = wmedian(sub["PHHTTINC"], w)

    # Dwelling issues: any of DWI_05A–D == 1
    any_issue = (
        (sub["DWI_05A"] == 1) |
        (sub["DWI_05B"] == 1) |
        (sub["DWI_05C"] == 1) |
        (sub["DWI_05D"] == 1)
    )
    dwelling_pct = wpct(any_issue, w)

    # Social/affordable housing
    sah_valid = sub["PDV_SAH"].isin([1, 2])
    social_pct = wpct(sub["PDV_SAH"] == 1, w, denom_mask=sah_valid)

    # On social housing waitlist
    wl_valid = sub["WSA_05"].isin([1, 2])
    waitlist_pct = wpct(sub["WSA_05"] == 1, w, denom_mask=wl_valid)

    # No employed person in household
    empl_valid = sub["PEMPL"].isin([1, 2])
    no_empl_pct = wpct(sub["PEMPL"] == 2, w, denom_mask=empl_valid)

    return {
        "n_matched_unweighted": len(sub),
        "n_matched_weighted": round(float(w.sum()), 1),
        "core_housing_need_pct": chn_pct,
        "shelter_cost_30pct_plus_pct": shelter_30,
        "shelter_cost_100pct_plus_pct": shelter_100,
        "median_household_income": med_inc,
        "dwelling_issues_pct": dwelling_pct,
        "social_housing_pct": social_pct,
        "on_waitlist_pct": waitlist_pct,
        "no_employment_pct": no_empl_pct,
        "filters_applied": filters_applied,
        "data_source": "CHS 2022 PUMF microdata — Statistics Canada",
    }


def get_cohort_stats(agent: dict) -> dict:
    """
    Returns weighted cohort statistics for the demographic slice matching agent.

    Applies filters progressively, relaxing from most-specific to least if the
    matched cohort is under 30 weighted records. Tenure is always kept.
    Returns {} if PUMF data is unavailable.
    """
    df = load_pumf()
    if df is None:
        return {}

    w = df["PFWEIGHT"]

    all_filters = agent_to_pumf_filters(agent)

    # Relaxation order: drop income first, then immigration, then region, then age.
    # Tenure is always kept.
    relaxation_order = ["income", "immigration", "region", "age"]

    # Start with all available filters
    active_filter_names = [f for f in ["age", "tenure", "income", "immigration", "region"] if f in all_filters]

    def apply_filters(names: list[str]) -> tuple[pd.DataFrame, pd.Series]:
        mask = pd.Series(True, index=df.index)
        for name in names:
            mask = mask & all_filters[name](df)
        sub = df[mask]
        return sub, w[mask]

    current_names = list(active_filter_names)

    # Try progressively relaxed filter sets
    for _ in range(len(relaxation_order) + 1):
        sub, sw = apply_filters(current_names)
        weighted_n = sw.sum()

        if weighted_n >= 30:
            return _compute_stats(sub, sw, list(current_names))

        # Find the next filter to drop (in relaxation order, skip tenure)
        dropped = False
        for fname in relaxation_order:
            if fname in current_names:
                current_names.remove(fname)
                dropped = True
                break

        if not dropped:
            break

    # Final attempt with whatever remains (could be just tenure or nothing)
    sub, sw = apply_filters(current_names)
    if sw.sum() >= 30:
        return _compute_stats(sub, sw, list(current_names))

    # Fall back to national averages
    return _compute_stats(df, w, [])
