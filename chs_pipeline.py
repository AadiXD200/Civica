"""
Parses the CHS 2022 PUMF microdata and outputs survey_stats.json —
demographic and regional housing need breakdowns that ground specialist agents.

Uses survey weights (PFWEIGHT) for all estimates so figures are representative
of Canadian households, not just the survey sample.

Usage:
    python chs_pipeline.py
Output:
    data/survey_stats.json
"""

import json
import os
import pandas as pd
import numpy as np

CHS_PATH = os.path.join(os.path.dirname(__file__), "2022", "Chs2022ecl_pumf.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "survey_stats.json")

# ── Code maps (from STATA label files + StatsCan CHS 2022 documentation) ─────

REGION_MAP = {
    1: "Atlantic",
    2: "Quebec",
    3: "Ontario",
    4: "Prairies",
    5: "British Columbia",
}

# PCHN: core housing need (derived variable)
# 1=In core housing need, 2=Not in core housing need, 3=Not examined, 6/9=N/A
CORE_NEED_YES = 1

# PSTIR_GR: shelter cost to income ratio group
# The PUMF recodes to 3 groups for privacy protection (master file has 5):
# 1=<30%, 2=30-99%, 3=≥100% (spending entire income or more on shelter), 9=not stated
STIR_MAP = {1: "<30%", 2: "30-99%", 3: "≥100%"}
UNAFFORDABLE_STIR = {2, 3}  # ≥30% = unaffordable by CMHC standard

# PAGEP1: age group of reference person
# 1=15-34, 2=35-54, 3=55-64, 4=65+
AGE_MAP = {1: "15-34", 2: "35-54", 3: "55-64", 4: "65+"}

# PRSPIMST: immigration status — 1=Non-immigrant, 2=Immigrant, 9=not stated
# PVISMIN: 1=Visible minority member present, 2=No visible minority, 9=not stated
# PEMPL: 1=At least one employed, 2=No employed person, 9=not stated
# PDCT_05: Tenure — 1=Yes (owned by household member), 2=No (renter), 6/9=N/A
OWNER_CODE = 1
RENTER_CODE = 2

# PDV_SAH: Social/affordable housing — 1=Yes, 2=No, 6=valid skip, 9=not stated
SAH_YES = 1


def wpct(mask, weight, denom_mask=None):
    """Weighted percentage of rows matching mask, over denom_mask rows."""
    if denom_mask is None:
        denom_mask = pd.Series(True, index=mask.index)
    denom = weight[denom_mask].sum()
    if denom == 0:
        return None
    return round(100 * weight[mask & denom_mask].sum() / denom, 1)


def wmedian(series, weight):
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


def load_data():
    df = pd.read_csv(CHS_PATH)
    # Keep only households examined for core housing need (PCHN=1 or 2)
    df = df[df["PCHN"].isin([1, 2])].copy()
    # Sentinel income (99999999999) → NaN
    df.loc[df["PHHTTINC"] >= 99999999000, "PHHTTINC"] = None
    w = df["PFWEIGHT"]
    return df, w


def stats_for(df, w):
    """Compute core housing stats for a subset of the dataframe."""
    # Core housing need rate
    chn = wpct(df["PCHN"] == CORE_NEED_YES, w)

    # Shelter cost ≥30% income rate (exclude not-stated)
    stir_valid = df["PSTIR_GR"].isin(STIR_MAP)
    unaffordable = wpct(
        df["PSTIR_GR"].isin(UNAFFORDABLE_STIR),
        w,
        denom_mask=stir_valid,
    )

    # Renter rate (PDCT_05=2 means not owned by household member)
    tenure_valid = df["PDCT_05"].isin([1, 2])
    renter_pct = wpct(df["PDCT_05"] == RENTER_CODE, w, denom_mask=tenure_valid)

    # Weighted median income
    med_inc = wmedian(df["PHHTTINC"], w)

    return {
        "n_unweighted": len(df),
        "core_housing_need_pct": chn,
        "shelter_cost_30pct_plus_pct": unaffordable,
        "renter_pct": renter_pct,
        "median_household_income": med_inc,
    }


def build_national_stats(df, w):
    base = stats_for(df, w)
    base["social_housing_pct"] = wpct(
        df["PDV_SAH"] == SAH_YES, w,
        denom_mask=df["PDV_SAH"].isin([1, 2])
    )
    base["dwelling_issues_pct"] = wpct(
        (df["DWI_05A"] == 1) | (df["DWI_05B"] == 1) |
        (df["DWI_05C"] == 1) | (df["DWI_05D"] == 1),
        w,
    )
    base["waitlist_social_housing_pct"] = wpct(
        df["WSA_05"] == 1, w,
        denom_mask=df["WSA_05"].isin([1, 2])
    )
    return base


def build_regional_stats(df, w):
    stats = {}
    for code, name in REGION_MAP.items():
        mask = df["REGION"] == code
        sub, sw = df[mask], w[mask]
        if len(sub) < 50:
            continue
        s = stats_for(sub, sw)
        s["dwelling_issues_pct"] = wpct(
            (sub["DWI_05A"] == 1) | (sub["DWI_05B"] == 1) |
            (sub["DWI_05C"] == 1) | (sub["DWI_05D"] == 1),
            sw,
        )
        stats[name] = s
    return stats


def build_demographic_stats(df, w):
    stats = {}

    # By age group
    age_stats = {}
    for code, label in AGE_MAP.items():
        mask = df["PAGEP1"] == code
        sub, sw = df[mask], w[mask]
        if len(sub) < 50:
            continue
        age_stats[label] = stats_for(sub, sw)
    stats["by_age"] = age_stats

    # Immigrants vs non-immigrants
    for label, code in [("immigrants", 2), ("non_immigrants", 1)]:
        mask = df["PRSPIMST"] == code
        sub, sw = df[mask], w[mask]
        stats[label] = stats_for(sub, sw)

    # Visible minority households
    for label, code in [("visible_minority_households", 1), ("non_visible_minority_households", 2)]:
        mask = df["PVISMIN"] == code
        sub, sw = df[mask], w[mask]
        stats[label] = stats_for(sub, sw)

    # Renters vs owners
    for label, code in [("renters", RENTER_CODE), ("owners", OWNER_CODE)]:
        mask = df["PDCT_05"] == code
        sub, sw = df[mask], w[mask]
        stats[label] = stats_for(sub, sw)

    # Households with no employed person
    mask = df["PEMPL"] == 2
    sub, sw = df[mask], w[mask]
    stats["no_employed_person"] = stats_for(sub, sw)

    return stats


def build_income_quintile_stats(df, w):
    """Core housing need and affordability by household income quintile."""
    valid_mask = df["PHHTTINC"].notna()
    sub = df[valid_mask].copy()
    sw = w[valid_mask]

    # Use weighted quantile cuts
    sub["income_quintile"] = pd.qcut(
        sub["PHHTTINC"], 5,
        labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"]
    )
    stats = {}
    for q in ["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"]:
        mask = sub["income_quintile"] == q
        qs, qw = sub[mask], sw[mask]
        s = stats_for(qs, qw)
        s["income_range"] = f"${int(qs['PHHTTINC'].min()):,}–${int(qs['PHHTTINC'].max()):,}"
        stats[q] = s
    return stats


def main():
    print("Loading CHS 2022 microdata...")
    df, w = load_data()
    print(f"  {len(df):,} households (after filtering to examined PCHN responses)")
    print(f"  Total weighted households: {w.sum():,.0f}")

    output = {
        "source": "Statistics Canada, Canadian Housing Survey (CHS) 2022, Public Use Microdata File",
        "citation": (
            "Statistics Canada. (2023). Canadian Housing Survey, 2022 "
            "[Public Use Microdata File]. Ottawa: Statistics Canada."
        ),
        "note": (
            "All percentages are survey-weighted (PFWEIGHT) and represent Canadian "
            "households, not the raw sample. Core housing need (PCHN) and shelter-cost-to-income "
            "ratio groups (PSTIR_GR) are Statistics Canada derived variables. "
            "Tenure from PDCT_05 (dwelling owned by household member). "
            "Excludes households not examined for core housing need (band housing, collective dwellings)."
        ),
        "national": build_national_stats(df, w),
        "by_region": build_regional_stats(df, w),
        "by_demographic": build_demographic_stats(df, w),
        "by_income_quintile": build_income_quintile_stats(df, w),
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWritten to {OUT_PATH}")

    nat = output["national"]
    print(f"\nNational snapshot (weighted, n_unweighted={nat['n_unweighted']:,}):")
    print(f"  Core housing need:         {nat['core_housing_need_pct']}%")
    print(f"  Shelter cost ≥30% income:  {nat['shelter_cost_30pct_plus_pct']}%")
    print(f"  Renter households:         {nat['renter_pct']}%")
    print(f"  Weighted median income:    ${nat['median_household_income']:,}")
    print(f"  Social housing:            {nat['social_housing_pct']}%")
    print(f"\nBy region:")
    for region, s in output["by_region"].items():
        print(f"  {region:<22} core need {s['core_housing_need_pct']}%  unaffordable {s['shelter_cost_30pct_plus_pct']}%  renters {s['renter_pct']}%")
    print(f"\nBy demographic:")
    dem = output["by_demographic"]
    print(f"  Immigrants:           core need {dem['immigrants']['core_housing_need_pct']}%  renters {dem['immigrants']['renter_pct']}%")
    print(f"  Non-immigrants:       core need {dem['non_immigrants']['core_housing_need_pct']}%  renters {dem['non_immigrants']['renter_pct']}%")
    print(f"  Visible minority HH:  core need {dem['visible_minority_households']['core_housing_need_pct']}%  renters {dem['visible_minority_households']['renter_pct']}%")
    print(f"  Renters:              core need {dem['renters']['core_housing_need_pct']}%")
    print(f"  No employment:        core need {dem['no_employed_person']['core_housing_need_pct']}%")
    print(f"\nBy income quintile:")
    for q, s in output["by_income_quintile"].items():
        print(f"  {q:<18} {s['income_range']:<25} core need {s['core_housing_need_pct']}%")


if __name__ == "__main__":
    main()
