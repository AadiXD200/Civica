# panel_augmentor.py
# Returns additional agent dicts to append to the base panel for this policy run.
# Each augmented agent gets a high population_weight (0.05) and a distinctive profile.
# IDs start at 51 to avoid collision with the base 50.

DOMAIN_AUGMENTATIONS = {
    "education": [
        {"id": 51, "city": "Toronto", "province": "ON", "age_bracket": "18-24", "income_bracket": "very_low", "tenure": "renter", "debt_load": "high", "family_size": "single", "employment_type": "student", "immigration_status": "born_here", "population_weight": 0.05},
        {"id": 52, "city": "Montreal", "province": "QC", "age_bracket": "18-24", "income_bracket": "very_low", "tenure": "renter", "debt_load": "high", "family_size": "single", "employment_type": "student", "immigration_status": "recent_immigrant", "population_weight": 0.05},
        {"id": 53, "city": "Halifax", "province": "NS", "age_bracket": "18-24", "income_bracket": "low", "tenure": "renter", "debt_load": "high", "family_size": "single", "employment_type": "student", "immigration_status": "born_here", "population_weight": 0.03},
        {"id": 54, "city": "Vancouver", "province": "BC", "age_bracket": "25-34", "income_bracket": "low", "tenure": "renter", "debt_load": "high", "family_size": "single", "employment_type": "student", "immigration_status": "established_immigrant", "population_weight": 0.04},
    ],
    "healthcare": [
        {"id": 51, "city": "Northern Ontario Rural", "province": "ON", "age_bracket": "65+", "income_bracket": "low", "tenure": "owner", "debt_load": "none", "family_size": "couple", "employment_type": "retired", "immigration_status": "born_here", "population_weight": 0.05},
        {"id": 52, "city": "PEI Rural", "province": "PE", "age_bracket": "50-64", "income_bracket": "very_low", "tenure": "renter", "debt_load": "low", "family_size": "single", "employment_type": "unemployed", "immigration_status": "born_here", "population_weight": 0.04},
        {"id": 53, "city": "Winnipeg", "province": "MB", "age_bracket": "35-49", "income_bracket": "low", "tenure": "renter", "debt_load": "medium", "family_size": "large_family", "employment_type": "gig", "immigration_status": "refugee", "population_weight": 0.05},
        {"id": 54, "city": "Vancouver", "province": "BC", "age_bracket": "65+", "income_bracket": "very_low", "tenure": "renter", "debt_load": "none", "family_size": "single", "employment_type": "retired", "immigration_status": "recent_immigrant", "population_weight": 0.04},
    ],
    "labour": [
        {"id": 51, "city": "Toronto", "province": "ON", "age_bracket": "25-34", "income_bracket": "very_low", "tenure": "renter", "debt_load": "medium", "family_size": "single", "employment_type": "gig", "immigration_status": "recent_immigrant", "population_weight": 0.05},
        {"id": 52, "city": "Calgary", "province": "AB", "age_bracket": "35-49", "income_bracket": "low", "tenure": "renter", "debt_load": "high", "family_size": "small_family", "employment_type": "gig", "immigration_status": "born_here", "population_weight": 0.05},
        {"id": 53, "city": "Vancouver", "province": "BC", "age_bracket": "25-34", "income_bracket": "very_low", "tenure": "renter", "debt_load": "medium", "family_size": "single", "employment_type": "gig", "immigration_status": "established_immigrant", "population_weight": 0.04},
        {"id": 54, "city": "Hamilton", "province": "ON", "age_bracket": "50-64", "income_bracket": "low", "tenure": "renter", "debt_load": "medium", "family_size": "couple", "employment_type": "unemployed", "immigration_status": "born_here", "population_weight": 0.04},
    ],
    "transit": [
        {"id": 51, "city": "Toronto", "province": "ON", "age_bracket": "25-34", "income_bracket": "very_low", "tenure": "renter", "debt_load": "medium", "family_size": "single", "employment_type": "gig", "immigration_status": "recent_immigrant", "population_weight": 0.05},
        {"id": 52, "city": "Montreal", "province": "QC", "age_bracket": "18-24", "income_bracket": "very_low", "tenure": "renter", "debt_load": "none", "family_size": "single", "employment_type": "student", "immigration_status": "born_here", "population_weight": 0.04},
        {"id": 53, "city": "Northern Ontario Rural", "province": "ON", "age_bracket": "35-49", "income_bracket": "low", "tenure": "owner", "debt_load": "medium", "family_size": "large_family", "employment_type": "salaried", "immigration_status": "born_here", "population_weight": 0.04},
    ],
    "climate": [
        {"id": 51, "city": "Calgary", "province": "AB", "age_bracket": "35-49", "income_bracket": "high", "tenure": "owner", "debt_load": "medium", "family_size": "small_family", "employment_type": "salaried", "immigration_status": "born_here", "population_weight": 0.05},
        {"id": 52, "city": "Northern BC Rural", "province": "BC", "age_bracket": "50-64", "income_bracket": "low", "tenure": "owner", "debt_load": "low", "family_size": "couple", "employment_type": "self_employed", "immigration_status": "born_here", "population_weight": 0.04},
        {"id": 53, "city": "Regina", "province": "SK", "age_bracket": "35-49", "income_bracket": "medium", "tenure": "owner", "debt_load": "medium", "family_size": "large_family", "employment_type": "salaried", "immigration_status": "born_here", "population_weight": 0.05},
    ],
    "immigration": [
        {"id": 51, "city": "Toronto", "province": "ON", "age_bracket": "25-34", "income_bracket": "low", "tenure": "renter", "debt_load": "medium", "family_size": "small_family", "employment_type": "salaried", "immigration_status": "recent_immigrant", "population_weight": 0.05},
        {"id": 52, "city": "Vancouver", "province": "BC", "age_bracket": "35-49", "income_bracket": "low", "tenure": "renter", "debt_load": "medium", "family_size": "small_family", "employment_type": "salaried", "immigration_status": "refugee", "population_weight": 0.05},
        {"id": 53, "city": "Winnipeg", "province": "MB", "age_bracket": "25-34", "income_bracket": "very_low", "tenure": "renter", "debt_load": "none", "family_size": "large_family", "employment_type": "unemployed", "immigration_status": "refugee", "population_weight": 0.04},
        {"id": 54, "city": "Edmonton", "province": "AB", "age_bracket": "35-49", "income_bracket": "medium", "tenure": "renter", "debt_load": "medium", "family_size": "large_family", "employment_type": "salaried", "immigration_status": "established_immigrant", "population_weight": 0.04},
    ],
}


def get_dynamic_panel_augmentation(domain: str, policy_classification: dict, base_agents: list) -> list:
    """Returns additional agents to add to the panel for this policy domain."""
    augments = DOMAIN_AUGMENTATIONS.get(domain, [])
    # Also augment based on primary_affected if domain augmentation is empty
    if not augments:
        primary = policy_classification.get("primary_affected", "")
        if "youth" in primary or "student" in primary:
            augments = DOMAIN_AUGMENTATIONS.get("education", [])
        elif "worker" in primary or "gig" in primary:
            augments = DOMAIN_AUGMENTATIONS.get("labour", [])
    return augments
