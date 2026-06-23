"""
agent_generator.py

Generates 50 demographically representative Canadian household agents by
stratified weighted sampling from the Statistics Canada CHS 2022 PUMF
(Public Use Microdata File, 37,102 households).

Every agent attribute is derived from real survey data except:
  - city: PUMF has only 5 REGION codes; city assigned probabilistically
    within region using population weights.
  - immigration sub-category: PUMF gives immigrant/non-immigrant binary;
    recent/established/refugee sub-split uses age-based probabilities.
  - employment sub-category: PUMF gives employed/not binary; type inferred
    from age + education + income proxies.

Usage:
    python3 agent_generator.py          # generates + prints + caches
    from agent_generator import load_or_generate_agents
"""

import json
import os
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

PUMF_PATH  = os.path.join(os.path.dirname(__file__), "2022", "Chs2022ecl_pumf.csv")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "dynamic_agents.json")

# ── Vocabulary constants ───────────────────────────────────────────────────────

INCOME_THRESHOLDS = [0, 27_000, 48_000, 77_500, 130_000, float("inf")]
INCOME_LABELS     = ["very_low", "low", "medium", "high", "very_high"]

AGE_MAP = {1: "25-34", 2: "35-49", 3: "50-64", 4: "65+"}

REGION_TO_PROVINCE = {1: "NS", 2: "QC", 3: "ON", 4: "AB", 5: "BC"}

# Valid cities — must match keys in data/city_profiles.json + orchestrator CITY_NAME_MAP
VALID_CITIES = {
    "Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton",
    "Ottawa", "Winnipeg", "Hamilton", "Kitchener-Waterloo", "Halifax",
    "Victoria", "Saskatoon", "Regina", "Kelowna", "Sudbury",
    "Northern Ontario Rural", "Northern BC Rural", "PEI Rural",
    "Reserve Northern Ontario", "Nunavut Remote",
}

VALID_AGE_BRACKETS     = {"18-24", "25-34", "35-49", "50-64", "65+"}
VALID_INCOME_BRACKETS  = set(INCOME_LABELS)
VALID_TENURES          = {"renter", "owner"}
VALID_DEBT_LOADS       = {"none", "low", "medium", "high"}
VALID_FAMILY_SIZES     = {"single", "couple", "small_family", "large_family"}
VALID_EMPLOYMENT_TYPES = {"student", "salaried", "self_employed", "gig", "unemployed", "retired"}
VALID_IMMIGRATION      = {"born_here", "recent_immigrant", "established_immigrant", "refugee"}

# ── City assignment probabilities per REGION ──────────────────────────────────
# Each entry: (city_name, province_code, base_probability)
# Probabilities per region must sum to 1.0

CITY_ASSIGNMENTS: dict[int, list[tuple[str, str, float]]] = {
    1: [  # Atlantic
        ("Halifax",               "NS", 0.85),
        ("PEI Rural",             "PE", 0.15),
    ],
    2: [  # Quebec
        ("Montreal",              "QC", 1.00),
    ],
    3: [  # Ontario
        ("Toronto",               "ON", 0.42),
        ("Ottawa",                "ON", 0.15),
        ("Hamilton",              "ON", 0.10),
        ("Kitchener-Waterloo",    "ON", 0.10),
        ("Sudbury",               "ON", 0.08),
        ("Northern Ontario Rural","ON", 0.11),
        ("Reserve Northern Ontario","ON", 0.04),
    ],
    4: [  # Prairies
        ("Calgary",               "AB", 0.30),
        ("Edmonton",              "AB", 0.25),
        ("Saskatoon",             "SK", 0.20),
        ("Regina",                "SK", 0.15),
        ("Winnipeg",              "MB", 0.10),
    ],
    5: [  # British Columbia
        ("Vancouver",             "BC", 0.55),
        ("Victoria",              "BC", 0.20),
        ("Kelowna",               "BC", 0.15),
        ("Northern BC Rural",     "BC", 0.10),
    ],
}

# ── Data loading ───────────────────────────────────────────────────────────────

def _load_and_prepare_pumf() -> pd.DataFrame:
    """
    Loads CHS 2022 PUMF CSV, filters to examined households, cleans sentinel
    values, and derives working columns: income_quintile, age_bracket, family_size.
    """
    df = pd.read_csv(PUMF_PATH)

    # Keep only households examined for core housing need
    df = df[df["PCHN"].isin([1, 2])].copy()

    # Sentinel income → NaN
    df.loc[df["PHHTTINC"] >= 99_999_999_000, "PHHTTINC"] = None

    # Drop invalid tenure codes (~411 rows with code 9)
    df = df[df["PDCT_05"].isin([1, 2])].copy()

    # Derive income quintile (0–4); NaN income → 2 (medium)
    df["income_quintile"] = pd.cut(
        df["PHHTTINC"],
        bins=INCOME_THRESHOLDS,
        labels=False,
        right=False,
    ).fillna(2).astype(int)

    # Derive age_bracket from PAGEP1
    # Code 1 = 15–34: assign "18-24" if PHGEDUC ∈ {1,2} (no/some high school — student proxy)
    # else "25-34"
    def _age_bracket(row):
        code = row["PAGEP1"]
        if code == 1:
            return "18-24" if row["PHGEDUC"] in {1, 2} else "25-34"
        return AGE_MAP.get(code, "35-49")

    df["age_bracket"] = df.apply(_age_bracket, axis=1)

    # Derive family_size from PHHSIZE
    def _family_size(n):
        if n == 1:
            return "single"
        if n == 2:
            return "couple"
        if n in {3, 4}:
            return "small_family"
        if n >= 5:
            return "large_family"
        return "couple"  # 99 (not stated)

    df["family_size"] = df["PHHSIZE"].apply(_family_size)

    return df.reset_index(drop=True)


# ── Stratified weighted sampling ───────────────────────────────────────────────

def _largest_remainder(raw: dict, n: int) -> dict:
    """Allocates n slots to cells using the Largest Remainder Method."""
    floor = {k: int(v) for k, v in raw.items()}
    remainders = {k: raw[k] - floor[k] for k in raw}
    deficit = n - sum(floor.values())
    for k in sorted(remainders, key=lambda k: -remainders[k])[:deficit]:
        floor[k] += 1
    return floor


def _stratify_and_sample(
    df: pd.DataFrame,
    rng: np.random.Generator,
    n: int = 50,
) -> tuple[list[pd.Series], list[float]]:
    """
    Stratified weighted sampling across REGION × PDCT_05 × income_quintile × PAGEP1.

    Uses boosted weights to over-sample analytically important demographics
    (renters, low-income, young) while capping each cell at 2 slots and each
    region at 30% of total. The true CHS PFWEIGHT-based cell weight is preserved
    as population_weight for each agent.

    Returns (list_of_rows, list_of_cell_weights), one entry per agent slot.
    """
    w = df["PFWEIGHT"]

    # ── Build cell index ──────────────────────────────────────────────────────
    cells: dict[tuple, pd.Index] = {}
    for key, group in df.groupby(
        ["REGION", "PDCT_05", "income_quintile", "PAGEP1"], sort=False
    ):
        cells[key] = group.index

    sparse = {k for k, idx in cells.items() if len(idx) < 3}
    cell_weights = {k: float(w[idx].sum()) for k, idx in cells.items()}
    total_w = sum(cell_weights.values())

    # ── Compute boosted weights ───────────────────────────────────────────────
    # Boost multipliers make analytically important demographics more likely
    # to receive agent slots. The true cell_weight (PFWEIGHT sum) is preserved
    # as population_weight for each agent — boosting only affects sampling.
    CELL_MAX   = 2      # max agents per cell (prevents near-duplicates)
    REGION_MAX = int(n * 0.30)  # max agents per region (prevents Montreal monopoly)

    def _boost(region, tenure, iq, age) -> float:
        m = 1.0
        if tenure == 2:      m *= 2.5  # renters
        if iq in {0, 1}:     m *= 2.0  # low/very_low income
        if age == 1:         m *= 3.0  # young (15–34)
        if age == 2:         m *= 1.5  # 35–54
        if region == 1:      m *= 3.5  # Atlantic: tiny PUMF sample, needs boost
        if region == 5:      m *= 1.4  # BC: slightly under-sampled vs population
        return m

    boosted: dict[tuple, float] = {
        k: cell_weights[k] * _boost(*k)
        for k in cells
        if k not in sparse
    }

    # ── Largest Remainder on boosted weights, hard-capped at CELL_MAX ────────
    total_b = sum(boosted.values())
    raw_alloc = {k: min(bw / total_b * n, float(CELL_MAX)) for k, bw in boosted.items()}
    alloc: dict[tuple, int] = _largest_remainder(raw_alloc, n)

    # ── Enforce region cap (prevent one region dominating) ───────────────────
    for rc in [1, 2, 3, 4, 5]:
        rc_cells = [(k, alloc[k]) for k in alloc if k[0] == rc]
        rc_total = sum(v for _, v in rc_cells)
        if rc_total > REGION_MAX:
            excess = rc_total - REGION_MAX
            # Trim from lowest-boosted cells first
            for k, _ in sorted(rc_cells, key=lambda x: boosted.get(x[0], 0)):
                trim = min(alloc[k] - 1, excess)
                if trim > 0:
                    alloc[k] -= trim
                    excess -= trim
                if excess <= 0:
                    break

    # ── Guarantee every region has ≥ 2 agents ────────────────────────────────
    for rc in [1, 2, 3, 4, 5]:
        rc_total = sum(v for k, v in alloc.items() if k[0] == rc)
        deficit = max(0, 2 - rc_total)
        if deficit:
            candidates = sorted(
                [k for k in boosted if k[0] == rc and alloc.get(k, 0) < CELL_MAX],
                key=lambda k: -boosted[k],
            )
            added = 0
            for k in candidates:
                if added >= deficit:
                    break
                alloc[k] = alloc.get(k, 0) + 1
                added += 1
                # Steal from lowest-boosted cell in another over-represented region
                donors = sorted(
                    [(k2, alloc[k2]) for k2 in alloc if k2[0] != rc and alloc[k2] > 1],
                    key=lambda x: boosted.get(x[0], 0),
                )
                if donors:
                    alloc[donors[0][0]] -= 1

    # ── Fix total to exactly n ────────────────────────────────────────────────
    actual = sum(alloc.values())
    diff = n - actual
    if diff != 0:
        # Add/remove from highest/lowest-boosted cells with headroom/surplus
        sorted_by_boost = sorted(boosted, key=lambda k: -boosted[k])
        for k in sorted_by_boost:
            if diff == 0:
                break
            if diff > 0 and alloc.get(k, 0) < CELL_MAX:
                alloc[k] = alloc.get(k, 0) + 1
                diff -= 1
            elif diff < 0 and alloc.get(k, 0) > 1:
                alloc[k] -= 1
                diff += 1

    # ── Sample rows from allocated cells ─────────────────────────────────────
    def _nearest_cell(key: tuple) -> tuple | None:
        region, tenure, iq, age = key
        for iq2 in range(5):
            k2 = (region, tenure, iq2, age)
            if k2 != key and k2 in cells and k2 not in sparse:
                return k2
        for age2 in [2, 3, 1, 4]:
            k2 = (region, tenure, iq, age2)
            if k2 != key and k2 in cells and k2 not in sparse:
                return k2
        return None

    rows_out: list[pd.Series] = []
    weights_out: list[float] = []

    for key, slots in alloc.items():
        if slots <= 0:
            continue

        idx = cells.get(key)
        cw = cell_weights.get(key, 1.0)

        # Redirect sparse/missing cells to nearest valid cell
        if idx is None or key in sparse:
            alt = _nearest_cell(key)
            if alt:
                idx = cells[alt]
                cw = cell_weights[alt]
            else:
                continue

        cell_w_arr = w[idx].values.astype(float)
        cell_w_arr /= cell_w_arr.sum()

        replace = slots > len(idx)
        chosen = rng.choice(len(idx), size=slots, replace=replace, p=cell_w_arr)

        for ci in chosen:
            rows_out.append(df.loc[idx[ci]])
            weights_out.append(cw / slots)

    return rows_out, weights_out


# ── Field derivation helpers ───────────────────────────────────────────────────

def _derive_city(
    region: int,
    income_q: int,
    phtype: int,
    nunavut_taken: list[bool],
    rng: np.random.Generator,
) -> tuple[str, str]:
    """
    Maps REGION code + household characteristics to a city name and province.
    One Prairie very_low renter slot is redirected to "Nunavut Remote" (province NU).
    """
    # Nunavut override: one Prairie agent (region 4) with very low income
    # becomes Nunavut Remote (PUMF has no Nunavut code)
    if region == 4 and income_q == 0 and not nunavut_taken[0]:
        nunavut_taken[0] = True
        return "Nunavut Remote", "NU"

    options = CITY_ASSIGNMENTS[region]
    cities  = [c for c, p, w in options]
    provs   = [p for c, p, w in options]
    probs   = np.array([w for c, p, w in options], dtype=float)

    # Modest boost to rural cities for lower-income detached/semi households
    rural_indices = [
        i for i, c in enumerate(cities)
        if any(kw in c for kw in ["Rural", "Remote", "Reserve", "Northern"])
    ]
    if rural_indices and income_q in {0, 1} and phtype in {1, 2}:
        boost = 0.05
        probs[rural_indices] += boost / len(rural_indices)
        # Reduce largest-city share to compensate
        largest = int(np.argmax(probs))
        if largest not in rural_indices:
            probs[largest] = max(0.01, probs[largest] - boost)

    probs = probs / probs.sum()  # renormalize

    idx = int(rng.choice(len(cities), p=probs))
    return cities[idx], provs[idx]


def _derive_debt_load(row: pd.Series) -> str:
    """
    Infers debt_load from shelter cost ratio (renters) or mortgage data (owners).
    """
    pdct = int(row["PDCT_05"])
    pstir = int(row.get("PSTIR_GR", 9))
    iq = int(row["income_quintile"])

    if pdct == 2:  # renter
        if pstir == 1:
            return "none"
        if pstir == 2:
            return "medium"
        if pstir == 3:
            return "high"
        return "low"

    # owner
    pown20 = int(row.get("POWN_20", 9))
    if pown20 == 2:  # owns outright, no mortgage
        return "none"

    if pown20 == 1:  # has mortgage
        pown80 = row.get("POWN_80", None)
        try:
            pown80_v = int(pown80)
        except (TypeError, ValueError):
            pown80_v = 99_999_996

        if pown80_v >= 99_999_996:  # sentinel
            return ["high", "high", "medium", "low", "low"][iq]
        if pown80_v < 90_000:
            return "low"
        if pown80_v <= 270_000:
            return "medium"
        return "high"

    # POWN_20 in {6, 9} (skip / not stated) — income-based guess
    return ["medium", "medium", "low", "low", "low"][iq]


def _derive_employment_type(row: pd.Series) -> str:
    """
    Infers employment type from PEMPL (employed/not), PAGEP1, PHGEDUC, PFTHB5YR,
    and income_quintile.
    """
    pempl  = int(row.get("PEMPL", 9))
    pagep1 = int(row.get("PAGEP1", 2))
    phged  = int(row.get("PHGEDUC", 99))
    pfthb  = int(row.get("PFTHB5YR", 9))
    iq     = int(row["income_quintile"])

    if pempl == 9:
        return "unemployed"

    if pempl == 2:  # no employed person in household
        if pagep1 == 4:
            return "retired"
        if pagep1 == 1 and phged in {1, 2, 3}:
            return "student"
        return "unemployed"

    # pempl == 1 (at least one employed person)
    # self_employed heuristic: mid-age, mid-to-high income, not recent homebuyer, no degree
    if pagep1 in {2, 3} and iq in {2, 3, 4} and pfthb == 2 and phged in {4, 5}:
        return "self_employed"

    if pagep1 == 1 and phged in {1, 2, 3}:
        return "gig"

    if pfthb == 1:
        return "salaried"

    if phged in {6, 7}:
        return "salaried"

    if iq in {0, 1}:
        return "gig"

    return "salaried"


def _derive_immigration_detail(
    row: pd.Series,
    rng: np.random.Generator,
) -> str:
    """
    Maps PRSPIMST (binary immigrant/non-immigrant) to granular immigration status.
    Uses age group as proxy for recency of arrival.
    """
    prspimst = int(row.get("PRSPIMST", 9))
    if prspimst != 2:
        return "born_here"  # code 1 (non-immigrant) or code 9 (not stated)

    pagep1 = int(row.get("PAGEP1", 2))
    if pagep1 == 1:
        probs = [0.60, 0.30, 0.10]
    elif pagep1 == 2:
        probs = [0.20, 0.65, 0.15]
    else:
        probs = [0.05, 0.90, 0.05]

    return str(rng.choice(
        ["recent_immigrant", "established_immigrant", "refugee"],
        p=probs,
    ))


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_agents(agents: list[dict]) -> None:
    """Validates generated agent list. Raises ValueError on hard failures."""
    if len(agents) != 50:
        raise ValueError(f"Expected 50 agents, got {len(agents)}")

    ids = [a["id"] for a in agents]
    if len(set(ids)) != 50:
        raise ValueError("Duplicate agent IDs detected")

    weight_sum = sum(a["population_weight"] for a in agents)
    if abs(weight_sum - 1.0) > 0.01:
        raise ValueError(f"population_weight sum = {weight_sum:.4f}, expected 1.0 ± 0.01")

    for a in agents:
        if a["city"] not in VALID_CITIES:
            raise ValueError(f"Agent {a['id']} has invalid city: {a['city']!r}")
        if a["age_bracket"] not in VALID_AGE_BRACKETS:
            raise ValueError(f"Agent {a['id']} invalid age_bracket: {a['age_bracket']!r}")
        if a["income_bracket"] not in VALID_INCOME_BRACKETS:
            raise ValueError(f"Agent {a['id']} invalid income_bracket: {a['income_bracket']!r}")
        if a["tenure"] not in VALID_TENURES:
            raise ValueError(f"Agent {a['id']} invalid tenure: {a['tenure']!r}")
        if a["debt_load"] not in VALID_DEBT_LOADS:
            raise ValueError(f"Agent {a['id']} invalid debt_load: {a['debt_load']!r}")
        if a["family_size"] not in VALID_FAMILY_SIZES:
            raise ValueError(f"Agent {a['id']} invalid family_size: {a['family_size']!r}")
        if a["employment_type"] not in VALID_EMPLOYMENT_TYPES:
            raise ValueError(f"Agent {a['id']} invalid employment_type: {a['employment_type']!r}")
        if a["immigration_status"] not in VALID_IMMIGRATION:
            raise ValueError(f"Agent {a['id']} invalid immigration_status: {a['immigration_status']!r}")

    # Soft diversity warnings
    n_renters  = sum(1 for a in agents if a["tenure"] == "renter")
    n_rural    = sum(1 for a in agents if any(
        kw in a["city"] for kw in ["Rural", "Remote", "Reserve", "Nunavut", "Northern"]
    ))
    n_immigrant = sum(1 for a in agents if a["immigration_status"] != "born_here")

    if n_renters < 15:
        warnings.warn(f"Only {n_renters} renters — may underrepresent rental stress")
    if n_rural < 6:
        warnings.warn(f"Only {n_rural} rural/remote agents — below 12% rural target")
    if n_immigrant < 3:
        warnings.warn(f"Only {n_immigrant} immigrant agents — very low immigrant representation")


# ── Main generation function ───────────────────────────────────────────────────

def generate_agents(n: int = 50, seed: int = 42) -> list[dict]:
    """
    Generates n demographically representative agents from CHS 2022 PUMF.
    Deterministic given the same n and seed.
    """
    rng = np.random.default_rng(seed)

    df = _load_and_prepare_pumf()
    rows, cell_weights = _stratify_and_sample(df, rng, n)

    total_weight = sum(cell_weights)
    nunavut_taken = [False]  # mutable flag for Nunavut assignment

    # Pre-assign rural slots: guarantee at least one agent per rural city
    # by tagging specific row indices to force rural city assignment.
    # We tag the first low-income renter in each rural-capable region.
    RURAL_GUARANTEES = {
        3: "Northern Ontario Rural",   # Ontario
        4: "Nunavut Remote",           # Prairies (repurposed)
        5: "Northern BC Rural",        # BC
    }
    rural_region_assigned: dict[int, bool] = {r: False for r in RURAL_GUARANTEES}
    # Also guarantee Reserve Northern Ontario (region 3, very_low)
    reserve_assigned = [False]

    agents: list[dict] = []
    for i, (row, cw) in enumerate(zip(rows, cell_weights)):
        region = int(row["REGION"])
        iq     = int(row["income_quintile"])
        phtype = int(row.get("PHTYPE", 99))
        tenure_code = int(row["PDCT_05"])

        # Force rural assignments for guaranteed slots
        forced_city = None
        forced_prov = None
        if (region == 3 and iq in {0, 1} and tenure_code == 2
                and not reserve_assigned[0]):
            forced_city, forced_prov = "Reserve Northern Ontario", "ON"
            reserve_assigned[0] = True
        elif (region in RURAL_GUARANTEES and iq in {0, 1}
              and not rural_region_assigned[region]):
            forced_city = RURAL_GUARANTEES[region]
            forced_prov = "NU" if forced_city == "Nunavut Remote" else REGION_TO_PROVINCE[region]
            rural_region_assigned[region] = True
            if forced_city == "Nunavut Remote":
                nunavut_taken[0] = True

        if forced_city:
            city, province = forced_city, forced_prov
        else:
            city, province = _derive_city(region, iq, phtype, nunavut_taken, rng)

        agent = {
            "id":               i + 1,
            "city":             city,
            "province":         province,
            "age_bracket":      str(row["age_bracket"]),
            "income_bracket":   INCOME_LABELS[iq],
            "tenure":           "owner" if int(row["PDCT_05"]) == 1 else "renter",
            "debt_load":        _derive_debt_load(row),
            "family_size":      str(row["family_size"]),
            "employment_type":  _derive_employment_type(row),
            "immigration_status": _derive_immigration_detail(row, rng),
            "population_weight": round(cw / total_weight, 4),
        }
        agents.append(agent)

    # Normalize weights and fix rounding so they sum exactly to 1.0
    w_sum = sum(a["population_weight"] for a in agents)
    if abs(w_sum - 1.0) > 0.0001:
        # Adjust the highest-weight agent
        largest_i = max(range(len(agents)), key=lambda i: agents[i]["population_weight"])
        agents[largest_i]["population_weight"] = round(
            agents[largest_i]["population_weight"] + (1.0 - w_sum), 4
        )

    _validate_agents(agents)
    return agents


# ── Cache layer ────────────────────────────────────────────────────────────────

def load_or_generate_agents(
    cache_path: str = CACHE_PATH,
    n: int = 50,
    seed: int = 42,
) -> list[dict] | None:
    """
    Loads agents from cache if available and valid; otherwise generates and
    caches them. Returns None on any failure (caller should use static fallback).
    """
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                data = json.load(f)
            if data.get("n") == n and data.get("seed") == seed:
                agents = data["agents"]
                if len(agents) == n:
                    print(
                        f"[agent_generator] Loaded {n} dynamic agents from cache "
                        f"(generated {data.get('generated_at','?')})",
                        flush=True,
                    )
                    return agents
        except Exception as e:
            print(f"[agent_generator] Cache read failed ({e}), regenerating", flush=True)

    try:
        print("[agent_generator] Generating dynamic agents from CHS 2022 PUMF...", flush=True)
        agents = generate_agents(n, seed)

        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        cache_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": n,
            "seed": seed,
            "pumf_rows_used": 37102,
            "agents": agents,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)

        print(f"[agent_generator] {n} agents generated and cached to {cache_path}", flush=True)
        return agents

    except Exception as e:
        print(f"[agent_generator] Generation failed ({e}), caller should use static fallback", flush=True)
        return None


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating 50 agents from CHS 2022 PUMF...\n")
    agents = generate_agents(50, seed=42)

    # Print summary
    from collections import Counter

    def dist(field):
        return dict(Counter(a[field] for a in agents))

    print(f"Total agents: {len(agents)}")
    print(f"Weight sum:   {sum(a['population_weight'] for a in agents):.4f}")
    print()
    print("Tenure:      ", dist("tenure"))
    print("Income:      ", dist("income_bracket"))
    print("Age:         ", dist("age_bracket"))
    print("Employment:  ", dist("employment_type"))
    print("Immigration: ", dist("immigration_status"))
    print("Debt load:   ", dist("debt_load"))
    print("Family size: ", dist("family_size"))
    print()
    print("City distribution:")
    for city, count in sorted(Counter(a["city"] for a in agents).items(), key=lambda x: -x[1]):
        agents_for_city = [a for a in agents if a["city"] == city]
        w = sum(a["population_weight"] for a in agents_for_city)
        print(f"  {city:<30} {count:>2} agents  weight={w:.3f}")
    print()

    rural_kw = {"Rural", "Remote", "Reserve", "Nunavut", "Northern"}
    n_rural = sum(1 for a in agents if any(kw in a["city"] for kw in rural_kw))
    n_renters = sum(1 for a in agents if a["tenure"] == "renter")
    n_immigrant = sum(1 for a in agents if a["immigration_status"] != "born_here")
    print(f"Rural/remote agents: {n_rural}")
    print(f"Renters:             {n_renters}")
    print(f"Immigrants:          {n_immigrant}")
    print()
    print("Sample agents:")
    for a in agents[:5]:
        print(f"  {a}")
