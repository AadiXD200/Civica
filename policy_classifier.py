import json
import re
from dotenv import load_dotenv

load_dotenv()

# ── Known Canadian cities → province mapping ─────────────────────────────────
# Used for deterministic city extraction from policy text (no LLM needed)
CITY_TO_PROVINCE: dict[str, str] = {
    "toronto": "ON", "north york": "ON", "scarborough": "ON", "etobicoke": "ON",
    "mississauga": "ON", "brampton": "ON", "hamilton": "ON", "london": "ON",
    "ottawa": "ON", "kingston": "ON", "kitchener": "ON", "waterloo": "ON",
    "windsor": "ON", "barrie": "ON", "sudbury": "ON", "thunder bay": "ON",
    "montreal": "QC", "québec city": "QC", "quebec city": "QC", "laval": "QC",
    "longueuil": "QC", "gatineau": "QC", "sherbrooke": "QC",
    "vancouver": "BC", "surrey": "BC", "burnaby": "BC", "richmond": "BC",
    "abbotsford": "BC", "kelowna": "BC", "victoria": "BC", "nanaimo": "BC",
    "calgary": "AB", "edmonton": "AB", "red deer": "AB", "lethbridge": "AB",
    "medicine hat": "AB", "fort mcmurray": "AB",
    "saskatoon": "SK", "regina": "SK",
    "winnipeg": "MB", "brandon": "MB",
    "halifax": "NS", "dartmouth": "NS",
    "fredericton": "NB", "moncton": "NB", "saint john": "NB",
    "charlottetown": "PE",
    "st. john's": "NL", "st johns": "NL",
    "whitehorse": "YT",
    "yellowknife": "NT",
    "iqaluit": "NU",
}

# Province name → code mapping (for when policy says "Ontario" not "Toronto")
PROVINCE_NAME_TO_CODE: dict[str, str] = {
    "ontario": "ON", "british columbia": "BC", "alberta": "AB",
    "quebec": "QC", "québec": "QC", "saskatchewan": "SK", "manitoba": "MB",
    "nova scotia": "NS", "new brunswick": "NB", "newfoundland": "NL",
    "newfoundland and labrador": "NL", "pei": "PE", "prince edward island": "PE",
    "yukon": "YT", "northwest territories": "NT", "nunavut": "NU",
    "bc": "BC", "ab": "AB", "on": "ON", "qc": "QC", "sk": "SK",
    "mb": "MB", "ns": "NS", "nb": "NB", "nl": "NL",
}

# Province code → REGION code in CHS PUMF
PROVINCE_TO_REGION: dict[str, int] = {
    "NS": 1, "NB": 1, "NL": 1, "PE": 1,
    "QC": 2,
    "ON": 3,
    "SK": 4, "MB": 4, "AB": 4,
    "BC": 5,
    "YT": 5, "NT": 4, "NU": 4,
}

# Province code → valid cities in that province (for agent generation)
PROVINCE_TO_CITIES: dict[str, list[str]] = {
    "ON": ["Toronto", "Ottawa", "Hamilton", "Kitchener-Waterloo", "Sudbury", "Northern Ontario Rural", "Reserve Northern Ontario"],
    "QC": ["Montreal"],
    "BC": ["Vancouver", "Victoria", "Kelowna", "Northern BC Rural"],
    "AB": ["Calgary", "Edmonton"],
    "SK": ["Saskatoon", "Regina"],
    "MB": ["Winnipeg"],
    "NS": ["Halifax"],
    "NB": ["Halifax"],  # no NB city in panel — Halifax is nearest Maritime proxy
    "NL": ["Halifax"],  # no NL city in panel — Halifax is nearest Atlantic proxy
    "PE": ["PEI Rural"],
    "YT": ["Northern BC Rural"],
    "NT": ["Nunavut Remote"],
    "NU": ["Nunavut Remote"],
}

# City name in policy text → canonical city name used in agent system
CITY_CANONICAL: dict[str, str] = {
    "toronto": "Toronto", "north york": "Toronto", "scarborough": "Toronto",
    "etobicoke": "Toronto", "mississauga": "Toronto", "brampton": "Toronto",
    "ottawa": "Ottawa", "hamilton": "Hamilton",
    "kitchener": "Kitchener-Waterloo", "waterloo": "Kitchener-Waterloo",
    "sudbury": "Sudbury",
    "montreal": "Montreal", "québec city": "Montreal", "quebec city": "Montreal",
    "laval": "Montreal", "longueuil": "Montreal", "gatineau": "Ottawa",
    "sherbrooke": "Montreal",
    "vancouver": "Vancouver", "surrey": "Vancouver", "burnaby": "Vancouver",
    "richmond": "Vancouver", "abbotsford": "Vancouver",
    "kelowna": "Kelowna", "victoria": "Victoria", "nanaimo": "Victoria",
    "calgary": "Calgary", "edmonton": "Edmonton",
    "red deer": "Edmonton", "lethbridge": "Calgary",
    "fort mcmurray": "Edmonton",
    "saskatoon": "Saskatoon", "regina": "Regina",
    "winnipeg": "Winnipeg",
    "halifax": "Halifax", "dartmouth": "Halifax",
    "fredericton": "Halifax", "moncton": "Halifax", "saint john": "Halifax",
    "charlottetown": "PEI Rural",
    "st. john's": "Halifax", "st johns": "Halifax",
    "whitehorse": "Northern BC Rural",
    "yellowknife": "Nunavut Remote",
    "iqaluit": "Nunavut Remote",
}


def extract_geo_scope(policy_text: str) -> dict:
    """
    Deterministically extracts geographic scope from policy text.
    No LLM call — pure regex + lookup.

    Returns:
        {
            "scope_level": "municipal" | "provincial" | "national",
            "detected_cities": [...],      # canonical city names
            "detected_provinces": [...],   # province codes
            "primary_province": "ON"|...,  # single province if clear, else None
            "chs_regions": [...],          # PUMF REGION codes to sample from
            "city_weights": {...},         # city → weight for agent sampling
        }
    """
    text_lower = policy_text.lower()

    # ── Step 1: Find all city mentions ──────────────────────────────────────
    detected_cities: list[str] = []
    city_province_map: dict[str, str] = {}

    for city_raw, province in CITY_TO_PROVINCE.items():
        # Match whole word / phrase
        pattern = r'\b' + re.escape(city_raw) + r'\b'
        if re.search(pattern, text_lower):
            canonical = CITY_CANONICAL.get(city_raw, city_raw.title())
            if canonical not in detected_cities:
                detected_cities.append(canonical)
                city_province_map[canonical] = province

    # ── Step 2: Find province mentions ──────────────────────────────────────
    detected_provinces: list[str] = []
    for prov_name, prov_code in PROVINCE_NAME_TO_CODE.items():
        pattern = r'\b' + re.escape(prov_name) + r'\b'
        if re.search(pattern, text_lower):
            if prov_code not in detected_provinces:
                detected_provinces.append(prov_code)

    # Add provinces implied by detected cities
    for city, prov in city_province_map.items():
        if prov not in detected_provinces:
            detected_provinces.append(prov)

    # ── Step 3: Determine scope level ───────────────────────────────────────
    # Municipal: 1-2 cities explicitly mentioned, no national language
    # Provincial: province(s) mentioned or implied, no national scope words
    # National: default / national keywords / multiple provinces
    national_keywords = r'\b(canada|canadian|national|federal|country-wide|nationwide|all provinces|every province)\b'
    is_national_language = bool(re.search(national_keywords, text_lower))

    n_provinces = len(set(detected_provinces))

    if detected_cities and not is_national_language and n_provinces <= 2:
        scope_level = "municipal"
    elif detected_provinces and not is_national_language and n_provinces <= 2:
        scope_level = "provincial"
    else:
        scope_level = "national"

    # ── Step 4: Primary province ────────────────────────────────────────────
    primary_province: str | None = None
    if len(set(detected_provinces)) == 1:
        primary_province = detected_provinces[0]
    elif scope_level == "municipal" and city_province_map:
        # All detected cities in same province?
        provs = set(city_province_map.values())
        if len(provs) == 1:
            primary_province = list(provs)[0]

    # ── Step 5: CHS regions to sample from ─────────────────────────────────
    if scope_level == "national":
        chs_regions = [1, 2, 3, 4, 5]
    elif primary_province:
        region = PROVINCE_TO_REGION.get(primary_province)
        if region:
            # Always include at least 2 adjacent regions for robustness
            adjacent = {
                1: [1, 2],      # Atlantic → also QC
                2: [2, 3],      # QC → also ON
                3: [3, 2],      # ON → also QC
                4: [4, 3],      # Prairies → also ON
                5: [5, 4],      # BC → also Prairies
            }
            chs_regions = adjacent.get(region, [region])
        else:
            chs_regions = [1, 2, 3, 4, 5]
    else:
        chs_regions = [1, 2, 3, 4, 5]

    # ── Step 6: City weights for agent sampling ─────────────────────────────
    city_weights: dict[str, float] = {}
    if scope_level == "municipal" and detected_cities:
        # Weight detected cities heavily; fill remainder from same province
        primary_weight = 0.70 / len(detected_cities)
        for city in detected_cities:
            city_weights[city] = primary_weight
        # Fill rest from same province cities
        if primary_province:
            fill_cities = [
                c for c in PROVINCE_TO_CITIES.get(primary_province, [])
                if c not in detected_cities
            ]
            if fill_cities:
                remainder = 0.30
                per_fill = remainder / len(fill_cities)
                for c in fill_cities:
                    city_weights[c] = per_fill
    elif scope_level == "provincial" and primary_province:
        prov_cities = PROVINCE_TO_CITIES.get(primary_province, [])
        if prov_cities:
            per_city = 1.0 / len(prov_cities)
            for c in prov_cities:
                city_weights[c] = per_city
    # national: city_weights stays empty → agent_generator uses its normal distribution

    return {
        "scope_level": scope_level,
        "detected_cities": detected_cities,
        "detected_provinces": detected_provinces,
        "primary_province": primary_province,
        "chs_regions": chs_regions,
        "city_weights": city_weights,
    }


# ── Policy-type → demographic boost config ───────────────────────────────────
# Each policy type defines which demographic cells to oversample.
# "guaranteed_slots" ensures specific demographics always appear in the panel.

POLICY_TYPE_SAMPLING: dict[str, dict] = {
    # age_boost keys are PAGEP1 codes: 1=18-34, 2=35-49, 3=50-64, 4=65+
    "supply": {
        "tenure_boost": {"renter": 2.5, "owner": 1.0},
        "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.2, "high": 0.8, "very_high": 0.5},
        "age_boost": {1: 1.8, 2: 1.5, 3: 1.0, 4: 0.8},  # young renters squeezed hardest
        "guaranteed_slots": ["indigenous_renter", "senior_renter", "recent_immigrant_renter", "youth_renter"],
    },
    "demand": {
        "tenure_boost": {"renter": 2.0, "owner": 1.2},
        "income_boost": {"very_low": 2.0, "low": 2.0, "medium": 1.5, "high": 1.0, "very_high": 0.7},
        "age_boost": {1: 2.0, 2: 1.5, 3: 1.0, 4: 0.8},
        "guaranteed_slots": ["youth_renter", "recent_immigrant_renter", "senior_owner"],
    },
    "tax": {
        "tenure_boost": {"renter": 1.5, "owner": 1.5},
        "income_boost": {"very_low": 1.5, "low": 1.5, "medium": 1.5, "high": 1.2, "very_high": 1.5},
        "age_boost": {1: 1.0, 2: 1.5, 3: 1.8, 4: 1.5},  # working-age and seniors most tax-exposed
        "guaranteed_slots": ["senior_owner", "small_business_owner", "low_income_renter"],
    },
    "ai": {
        "tenure_boost": {"renter": 1.5, "owner": 1.2},
        "income_boost": {"very_low": 1.5, "low": 1.8, "medium": 2.0, "high": 1.2, "very_high": 0.8},
        "age_boost": {1: 3.0, 2: 2.5, 3: 1.0, 4: 0.3},  # youth and young adults are primary digital users
        "guaranteed_slots": ["gig_worker", "recent_immigrant_worker", "older_worker", "youth_worker"],
    },
    "healthcare": {
        "tenure_boost": {"renter": 1.5, "owner": 1.2},
        "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.2, "high": 0.8, "very_high": 0.5},
        "age_boost": {1: 1.0, 2: 1.2, 3: 1.8, 4: 2.5},  # seniors and chronic illness skew older
        "guaranteed_slots": ["indigenous_renter", "senior_renter", "refugee", "low_income_renter"],
    },
    "transit": {
        "tenure_boost": {"renter": 2.0, "owner": 1.0},
        "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.5, "high": 0.8, "very_high": 0.5},
        "age_boost": {1: 2.5, 2: 1.5, 3: 1.0, 4: 1.2},  # youth + seniors are heaviest transit users
        "guaranteed_slots": ["youth_renter", "recent_immigrant_renter", "low_income_renter", "senior_renter"],
    },
    "labour": {
        "tenure_boost": {"renter": 1.8, "owner": 1.0},
        "income_boost": {"very_low": 2.0, "low": 2.0, "medium": 1.5, "high": 1.0, "very_high": 0.8},
        "age_boost": {1: 2.0, 2: 2.0, 3: 1.5, 4: 0.5},  # working-age population
        "guaranteed_slots": ["gig_worker", "recent_immigrant_worker", "youth_worker", "indigenous_worker"],
    },
    "immigration": {
        "tenure_boost": {"renter": 2.5, "owner": 0.8},
        "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.2, "high": 0.8, "very_high": 0.5},
        "age_boost": {1: 2.5, 2: 2.0, 3: 1.0, 4: 0.5},  # immigrants skew younger
        "guaranteed_slots": ["recent_immigrant_renter", "refugee", "recent_immigrant_worker", "youth_renter"],
    },
    "environment": {
        "tenure_boost": {"renter": 1.2, "owner": 1.8},
        "income_boost": {"very_low": 1.5, "low": 1.8, "medium": 2.0, "high": 1.8, "very_high": 1.2},
        "age_boost": {1: 1.0, 2: 2.0, 3: 2.0, 4: 1.2},  # working-age fossil fuel workers + rate-payers
        "guaranteed_slots": ["rural_owner", "low_income_renter", "indigenous_renter", "senior_owner", "older_worker"],
        "region_boost": {4: 3.5},
    },
    "education": {
        "tenure_boost": {"renter": 2.0, "owner": 1.0},
        "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.5, "high": 1.0, "very_high": 0.5},
        "age_boost": {1: 3.5, 2: 1.5, 3: 0.8, 4: 0.5},  # students and young adults primary
        "guaranteed_slots": ["youth_renter", "recent_immigrant_renter", "indigenous_renter", "low_income_renter"],
    },
    "corrections": {
        "tenure_boost": {"renter": 2.0, "owner": 0.8},
        "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.2, "high": 0.8, "very_high": 0.5},
        "age_boost": {1: 2.5, 2: 2.0, 3: 1.2, 4: 0.5},  # justice-involved skews younger
        "guaranteed_slots": ["low_income_renter", "indigenous_renter", "youth_renter", "recent_immigrant_renter"],
    },
    "other": {
        "tenure_boost": {"renter": 1.8, "owner": 1.2},
        "income_boost": {"very_low": 2.0, "low": 1.8, "medium": 1.4, "high": 1.0, "very_high": 0.8},
        "age_boost": {1: 1.5, 2: 1.5, 3: 1.2, 4: 1.0},  # slight youth boost for unknown domain
        "guaranteed_slots": ["low_income_renter", "senior_renter", "recent_immigrant_renter"],
    },
}


async def classify_policy(client, asst_id, policy_text: str, intake_hints: dict | None = None) -> dict:
    """
    Runs before simulation starts.
    Classifies policy type to activate relevant agent attributes and data routing.
    Also extracts geographic scope deterministically (no extra LLM call).
    """
    hints = intake_hints or {}

    # ── Geographic scope extracted deterministically ─────────────────────────
    geo_scope = extract_geo_scope(policy_text)

    hint_lines = []
    if hints.get("primary_affected"):
        hint_lines.append(f'- primary_affected is already known: "{hints["primary_affected"]}" — use this value exactly')
    if hints.get("geography"):
        hint_lines.append(f'- geography is already known: "{hints["geography"]}" — use this value exactly')
    if hints.get("time_horizon"):
        hint_lines.append(f'- time_horizon is already known: "{hints["time_horizon"]}" — use this value exactly')
    if hints.get("mechanism"):
        hint_lines.append(f'- the policy mechanism is "{hints["mechanism"]}" — use this to inform the type field')

    hint_block = ""
    if hint_lines:
        hint_block = "\n\nUser-provided context (treat as authoritative):\n" + "\n".join(hint_lines)

    thread = await client.create_thread(asst_id)
    response = await client.add_message(
        thread_id=thread.thread_id,
        content=f"""Classify this Canadian government policy for demographic simulation purposes.

Policy: {policy_text}{hint_block}

Return exactly this JSON and nothing else:
{{
    "type": "supply|demand|tax|ai|healthcare|transit|labour|immigration|environment|education|corrections|other",
    "primary_affected": "renters|owners|all|low_income|immigrants|seniors|youth|indigenous|workers|justice_involved",
    "market": "rental|ownership|both|non_housing",
    "geography": "national|provincial|urban|rural|regional",
    "time_horizon": "immediate|short_term|long_term",
    "key_attributes": ["list", "of", "3-5", "demographic", "attributes", "most", "relevant", "to", "this", "policy"]
}}

Type selection rules:
- Use "ai" ONLY for policies primarily about artificial intelligence, automation, algorithmic systems, or digital technology governance. A labour policy that mentions digital tools is still "labour", not "ai".
- Use "labour" ONLY for policies primarily about employment conditions, wages, working hours, collective bargaining, or labour market regulation. A corrections policy that includes a reintegration employment provision is still "corrections", not "labour".
- Use "corrections" for policies primarily about criminal justice, parole, probation, incarceration, reintegration of justice-involved persons, or corrections system reform. Use this even when the policy has employment-adjacent provisions (Ban the Box, reintegration tax credits) as long as the primary subject is corrections/parole reform.
- Use "other" when no specific type fits.""",
        llm_provider="openai",
        model_name="gpt-4o",
        stream=False,
    )
    raw = response.content.strip().replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(raw)
        if hints.get("primary_affected"):
            result["primary_affected"] = hints["primary_affected"]
        if hints.get("geography"):
            result["geography"] = hints["geography"]
        if hints.get("time_horizon"):
            result["time_horizon"] = hints["time_horizon"]

        # Inject geo scope into classification result
        result["geo_scope"] = geo_scope
        # Get sampling config for this policy type
        result["sampling_config"] = POLICY_TYPE_SAMPLING.get(
            result.get("type", "other"), POLICY_TYPE_SAMPLING["other"]
        )
        return result
    except Exception:
        base = {
            "type": "other",
            "primary_affected": hints.get("primary_affected", "all"),
            "market": "non_housing",
            "geography": hints.get("geography", "national"),
            "time_horizon": hints.get("time_horizon", "short_term"),
            "key_attributes": ["age_bracket", "income_bracket", "employment_type"],
            "geo_scope": geo_scope,
            "sampling_config": POLICY_TYPE_SAMPLING["other"],
        }
        return base
