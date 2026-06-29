"""
agent_generator.py

Generates 50 demographically representative Canadian household agents by
stratified weighted sampling from the Statistics Canada CHS 2022 PUMF.

Key upgrade: accepts a scope_config from policy_classifier to generate
a panel scoped to the policy's geography and type:
  - Municipal policy in Toronto → 70%+ Ontario urban households
  - Provincial BC policy → BC-weighted households
  - National policy → full Canada distribution (default)
  - Housing policy → oversample renters, low-income
  - AI policy → oversample workers, gig, mid-income
  - etc.

Guaranteed stratified slots ensure every relevant demographic always appears.
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
AGE_MAP           = {1: "25-34", 2: "35-49", 3: "50-64", 4: "65+"}
REGION_TO_PROVINCE = {1: "NS", 2: "QC", 3: "ON", 4: "AB", 5: "BC"}

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

# ── City assignment probabilities per REGION (national default) ───────────────
CITY_ASSIGNMENTS_NATIONAL: dict[int, list[tuple[str, str, float]]] = {
    1: [("Halifax", "NS", 0.85), ("PEI Rural", "PE", 0.15)],
    2: [("Montreal", "QC", 1.00)],
    3: [
        ("Toronto", "ON", 0.42), ("Ottawa", "ON", 0.15),
        ("Hamilton", "ON", 0.10), ("Kitchener-Waterloo", "ON", 0.10),
        ("Sudbury", "ON", 0.08), ("Northern Ontario Rural", "ON", 0.11),
        ("Reserve Northern Ontario", "ON", 0.04),
    ],
    4: [
        ("Calgary", "AB", 0.30), ("Edmonton", "AB", 0.25),
        ("Saskatoon", "SK", 0.20), ("Regina", "SK", 0.15),
        ("Winnipeg", "MB", 0.10),
    ],
    5: [
        ("Vancouver", "BC", 0.55), ("Victoria", "BC", 0.20),
        ("Kelowna", "BC", 0.15), ("Northern BC Rural", "BC", 0.10),
    ],
}

# Scoped city weights per province (used when scope_level != national)
CITY_ASSIGNMENTS_BY_PROVINCE: dict[str, list[tuple[str, str, float]]] = {
    "ON": [
        ("Toronto", "ON", 0.50), ("Ottawa", "ON", 0.18),
        ("Hamilton", "ON", 0.12), ("Kitchener-Waterloo", "ON", 0.10),
        ("Sudbury", "ON", 0.05), ("Northern Ontario Rural", "ON", 0.03),
        ("Reserve Northern Ontario", "ON", 0.02),
    ],
    "QC": [("Montreal", "QC", 1.00)],
    "BC": [
        ("Vancouver", "BC", 0.65), ("Victoria", "BC", 0.20),
        ("Kelowna", "BC", 0.10), ("Northern BC Rural", "BC", 0.05),
    ],
    "AB": [("Calgary", "AB", 0.52), ("Edmonton", "AB", 0.48)],
    "SK": [("Saskatoon", "SK", 0.55), ("Regina", "SK", 0.45)],
    "MB": [("Winnipeg", "MB", 1.00)],
    "NS": [("Halifax", "NS", 1.00)],
    "NB": [("Halifax", "NS", 1.00)],
    "NL": [("Halifax", "NS", 1.00)],
    "PE": [("PEI Rural", "PE", 1.00)],
    "YT": [("Northern BC Rural", "BC", 1.00)],
    "NT": [("Nunavut Remote", "NU", 1.00)],
    "NU": [("Nunavut Remote", "NU", 1.00)],
}

# Guaranteed slot definitions — ensures specific demographics always in panel
# Format: (tenure, income_quintile_range, age_code_range, immigration_type)
GUARANTEED_SLOT_DEFS: dict[str, dict] = {
    "indigenous_renter":       {"tenure": 2, "iq_range": (0, 2), "age_range": (1, 3), "force_city": "Reserve Northern Ontario"},
    "senior_renter":           {"tenure": 2, "iq_range": (0, 2), "age_range": (4, 4), "force_city": None},
    "senior_owner":            {"tenure": 1, "iq_range": (1, 3), "age_range": (4, 4), "force_city": None},
    "youth_renter":            {"tenure": 2, "iq_range": (0, 2), "age_range": (1, 1), "force_city": None},
    "recent_immigrant_renter": {"tenure": 2, "iq_range": (0, 2), "age_range": (1, 2), "force_imm": "recent_immigrant"},
    "recent_immigrant_worker": {"tenure": 2, "iq_range": (1, 3), "age_range": (1, 2), "force_imm": "recent_immigrant"},
    "refugee":                 {"tenure": 2, "iq_range": (0, 1), "age_range": (1, 2), "force_imm": "refugee"},
    "low_income_renter":       {"tenure": 2, "iq_range": (0, 1), "age_range": (1, 3), "force_city": None},
    "gig_worker":              {"tenure": 2, "iq_range": (0, 2), "age_range": (1, 2), "force_empl": "gig"},
    "older_worker":            {"tenure": 1, "iq_range": (2, 3), "age_range": (3, 3), "force_city": None},
    "youth_worker":            {"tenure": 2, "iq_range": (1, 2), "age_range": (1, 1), "force_empl": "salaried"},
    "indigenous_worker":       {"tenure": 2, "iq_range": (0, 2), "age_range": (1, 3), "force_city": "Reserve Northern Ontario"},
    "rural_owner":             {"tenure": 1, "iq_range": (1, 3), "age_range": (2, 4), "force_city": "Northern Ontario Rural"},
    "small_business_owner":    {"tenure": 1, "iq_range": (2, 4), "age_range": (2, 3), "force_empl": "self_employed"},
}


# ── Domain persona definitions ────────────────────────────────────────────────
# For non-housing policies, inject 15 synthetic personas whose primary lens
# matches the policy domain. These are NOT drawn from PUMF — they're constructed
# from policy-relevant archetypes with plausible demographic grounding.
# Each entry: city, tenure, age_bracket, income_bracket, employment_type,
#             immigration_status, family_size, debt_load, population_weight (pre-norm)
# population_weight is set equal to a typical PUMF agent (~0.02) and re-normalized.

DOMAIN_PERSONAS: dict[str, list[dict]] = {
    "drug_health": [
        # People with lived substance-use experience — the primary affected group
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "25-34", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "person_in_recovery",         "domain_context": "In recovery from opioid use disorder; previously relied on emergency services"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "very_low",  "employment_type": "gig",          "immigration_status": "established_immigrant", "family_size": "single",       "debt_load": "high",   "domain_role": "active_substance_user",      "domain_context": "Currently using substances; lives near a known consumption site corridor"},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "18-24", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "youth_substance_user",       "domain_context": "Youth with substance use disorder; had prior possession charge"},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "indigenous_substance_user",  "domain_context": "Indigenous, lives off-reserve; history of substance use tied to intergenerational trauma"},
        {"city": "Halifax",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "high",   "domain_role": "parent_substance_user",      "domain_context": "Parent with substance use disorder; fears criminal record affecting custody"},
        # Healthcare and harm-reduction workers
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "harm_reduction_worker",      "domain_context": "Front-line harm reduction worker at a supervised consumption site"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "recent_immigrant",      "family_size": "couple",       "debt_load": "low",    "domain_role": "public_health_nurse",        "domain_context": "Public health nurse who regularly responds to overdose calls"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "addictions_counsellor",      "domain_context": "Addictions counsellor at a publicly funded treatment centre"},
        # People with criminal records from prior possession
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "prior_possession_charge",    "domain_context": "Has prior drug possession conviction; faces employment and housing barriers as a result"},
        {"city": "Edmonton",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "racialized_prior_charge",    "domain_context": "Racialized person; disproportionately policed for possession; prior conviction affecting employment"},
        # Community members near proposed consumption sites
        {"city": "Vancouver",          "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "low",    "domain_role": "nimby_homeowner",            "domain_context": "Homeowner near proposed consumption site; concerned about neighbourhood safety and property values"},
        {"city": "Montreal",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "small_business_near_site",   "domain_context": "Small business owner one block from a proposed supervised consumption facility"},
        # Municipal and enforcement perspective
        {"city": "Ottawa",             "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "municipal_budget_officer",   "domain_context": "Works in municipal finance; tracks RCMP/policing budget reallocation impacts"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "conservative_taxpayer",      "domain_context": "Skeptical of decriminalization; concerned about public safety and moral hazard of policy"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "established_immigrant", "family_size": "single",       "debt_load": "medium", "domain_role": "neighbourhood_peer_worker",  "domain_context": "Peer support worker; was formerly unhoused and substance-using; now employed in harm reduction"},
    ],
    "labour_employment": [
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "gig_platform_worker",        "domain_context": "Ride-share and delivery worker; no employment benefits or union protection"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "recent_immigrant",      "family_size": "small_family", "debt_load": "high",   "domain_role": "temp_agency_worker",         "domain_context": "Works through temp agencies; income is irregular and below median"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "small_employer",             "domain_context": "Runs a 12-person business; tracks wage floor and compliance costs directly"},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "unionized_worker",           "domain_context": "Member of a private-sector union; tracks collective agreement impacts"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "18-24", "income_bracket": "very_low",  "employment_type": "student",      "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "student_part_time_worker",   "domain_context": "Part-time student worker; minimum wage is primary income"},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "indigenous_worker",          "domain_context": "Indigenous worker; faces systemic hiring barriers; tracks labour equity policy closely"},
        {"city": "Edmonton",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "franchise_owner",            "domain_context": "Franchise operator with 30+ employees; compliance cost exposure is high"},
        {"city": "Halifax",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "salaried",     "immigration_status": "recent_immigrant",      "family_size": "small_family", "debt_load": "medium", "domain_role": "precarious_worker",          "domain_context": "Works multiple part-time jobs; no path to permanent employment"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "established_immigrant", "family_size": "couple",       "debt_load": "low",    "domain_role": "tech_worker",                "domain_context": "Knowledge worker; tracks automation and AI displacement risk"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "unemployed",   "immigration_status": "established_immigrant", "family_size": "small_family", "debt_load": "high",   "domain_role": "long_term_unemployed",       "domain_context": "Long-term unemployed; benefits recipient; tracks policy effects on income support"},
        {"city": "Ottawa",             "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "hr_manager",                 "domain_context": "HR manager at a mid-size firm; tracks hiring, firing, and compliance impacts"},
        {"city": "Montreal",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "professional_self_employed",  "domain_context": "Incorporated professional; tracks regulatory and tax implications for the self-employed"},
        {"city": "Calgary",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "recent_immigrant",      "family_size": "single",       "debt_load": "medium", "domain_role": "migrant_worker",             "domain_context": "Temporary foreign worker; limited access to employment protections"},
        {"city": "Hamilton",           "tenure": "renter", "age_bracket": "50-64", "income_bracket": "low",       "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "displaced_manufacturing",    "domain_context": "Former factory worker; displaced by automation; seeking retraining"},
        {"city": "Toronto",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "middle_manager",             "domain_context": "Middle manager; tracks hiring freezes and headcount decisions directly"},
    ],
    "healthcare": [
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "65+",   "income_bracket": "low",       "employment_type": "retired",      "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "elderly_patient",            "domain_context": "Regular user of public healthcare; tracks wait times and drug coverage personally"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "recent_immigrant",      "family_size": "small_family", "debt_load": "high",   "domain_role": "uninsured_patient",          "domain_context": "No employer drug plan; pays out-of-pocket for prescriptions; tracks cost directly"},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "healthcare_worker",          "domain_context": "Registered nurse; tracks workload, staffing ratios, and wage impacts"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "very_high", "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "private_insurance_user",     "domain_context": "Has private drug plan through employer; tracks public-private system interactions"},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "50-64", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "chronic_condition_patient",  "domain_context": "Managing diabetes and hypertension; high prescription drug costs relative to income"},
        {"city": "Halifax",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "family_caregiver",           "domain_context": "Primary caregiver for elderly parent; tracks home care funding and respite services"},
        {"city": "Ottawa",             "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "low",    "domain_role": "hospital_administrator",     "domain_context": "Hospital finance officer; tracks provincial funding, bed capacity, and staffing budgets"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "established_immigrant", "family_size": "single",       "debt_load": "medium", "domain_role": "mental_health_patient",      "domain_context": "Manages anxiety and depression; relies on public mental health services; tracks coverage gaps"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "65+",   "income_bracket": "very_low",  "employment_type": "retired",      "immigration_status": "recent_immigrant",      "family_size": "single",       "debt_load": "low",    "domain_role": "immigrant_senior_patient",   "domain_context": "Recent immigrant senior with limited English; relies heavily on interpreter services"},
        {"city": "Edmonton",           "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "rural_healthcare_worker",    "domain_context": "Works at a regional hospital serving a large rural catchment; tracks rural access gaps"},
        {"city": "Reserve Northern Ontario", "tenure": "renter", "age_bracket": "35-49", "income_bracket": "very_low", "employment_type": "unemployed", "immigration_status": "born_here",           "family_size": "small_family", "debt_load": "high",   "domain_role": "indigenous_health_patient",  "domain_context": "Indigenous community member; relies on nursing station; tracks Jordan's Principle gaps"},
        {"city": "Montreal",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "private_clinic_user",        "domain_context": "Uses private clinic for non-emergency care; has supplementary insurance"},
        {"city": "Saskatoon",          "tenure": "renter", "age_bracket": "18-24", "income_bracket": "low",       "employment_type": "student",      "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "student_health_user",        "domain_context": "Post-secondary student; uses campus health services; tracks mental health wait times"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "disability_benefit_user",   "domain_context": "Lives with physical disability; tracks drug coverage, home care, and accessibility services"},
        {"city": "Calgary",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "established_immigrant", "family_size": "couple",       "debt_load": "low",    "domain_role": "new_parent_healthcare",      "domain_context": "New parent; relies heavily on maternal health, paediatric, and public health services"},
    ],
    "taxation_fiscal": [
        {"city": "Toronto",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "very_high", "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "high_income_earner",         "domain_context": "High-income professional; primary beneficiary or loser depending on policy structure"},
        {"city": "Vancouver",          "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "business_owner_tax",         "domain_context": "Incorporated business owner; tracks corporate and personal tax rate changes directly"},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "low_income_tax_filer",       "domain_context": "Files taxes but income too low to owe; tracks benefit clawbacks and GST/HST credits"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "capital_gains_holder",       "domain_context": "Holds significant investment portfolio; tracks capital gains inclusion rate changes"},
        {"city": "Ottawa",             "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "middle_income_earner",       "domain_context": "Middle-income salaried worker; tracks marginal rate changes and RRSP/TFSA contribution room"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "18-24", "income_bracket": "very_low",  "employment_type": "student",      "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "student_low_income",         "domain_context": "Student with minimal income; tracks tuition credits, bursaries, and GST rebates"},
        {"city": "Winnipeg",           "tenure": "owner",  "age_bracket": "65+",   "income_bracket": "medium",    "employment_type": "retired",      "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "retiree_fixed_income",       "domain_context": "Retired; income from CPP, OAS, and RRSP drawdowns; tracks tax treatment of retirement income"},
        {"city": "Vancouver",          "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "low",    "domain_role": "real_estate_investor",       "domain_context": "Owns investment properties; tracks property tax, capital gains, and landlord tax rules"},
        {"city": "Edmonton",           "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "unemployed",   "immigration_status": "established_immigrant", "family_size": "small_family", "debt_load": "high",   "domain_role": "transfer_recipient",         "domain_context": "Receives social assistance; tracks clawback rules and welfare tax interactions"},
        {"city": "Halifax",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "professional_incorporated",  "domain_context": "Incorporated professional (lawyer/accountant); tracks passive income rules and corporate tax"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "recent_immigrant",      "family_size": "small_family", "debt_load": "low",    "domain_role": "immigrant_professional",     "domain_context": "Immigrant professional; tracks foreign income, credential recognition, and tax treaties"},
        {"city": "Montreal",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "low",    "domain_role": "dual_income_household",      "domain_context": "Dual-income household; tracks income splitting rules and child benefit interactions"},
        {"city": "Northern Ontario Rural", "tenure": "owner", "age_bracket": "50-64", "income_bracket": "low",   "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "medium", "domain_role": "rural_self_employed",        "domain_context": "Rural farmer/tradesperson; tracks GST/HST input tax credits and rural tax credits"},
        {"city": "Calgary",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "first_time_saver",           "domain_context": "Early career worker; actively using TFSA and FHSA; tracks contribution room impacts"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "established_immigrant", "family_size": "single",       "debt_load": "high",   "domain_role": "gig_tax_filer",             "domain_context": "Self-employed gig worker; tracks quarterly installment requirements and deduction eligibility"},
    ],
    "criminal_justice": [
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "formerly_incarcerated",      "domain_context": "Was incarcerated; tracks re-entry support, record suspension, and employment barriers"},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "35-49", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "high",   "domain_role": "indigenous_formerly_incarcerated", "domain_context": "Indigenous; overrepresented in prison system; tracks systemic sentencing disparities"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "person_on_probation",        "domain_context": "On probation; tracks conditions, reporting requirements, and access to services"},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "established_immigrant", "family_size": "small_family", "debt_load": "medium", "domain_role": "racialized_stop_and_search",  "domain_context": "Racialized person; disproportionate police contact; tracks carding and civil liberties impacts"},
        {"city": "Ottawa",             "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "law_enforcement_officer",    "domain_context": "Police officer; tracks operational impacts of sentencing and enforcement policy changes"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "very_high", "employment_type": "self_employed", "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "victim_advocate",            "domain_context": "Crime victim; tracks restorative justice, restitution, and offender accountability mechanisms"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "defence_lawyer",             "domain_context": "Criminal defence lawyer; tracks legal aid funding, bail reform, and procedural rights"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "18-24", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "youth_at_risk",              "domain_context": "Youth in contact with justice system; tracks diversion programs and youth sentence alternatives"},
        {"city": "Halifax",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "recent_immigrant",      "family_size": "single",       "debt_load": "medium", "domain_role": "criminalized_immigrant",     "domain_context": "Non-citizen; criminal conviction could trigger deportation; tracks immigration-criminal law intersection"},
        {"city": "Montreal",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "low",    "domain_role": "prison_system_administrator", "domain_context": "Works in corrections administration; tracks staffing, capacity, and recidivism data"},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "community_corrections_worker", "domain_context": "Parole officer; tracks community supervision caseloads and reintegration resources"},
        {"city": "Toronto",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "prosecutor",                 "domain_context": "Crown prosecutor; tracks evidentiary standards, plea bargaining, and case load impacts"},
        {"city": "Reserve Northern Ontario", "tenure": "renter", "age_bracket": "25-34", "income_bracket": "very_low", "employment_type": "unemployed", "immigration_status": "born_here",           "family_size": "single",       "debt_load": "high",   "domain_role": "on_reserve_youth_justice",   "domain_context": "On-reserve youth; tracks Indigenous Peoples Courts and gladue principles application"},
        {"city": "Calgary",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "victim_services_worker",     "domain_context": "Works in victim services; tracks trauma support, court accompaniment, and compensation"},
        {"city": "Ottawa",             "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "policy_researcher_cj",       "domain_context": "Criminal justice policy researcher; tracks sentencing guidelines, recidivism, and racial disparity data"},
        # Justice-involved persons — primary population for corrections policy; drawn from
        # Correctional Investigator of Canada annual reports + Public Safety Canada recidivism stats.
        # These are NOT approximated from CHS housing microdata.
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "25-34", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "recently_released_federal",  "domain_context": "Recently released from federal custody after serving 2/3 of sentence; navigating Transitional Income Bridge, halfway house placement, and ban-the-box job search. ~70% of released federal offenders rely on social assistance within 6 months (CSC 2023)."},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "recently_released_indigenous", "domain_context": "Indigenous person recently released from federal custody; eligible for Section 84 healing lodge pathway. Indigenous people are 32% of federal inmates but 5% of the Canadian population (Correctional Investigator 2023). Tracks healing lodge capacity, cultural programming, and on-reserve reintegration support."},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "35-49", "income_bracket": "very_low",  "employment_type": "gig",          "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "on_parole_long_sentence",     "domain_context": "On parole after serving majority of a long sentence; subject to existing Parole Board of Canada timelines, not the accelerated pathway. Tracks supervision conditions, revocation risk, and the 12-month income bridge cliff effect."},
        {"city": "Edmonton",           "tenure": "renter", "age_bracket": "18-24", "income_bracket": "very_low",  "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "youth_transitioning_custody", "domain_context": "Young adult transitioning from youth custody to adult federal system; tracks continuity of education, mental health supports, and vulnerability to recidivism during the cliff-effect period post income bridge."},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "part_time",    "immigration_status": "established_immigrant", "family_size": "small_family", "debt_load": "medium", "domain_role": "formerly_incarcerated_parent", "domain_context": "Parent re-entering community after federal sentence; navigating child welfare involvement, housing instability, and employment barriers. Tracks impact of Ban the Box provision and Transitional Income Bridge on family reunification."},
    ],
    "education": [
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "18-24", "income_bracket": "low",       "employment_type": "student",      "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "undergraduate_student",      "domain_context": "Undergraduate student; tracks tuition, bursaries, and student loan repayment"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "18-24", "income_bracket": "very_low",  "employment_type": "student",      "immigration_status": "recent_immigrant",      "family_size": "single",       "debt_load": "high",   "domain_role": "international_student",      "domain_context": "International student; pays differential fees; tracks work permit and post-grad visa rules"},
        {"city": "Montreal",           "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "low",    "domain_role": "parent_school_age_children", "domain_context": "Parent of school-age children; tracks K-12 funding, class size, and special needs support"},
        {"city": "Ottawa",             "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "k12_teacher",               "domain_context": "Public school teacher; tracks salary grids, classroom conditions, and curriculum policy"},
        {"city": "Calgary",            "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "none",   "domain_role": "university_administrator",   "domain_context": "University VP Finance; tracks operating grants, tuition regulation, and research funding"},
        {"city": "Winnipeg",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "unemployed",   "immigration_status": "born_here",             "family_size": "single",       "debt_load": "high",   "domain_role": "recent_graduate_debt",       "domain_context": "Recent graduate with significant student debt; tracks repayment assistance programs"},
        {"city": "Halifax",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "established_immigrant", "family_size": "small_family", "debt_load": "medium", "domain_role": "eal_learner",               "domain_context": "Immigrant seeking language training; tracks LINC, CELPIP, and adult education funding"},
        {"city": "Reserve Northern Ontario", "tenure": "renter", "age_bracket": "25-34", "income_bracket": "very_low", "employment_type": "unemployed", "immigration_status": "born_here",           "family_size": "small_family", "debt_load": "high",   "domain_role": "first_nations_education",   "domain_context": "Indigenous person; tracks Jordan's Principle, band-operated schools, and post-secondary support"},
        {"city": "Toronto",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "low",       "employment_type": "gig",          "immigration_status": "established_immigrant", "family_size": "small_family", "debt_load": "medium", "domain_role": "immigrant_recredentialling",  "domain_context": "Foreign-trained professional; navigating credential recognition and bridging education costs"},
        {"city": "Edmonton",           "tenure": "owner",  "age_bracket": "50-64", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "couple",       "debt_load": "low",    "domain_role": "school_board_trustee",       "domain_context": "Elected school trustee; tracks provincial education grants and local levy decisions"},
        {"city": "Vancouver",          "tenure": "renter", "age_bracket": "25-34", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "early_childhood_educator",   "domain_context": "ECE worker; tracks childcare funding, wage subsidies, and regulated space availability"},
        {"city": "Saskatoon",          "tenure": "renter", "age_bracket": "18-24", "income_bracket": "low",       "employment_type": "student",      "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "rural_student",             "domain_context": "Rural student who relocated to study; tracks rural bursary and commuting cost support"},
        {"city": "Montreal",           "tenure": "renter", "age_bracket": "25-34", "income_bracket": "low",       "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "medium", "domain_role": "francophone_student",        "domain_context": "Francophone student; tracks language of instruction, minority rights, and transfer credit rules"},
        {"city": "Toronto",            "tenure": "owner",  "age_bracket": "35-49", "income_bracket": "high",      "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "small_family", "debt_load": "medium", "domain_role": "private_school_parent",      "domain_context": "Sends children to private school; tracks tax credit and voucher program implications"},
        {"city": "Halifax",            "tenure": "renter", "age_bracket": "35-49", "income_bracket": "medium",    "employment_type": "salaried",     "immigration_status": "born_here",             "family_size": "single",       "debt_load": "low",    "domain_role": "college_instructor",         "domain_context": "Community college instructor; tracks operating funding, sessional labour conditions, and enrolment"},
    ],
}

# Domain classifier — maps policy_classification.type → DOMAIN_PERSONAS key
# Housing policies use the standard PUMF panel; all others get domain injection
DOMAIN_INJECTION_MAP: dict[str, str] = {
    "drug_decriminalization": "drug_health",
    "drug_legalization": "drug_health",
    "harm_reduction": "drug_health",
    "healthcare": "healthcare",
    "pharmacare": "healthcare",
    "mental_health": "healthcare",
    "public_health": "healthcare",
    "labour": "labour_employment",
    "employment": "labour_employment",
    "minimum_wage": "labour_employment",
    "ai_automation": "labour_employment",
    "gig_economy": "labour_employment",
    "income_support": "taxation_fiscal",
    "taxation": "taxation_fiscal",
    "fiscal": "taxation_fiscal",
    "benefits": "taxation_fiscal",
    "criminal_justice": "criminal_justice",
    "policing": "criminal_justice",
    "sentencing": "criminal_justice",
    "incarceration": "criminal_justice",
    "education": "education",
    "student_aid": "education",
    "childcare": "education",
}

# Total validator panel size — all references to "50 validators" should derive from this
VALIDATOR_PANEL_SIZE = 50

# How many domain personas to inject (replaces lowest-weight PUMF agents)
DOMAIN_PERSONA_INJECT_N = 15


def _inject_domain_personas(
    agents: list[dict],
    policy_type: str,
    rng: np.random.Generator,
) -> list[dict]:
    """
    For non-housing policies: replace the 15 lowest-weight PUMF agents with
    synthetic domain personas whose primary lens matches the policy domain.
    Returns 50 agents with domain_persona=True on the injected ones.
    """
    domain_key = DOMAIN_INJECTION_MAP.get(policy_type.lower())
    if not domain_key or domain_key not in DOMAIN_PERSONAS:
        return agents  # No injection for housing or unknown domain

    persona_pool = DOMAIN_PERSONAS[domain_key]
    # Shuffle so we don't always pick the same 15
    indices = rng.permutation(len(persona_pool))[:DOMAIN_PERSONA_INJECT_N]
    selected_personas = [persona_pool[i] for i in indices]

    # Sort agents by population_weight ascending — lowest weight = most dispensable
    sorted_by_weight = sorted(range(len(agents)), key=lambda i: agents[i]["population_weight"])
    replace_indices = set(sorted_by_weight[:DOMAIN_PERSONA_INJECT_N])

    # The average weight of agents being replaced — domain personas inherit this
    avg_replaced_weight = sum(agents[i]["population_weight"] for i in replace_indices) / DOMAIN_PERSONA_INJECT_N

    new_agents = []
    persona_iter = iter(selected_personas)
    for i, agent in enumerate(agents):
        if i in replace_indices:
            p = next(persona_iter)
            new_agents.append({
                "id":                 agent["id"],  # will be reassigned later
                "city":               p["city"],
                "province":           _city_to_province(p["city"]),
                "age_bracket":        p["age_bracket"],
                "income_bracket":     p["income_bracket"],
                "tenure":             p["tenure"],
                "debt_load":          p["debt_load"],
                "family_size":        p["family_size"],
                "employment_type":    p["employment_type"],
                "immigration_status": p["immigration_status"],
                "population_weight":  avg_replaced_weight,
                "domain_persona":     True,
                "domain_role":        p["domain_role"],
                "domain_context":     p["domain_context"],
            })
        else:
            new_agents.append(agent)

    return new_agents


def _inject_generated_personas(agents: list[dict], personas: list[dict]) -> list[dict]:
    """
    Replace the lowest-weight PUMF agents with LLM-generated domain personas.
    Personas come from generate_validator_personas() in orchestrator.py.
    Each persona dict must have: city, tenure, age_bracket, income_bracket,
    employment_type, immigration_status, family_size, debt_load,
    domain_role, domain_context.
    """
    if not personas:
        return agents

    n = len(personas)
    sorted_by_weight = sorted(range(len(agents)), key=lambda i: agents[i]["population_weight"])
    replace_indices = set(sorted_by_weight[:n])
    avg_replaced_weight = sum(agents[i]["population_weight"] for i in replace_indices) / n

    valid_cities = {
        "Toronto", "Ottawa", "Hamilton", "Kitchener-Waterloo", "Sudbury",
        "Northern Ontario Rural", "Reserve Northern Ontario", "Montreal",
        "Vancouver", "Victoria", "Kelowna", "Northern BC Rural",
        "Calgary", "Edmonton", "Saskatoon", "Regina", "Winnipeg",
        "Halifax", "PEI Rural", "Nunavut Remote",
    }

    new_agents = []
    persona_iter = iter(personas)
    for i, agent in enumerate(agents):
        if i in replace_indices:
            p = next(persona_iter)
            city = p.get("city", "Toronto")
            if city not in valid_cities:
                city = "Toronto"
            new_agents.append({
                "agent_id":           agent.get("agent_id", i),
                "city":               city,
                "province":           _city_to_province(city),
                "age_bracket":        p.get("age_bracket", "25-34"),
                "income_bracket":     p.get("income_bracket", "low"),
                "tenure":             p.get("tenure", "renter"),
                "debt_load":          p.get("debt_load", "medium"),
                "family_size":        p.get("family_size", "single"),
                "employment_type":    p.get("employment_type", "gig"),
                "immigration_status": p.get("immigration_status", "born_here"),
                "population_weight":  avg_replaced_weight,
                "domain_persona":     True,
                "domain_role":        p.get("domain_role", "domain_affected_person"),
                "domain_context":     p.get("domain_context", ""),
            })
        else:
            new_agents.append(agent)

    return new_agents


def _city_to_province(city: str) -> str:
    _map = {
        "Toronto": "ON", "Ottawa": "ON", "Hamilton": "ON", "Kitchener-Waterloo": "ON",
        "Sudbury": "ON", "Northern Ontario Rural": "ON", "Reserve Northern Ontario": "ON",
        "Montreal": "QC", "Vancouver": "BC", "Victoria": "BC", "Kelowna": "BC",
        "Northern BC Rural": "BC", "Calgary": "AB", "Edmonton": "AB",
        "Saskatoon": "SK", "Regina": "SK", "Winnipeg": "MB",
        "Halifax": "NS", "PEI Rural": "PE", "Nunavut Remote": "NU",
    }
    return _map.get(city, "ON")


# ── Data loading ───────────────────────────────────────────────────────────────

_pumf_cache: pd.DataFrame | None = None

def _load_and_prepare_pumf() -> pd.DataFrame:
    global _pumf_cache
    if _pumf_cache is not None:
        return _pumf_cache

    df = pd.read_csv(PUMF_PATH)
    df = df[df["PCHN"].isin([1, 2])].copy()
    df.loc[df["PHHTTINC"] >= 99_999_999_000, "PHHTTINC"] = None
    df = df[df["PDCT_05"].isin([1, 2])].copy()

    df["income_quintile"] = pd.cut(
        df["PHHTTINC"], bins=INCOME_THRESHOLDS, labels=False, right=False,
    ).fillna(2).astype(int)

    def _age_bracket(row):
        code = row["PAGEP1"]
        if code == 1:
            return "18-24" if row["PHGEDUC"] in {1, 2} else "25-34"
        return AGE_MAP.get(code, "35-49")

    df["age_bracket"] = df.apply(_age_bracket, axis=1)

    def _family_size(n):
        if n == 1: return "single"
        if n == 2: return "couple"
        if n in {3, 4}: return "small_family"
        if n >= 5: return "large_family"
        return "couple"

    df["family_size"] = df["PHHSIZE"].apply(_family_size)
    _pumf_cache = df.reset_index(drop=True)
    return _pumf_cache


# ── Scope-aware sampling ───────────────────────────────────────────────────────

def _build_region_filter(geo_scope: dict) -> list[int]:
    """Returns CHS REGION codes to include based on geo scope."""
    scope_level = geo_scope.get("scope_level", "national")
    chs_regions = geo_scope.get("chs_regions", [1, 2, 3, 4, 5])
    if scope_level == "national":
        return [1, 2, 3, 4, 5]
    return chs_regions if chs_regions else [1, 2, 3, 4, 5]


def _build_boost_fn(sampling_config: dict, geo_scope: dict):
    """
    Returns a boost function (region, tenure, iq, age) → float
    that combines geographic scope boost with policy-type demographic boost.
    age codes: 1=18-34, 2=35-49, 3=50-64, 4=65+
    """
    tenure_boost = sampling_config.get("tenure_boost", {})
    income_boost = sampling_config.get("income_boost", {})
    region_boost = sampling_config.get("region_boost", {})
    # age_boost keys match PAGEP1 codes: 1=18-34, 2=35-49, 3=50-64, 4=65+
    age_boost    = sampling_config.get("age_boost", {})
    scope_level  = geo_scope.get("scope_level", "national")
    chs_regions  = geo_scope.get("chs_regions", [1, 2, 3, 4, 5])
    primary_regions = set(chs_regions)

    INCOME_LABEL_TO_IQ = {v: i for i, v in enumerate(INCOME_LABELS)}

    def boost(region: int, tenure: int, iq: int, age: int) -> float:
        m = 1.0

        # Geographic scope: heavily boost primary region(s)
        if scope_level == "provincial":
            if region in primary_regions:
                m *= 8.0
            else:
                m *= 0.05
        elif scope_level == "municipal":
            if region in primary_regions:
                m *= 5.0
            else:
                m *= 0.1

        if scope_level == "national" and region_boost:
            m *= region_boost.get(region, 1.0)

        # Policy-type tenure boost
        tenure_label = "renter" if tenure == 2 else "owner"
        m *= tenure_boost.get(tenure_label, 1.0)

        # Policy-type income boost
        income_label = INCOME_LABELS[min(iq, 4)]
        m *= income_boost.get(income_label, 1.0)

        # Policy-type age boost — keys are PAGEP1 int codes
        if age_boost:
            m *= age_boost.get(age, 1.0)

        # Always boost renters slightly for housing reality
        if tenure == 2:
            m *= 1.3

        # Always boost low-income slightly
        if iq in {0, 1}:
            m *= 1.2

        # Atlantic region always needs a boost (small PUMF sample)
        if region == 1:
            m *= 3.5

        return m

    return boost


def _largest_remainder(raw: dict, n: int) -> dict:
    floor = {k: int(v) for k, v in raw.items()}
    remainders = {k: raw[k] - floor[k] for k in raw}
    deficit = n - sum(floor.values())
    for k in sorted(remainders, key=lambda k: -remainders[k])[:deficit]:
        floor[k] += 1
    return floor


def _stratify_and_sample_scoped(
    df: pd.DataFrame,
    rng: np.random.Generator,
    geo_scope: dict,
    sampling_config: dict,
    n: int = 50,
) -> tuple[list[pd.Series], list[float]]:
    """
    Stratified weighted sampling across REGION × PDCT_05 × income_quintile × PAGEP1,
    with scope-aware and policy-type-aware boosting.
    """
    region_filter = _build_region_filter(geo_scope)
    scope_level   = geo_scope.get("scope_level", "national")

    # For scoped simulations: sample from scoped region primarily
    # but always keep some out-of-region for comparison diversity
    if scope_level in ("municipal", "provincial"):
        # Provincial: 95% in-region (2-3 out-of-province for contrast only)
        # Municipal: 90% in-region
        primary_pct = 0.90 if scope_level == "municipal" else 0.95
        primary_df = df[df["REGION"].isin(region_filter)]
        other_df   = df[~df["REGION"].isin(region_filter)]
        n_primary  = max(int(n * primary_pct), n - 3)
        n_other    = n - n_primary

        primary_rows, primary_weights = _sample_stratum(
            primary_df, rng, n_primary, geo_scope, sampling_config, is_primary=True
        )
        if len(other_df) > 0 and n_other > 0:
            other_rows, other_weights = _sample_stratum(
                other_df, rng, n_other, geo_scope, sampling_config, is_primary=False
            )
        else:
            other_rows, other_weights = [], []

        return primary_rows + other_rows, primary_weights + other_weights
    else:
        return _sample_stratum(df, rng, n, geo_scope, sampling_config, is_primary=True)


def _sample_stratum(
    df: pd.DataFrame,
    rng: np.random.Generator,
    n: int,
    geo_scope: dict,
    sampling_config: dict,
    is_primary: bool,
) -> tuple[list[pd.Series], list[float]]:
    if len(df) == 0 or n == 0:
        return [], []

    w = df["PFWEIGHT"]
    boost_fn = _build_boost_fn(
        sampling_config if is_primary else {"tenure_boost": {"renter": 1.5, "owner": 1.2}, "income_boost": {k: 1.0 for k in INCOME_LABELS}},
        geo_scope if is_primary else {**geo_scope, "scope_level": "national"},
    )

    cells: dict[tuple, pd.Index] = {}
    for key, group in df.groupby(["REGION", "PDCT_05", "income_quintile", "PAGEP1"], sort=False):
        cells[key] = group.index

    sparse = {k for k, idx in cells.items() if len(idx) < 3}
    cell_weights = {k: float(w[idx].sum()) for k, idx in cells.items()}

    CELL_MAX   = 3
    REGION_MAX = max(int(n * 0.35), 3)

    boosted: dict[tuple, float] = {
        k: cell_weights[k] * boost_fn(*k)
        for k in cells
        if k not in sparse
    }

    if not boosted:
        # Fallback: use all cells equally
        boosted = {k: cell_weights[k] for k in cells if k not in sparse}
    if not boosted:
        return [], []

    total_b = sum(boosted.values())
    raw_alloc = {k: min(bw / total_b * n, float(CELL_MAX)) for k, bw in boosted.items()}
    alloc: dict[tuple, int] = _largest_remainder(raw_alloc, n)

    # Enforce region cap
    for rc in [1, 2, 3, 4, 5]:
        rc_cells = [(k, alloc[k]) for k in alloc if k[0] == rc]
        rc_total = sum(v for _, v in rc_cells)
        if rc_total > REGION_MAX:
            excess = rc_total - REGION_MAX
            for k, _ in sorted(rc_cells, key=lambda x: boosted.get(x[0], 0)):
                trim = min(alloc[k] - 1, excess)
                if trim > 0:
                    alloc[k] -= trim
                    excess -= trim
                if excess <= 0:
                    break

    # Fix total
    actual = sum(alloc.values())
    diff = n - actual
    if diff != 0:
        sorted_by_boost = sorted(boosted, key=lambda k: -boosted[k])
        for k in sorted_by_boost:
            if diff == 0: break
            if diff > 0 and alloc.get(k, 0) < CELL_MAX:
                alloc[k] = alloc.get(k, 0) + 1
                diff -= 1
            elif diff < 0 and alloc.get(k, 0) > 1:
                alloc[k] -= 1
                diff += 1

    def _nearest_cell(key):
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
        cw  = cell_weights.get(key, 1.0)
        if idx is None or key in sparse:
            alt = _nearest_cell(key)
            if alt:
                idx = cells[alt]
                cw  = cell_weights[alt]
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

def _get_city_assignments(geo_scope: dict) -> dict[int, list[tuple[str, str, float]]]:
    """Returns city assignment table appropriate for the scope."""
    scope_level     = geo_scope.get("scope_level", "national")
    primary_province = geo_scope.get("primary_province")
    city_weights    = geo_scope.get("city_weights", {})

    if scope_level == "national" or not primary_province:
        return CITY_ASSIGNMENTS_NATIONAL

    # If we have explicit city weights from geo_scope, build a custom table
    if city_weights and scope_level == "municipal":
        from policy_classifier import PROVINCE_TO_REGION
        region_code = PROVINCE_TO_REGION.get(primary_province, 3)
        city_list = [(city, primary_province, weight) for city, weight in city_weights.items()]
        # Normalise
        total = sum(w for _, _, w in city_list)
        city_list = [(c, p, w / total) for c, p, w in city_list]
        return {region_code: city_list}

    # Provincial scope — use province-specific city table
    prov_cities = CITY_ASSIGNMENTS_BY_PROVINCE.get(primary_province)
    if prov_cities:
        from policy_classifier import PROVINCE_TO_REGION
        region_code = PROVINCE_TO_REGION.get(primary_province, 3)
        return {region_code: prov_cities}

    return CITY_ASSIGNMENTS_NATIONAL


def _derive_city(
    region: int,
    income_q: int,
    phtype: int,
    nunavut_taken: list[bool],
    rng: np.random.Generator,
    city_table: dict[int, list[tuple[str, str, float]]],
) -> tuple[str, str]:
    if region == 4 and income_q == 0 and not nunavut_taken[0]:
        nunavut_taken[0] = True
        return "Nunavut Remote", "NU"

    # Use scoped table if available for this region, else national
    options = city_table.get(region) or CITY_ASSIGNMENTS_NATIONAL.get(region, [("Halifax", "NS", 1.0)])
    cities  = [c for c, p, w in options]
    provs   = [p for c, p, w in options]
    probs   = np.array([w for c, p, w in options], dtype=float)

    rural_indices = [
        i for i, c in enumerate(cities)
        if any(kw in c for kw in ["Rural", "Remote", "Reserve", "Northern"])
    ]
    if rural_indices and income_q in {0, 1} and phtype in {1, 2}:
        boost = 0.05
        probs[rural_indices] += boost / len(rural_indices)
        largest = int(np.argmax(probs))
        if largest not in rural_indices:
            probs[largest] = max(0.01, probs[largest] - boost)

    probs = probs / probs.sum()
    idx = int(rng.choice(len(cities), p=probs))
    return cities[idx], provs[idx]


def _derive_debt_load(row: pd.Series) -> str:
    pdct  = int(row["PDCT_05"])
    pstir = int(row.get("PSTIR_GR", 9))
    iq    = int(row["income_quintile"])

    if pdct == 2:
        if pstir == 1: return "none"
        if pstir == 2: return "medium"
        if pstir == 3: return "high"
        return "low"

    pown20 = int(row.get("POWN_20", 9))
    if pown20 == 2: return "none"
    if pown20 == 1:
        try:
            pown80_v = int(row.get("POWN_80", 99_999_996))
        except (TypeError, ValueError):
            pown80_v = 99_999_996
        if pown80_v >= 99_999_996: return ["high", "high", "medium", "low", "low"][iq]
        if pown80_v < 90_000: return "low"
        if pown80_v <= 270_000: return "medium"
        return "high"
    return ["medium", "medium", "low", "low", "low"][iq]


def _derive_employment_type(row: pd.Series) -> str:
    pempl  = int(row.get("PEMPL", 9))
    pagep1 = int(row.get("PAGEP1", 2))
    phged  = int(row.get("PHGEDUC", 99))
    pfthb  = int(row.get("PFTHB5YR", 9))
    iq     = int(row["income_quintile"])

    if pempl == 9: return "unemployed"
    if pempl == 2:
        if pagep1 == 4: return "retired"
        if pagep1 == 1 and phged in {1, 2, 3}: return "student"
        return "unemployed"
    if pagep1 in {2, 3} and iq in {2, 3, 4} and pfthb == 2 and phged in {4, 5}: return "self_employed"
    if pagep1 == 1 and phged in {1, 2, 3}: return "gig"
    if pfthb == 1: return "salaried"
    if phged in {6, 7}: return "salaried"
    if iq in {0, 1}: return "gig"
    return "salaried"


def _derive_immigration_detail(row: pd.Series, rng: np.random.Generator) -> str:
    prspimst = int(row.get("PRSPIMST", 9))
    if prspimst != 2: return "born_here"

    pagep1 = int(row.get("PAGEP1", 2))
    if pagep1 == 1:   probs = [0.60, 0.30, 0.10]
    elif pagep1 == 2: probs = [0.20, 0.65, 0.15]
    else:             probs = [0.05, 0.90, 0.05]

    return str(rng.choice(["recent_immigrant", "established_immigrant", "refugee"], p=probs))


# ── Guaranteed slot injection ──────────────────────────────────────────────────

def _inject_guaranteed_slots(
    agents: list[dict],
    df: pd.DataFrame,
    guaranteed_slot_keys: list[str],
    geo_scope: dict,
    rng: np.random.Generator,
    city_table: dict,
) -> list[dict]:
    """
    For each guaranteed slot type, ensure at least one agent matching
    that profile exists. If not, replace a randomly chosen low-priority
    agent (owner, high-income) with a synthesised guaranteed-slot agent.
    """
    INCOME_LABEL_TO_IQ = {v: i for i, v in enumerate(INCOME_LABELS)}
    nunavut_taken = [False]

    for slot_key in guaranteed_slot_keys:
        defn = GUARANTEED_SLOT_DEFS.get(slot_key)
        if not defn:
            continue

        # Check if we already have an agent matching this slot
        force_city = defn.get("force_city")
        force_imm  = defn.get("force_imm")
        force_empl = defn.get("force_empl")
        tenure_lbl = "owner" if defn["tenure"] == 1 else "renter"

        def matches(a: dict) -> bool:
            if a["tenure"] != tenure_lbl: return False
            iq = INCOME_LABEL_TO_IQ.get(a["income_bracket"], 2)
            if not (defn["iq_range"][0] <= iq <= defn["iq_range"][1]): return False
            if force_city and a["city"] != force_city: return False
            if force_imm  and a["immigration_status"] != force_imm: return False
            if force_empl and a["employment_type"] != force_empl: return False
            return True

        if any(matches(a) for a in agents):
            continue  # Already present

        # Find a matching PUMF row
        mask = (df["PDCT_05"] == defn["tenure"])
        mask &= (df["income_quintile"] >= defn["iq_range"][0])
        mask &= (df["income_quintile"] <= defn["iq_range"][1])
        mask &= (df["PAGEP1"] >= defn["age_range"][0])
        mask &= (df["PAGEP1"] <= defn["age_range"][1])

        # For scoped panels, prefer rows from primary regions
        primary_regions = set(geo_scope.get("chs_regions", [1, 2, 3, 4, 5]))
        scoped_mask = mask & df["REGION"].isin(primary_regions)
        candidates = df[scoped_mask] if scoped_mask.sum() > 0 else df[mask]

        if len(candidates) == 0:
            continue  # Can't guarantee this slot from available data

        row = candidates.sample(1, random_state=int(rng.integers(0, 10000))).iloc[0]
        iq  = int(row["income_quintile"])

        if force_city:
            city, province = force_city, _city_to_province(force_city)
        else:
            region = int(row["REGION"])
            city, province = _derive_city(region, iq, int(row.get("PHTYPE", 99)), nunavut_taken, rng, city_table)

        empl = force_empl if force_empl else _derive_employment_type(row)
        imm  = force_imm  if force_imm  else _derive_immigration_detail(row, rng)

        new_agent = {
            "id":               0,  # will be reassigned
            "city":             city,
            "province":         province,
            "age_bracket":      str(row["age_bracket"]),
            "income_bracket":   INCOME_LABELS[iq],
            "tenure":           tenure_lbl,
            "debt_load":        _derive_debt_load(row),
            "family_size":      str(row["family_size"]),
            "employment_type":  empl,
            "immigration_status": imm,
            "population_weight": 0.0,  # will be redistributed
            "guaranteed_slot":  slot_key,
        }

        # Replace a low-priority agent (owner, high-income, no guaranteed slot)
        replaceable = [
            i for i, a in enumerate(agents)
            if a["tenure"] == "owner"
            and a.get("income_bracket") in ("high", "very_high")
            and not a.get("guaranteed_slot")
        ]
        if replaceable:
            idx_replace = int(rng.choice(replaceable))
            stolen_weight = agents[idx_replace]["population_weight"]
            agents[idx_replace] = new_agent
            new_agent["population_weight"] = stolen_weight
        else:
            # Fallback: append (will be trimmed to 50 later)
            agents.append(new_agent)

    return agents


def _city_to_province(city: str) -> str:
    _MAP = {
        "Toronto": "ON", "Ottawa": "ON", "Hamilton": "ON",
        "Kitchener-Waterloo": "ON", "Sudbury": "ON",
        "Northern Ontario Rural": "ON", "Reserve Northern Ontario": "ON",
        "Montreal": "QC", "Vancouver": "BC", "Victoria": "BC",
        "Kelowna": "BC", "Northern BC Rural": "BC",
        "Calgary": "AB", "Edmonton": "AB", "Saskatoon": "SK",
        "Regina": "SK", "Winnipeg": "MB", "Halifax": "NS",
        "PEI Rural": "PE", "Nunavut Remote": "NU",
    }
    return _MAP.get(city, "ON")


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_agents(agents: list[dict]) -> None:
    if len(agents) != VALIDATOR_PANEL_SIZE:
        raise ValueError(f"Expected {VALIDATOR_PANEL_SIZE} agents, got {len(agents)}")

    ids = [a["id"] for a in agents]
    if len(set(ids)) != VALIDATOR_PANEL_SIZE:
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

    n_renters   = sum(1 for a in agents if a["tenure"] == "renter")
    n_immigrant = sum(1 for a in agents if a["immigration_status"] != "born_here")
    if n_renters < 12:
        warnings.warn(f"Only {n_renters} renters — may underrepresent rental stress")
    if n_immigrant < 3:
        warnings.warn(f"Only {n_immigrant} immigrant agents — very low immigrant representation")


# ── Main generation function ───────────────────────────────────────────────────

def generate_agents(
    n: int = 50,
    seed: int | None = None,
    policy_classification: dict | None = None,
) -> list[dict]:
    """
    Generates n demographically representative agents from CHS 2022 PUMF.
    If policy_classification is provided, scopes the panel to the policy's
    geography and type. Otherwise falls back to national distribution.

    seed=None → random seed each call (different panel per simulation).
    seed=42   → deterministic (for caching/testing).
    """
    if seed is None:
        seed = int(np.random.default_rng().integers(0, 2**31))
    rng = np.random.default_rng(seed)

    df = _load_and_prepare_pumf()

    # Extract scope config from classification
    geo_scope       = {}
    sampling_config = {}
    panel_scope_summary = "national"

    if policy_classification:
        geo_scope       = policy_classification.get("geo_scope", {})
        sampling_config = policy_classification.get("sampling_config", {})
        scope_level     = geo_scope.get("scope_level", "national")
        detected_cities = geo_scope.get("detected_cities", [])
        primary_province = geo_scope.get("primary_province")

        if scope_level == "municipal" and detected_cities:
            panel_scope_summary = f"municipal ({', '.join(detected_cities[:2])})"
        elif scope_level == "provincial" and primary_province:
            panel_scope_summary = f"provincial ({primary_province})"

    if not sampling_config:
        sampling_config = {
            "tenure_boost": {"renter": 2.0, "owner": 1.0},
            "income_boost": {"very_low": 2.0, "low": 1.8, "medium": 1.4, "high": 1.0, "very_high": 0.8},
            "guaranteed_slots": ["indigenous_renter", "senior_renter", "recent_immigrant_renter"],
        }
    if not geo_scope:
        geo_scope = {"scope_level": "national", "chs_regions": [1, 2, 3, 4, 5], "city_weights": {}}

    city_table = _get_city_assignments(geo_scope)

    rows, cell_weights = _stratify_and_sample_scoped(df, rng, geo_scope, sampling_config, n)

    if len(rows) < n:
        # Fallback: pad with national sampling
        fallback_rows, fallback_weights = _sample_stratum(
            df, rng, n - len(rows),
            {"scope_level": "national", "chs_regions": [1, 2, 3, 4, 5]},
            sampling_config, is_primary=False,
        )
        rows += fallback_rows
        cell_weights += fallback_weights

    # Trim to exactly n
    rows = rows[:n]
    cell_weights = cell_weights[:n]

    total_weight = sum(cell_weights)
    nunavut_taken = [False]

    RURAL_GUARANTEES = {3: "Northern Ontario Rural", 4: "Nunavut Remote", 5: "Northern BC Rural"}
    rural_region_assigned: dict[int, bool] = {r: False for r in RURAL_GUARANTEES}
    reserve_assigned = [False]

    agents: list[dict] = []
    for i, (row, cw) in enumerate(zip(rows, cell_weights)):
        region      = int(row["REGION"])
        iq          = int(row["income_quintile"])
        phtype      = int(row.get("PHTYPE", 99))
        tenure_code = int(row["PDCT_05"])

        # Guarantee rural/reserve slots (only for national/provincial scope)
        forced_city = None
        forced_prov = None
        scope_level = geo_scope.get("scope_level", "national")
        if scope_level == "national":
            if (region == 3 and iq in {0, 1} and tenure_code == 2 and not reserve_assigned[0]):
                forced_city, forced_prov = "Reserve Northern Ontario", "ON"
                reserve_assigned[0] = True
            elif (region in RURAL_GUARANTEES and iq in {0, 1} and not rural_region_assigned.get(region, True)):
                forced_city = RURAL_GUARANTEES[region]
                forced_prov = "NU" if forced_city == "Nunavut Remote" else REGION_TO_PROVINCE[region]
                rural_region_assigned[region] = True
                if forced_city == "Nunavut Remote":
                    nunavut_taken[0] = True

        if forced_city:
            city, province = forced_city, forced_prov
        else:
            city, province = _derive_city(region, iq, phtype, nunavut_taken, rng, city_table)

        agent = {
            "id":               i + 1,
            "city":             city,
            "province":         province,
            "age_bracket":      str(row["age_bracket"]),
            "income_bracket":   INCOME_LABELS[iq],
            "tenure":           "owner" if tenure_code == 1 else "renter",
            "debt_load":        _derive_debt_load(row),
            "family_size":      str(row["family_size"]),
            "employment_type":  _derive_employment_type(row),
            "immigration_status": _derive_immigration_detail(row, rng),
            "population_weight": round(cw / total_weight, 4),
        }
        agents.append(agent)

    # Inject guaranteed slots for policy-specific demographics
    guaranteed_slot_keys = sampling_config.get("guaranteed_slots", [])
    if guaranteed_slot_keys:
        agents = _inject_guaranteed_slots(agents, df, guaranteed_slot_keys, geo_scope, rng, city_table)

    # Trim back to n if injection added extras
    agents = agents[:n]

    # Reassign IDs sequentially
    for i, a in enumerate(agents):
        a["id"] = i + 1

    # Normalize weights to sum to 1.0
    w_sum = sum(a["population_weight"] for a in agents)
    if w_sum > 0:
        for a in agents:
            a["population_weight"] = round(a["population_weight"] / w_sum, 4)
    # Fix rounding residual
    w_sum2 = sum(a["population_weight"] for a in agents)
    if abs(w_sum2 - 1.0) > 0.0001:
        largest_i = max(range(len(agents)), key=lambda i: agents[i]["population_weight"])
        agents[largest_i]["population_weight"] = round(
            agents[largest_i]["population_weight"] + (1.0 - w_sum2), 4
        )

    # Domain persona injection is now handled by orchestrator.py via generate_validator_personas()
    # which calls _inject_generated_personas() after the PUMF panel is built here.
    # The old lookup-table _inject_domain_personas() is no longer called.
        # Re-normalize weights after injection
        w_sum = sum(a["population_weight"] for a in agents)
        if w_sum > 0:
            for a in agents:
                a["population_weight"] = round(a["population_weight"] / w_sum, 4)
        # Fix rounding residual again
        w_sum2 = sum(a["population_weight"] for a in agents)
        if abs(w_sum2 - 1.0) > 0.0001:
            largest_i = max(range(len(agents)), key=lambda i: agents[i]["population_weight"])
            agents[largest_i]["population_weight"] = round(
                agents[largest_i]["population_weight"] + (1.0 - w_sum2), 4
            )

    # Minimum renter floor — housing-adjacent policies must keep ≥30% renters
    # to avoid thinning out the primary affected population.
    # Environment/climate policies that include housing mechanisms (retrofit, levy
    # on heating) are housing-adjacent; enforce the floor for them too.
    _housing_adjacent = {"housing", "rent_control", "zoning", "supply", "tenant_protection",
                         "affordable_housing", "social_housing", "housing_allowance", "environment"}
    if policy_type.lower() in _housing_adjacent:
        renter_count = sum(1 for a in agents if a.get("tenure") == "renter")
        renter_pct = renter_count / len(agents)
        if renter_pct < 0.30:
            # How many renters do we need to add to reach 30%?
            target_renters = int(0.30 * len(agents))
            shortfall = target_renters - renter_count
            # Swap out the lowest-weight owners (non-domain-persona) for renter equivalents
            owner_indices = [
                i for i, a in enumerate(agents)
                if a.get("tenure") == "owner" and not a.get("domain_persona")
            ]
            owner_indices.sort(key=lambda i: agents[i]["population_weight"])
            swapped = 0
            for idx in owner_indices:
                if swapped >= shortfall:
                    break
                agents[idx] = {**agents[idx], "tenure": "renter"}
                swapped += 1

    _validate_agents(agents)

    # Attach scope metadata (passed to frontend for display)
    for a in agents:
        a["panel_scope"] = panel_scope_summary

    return agents


def load_or_generate_agents(
    cache_path: str = CACHE_PATH,
    n: int = 50,
    seed: int = 42,
    policy_classification: dict | None = None,
) -> list[dict] | None:
    """
    For per-simulation dynamic panels: always generate fresh (no cache).
    For the static fallback cache: use cache when policy_classification is None.
    """
    if policy_classification is not None:
        # Dynamic per-simulation panel — always fresh, no cache
        try:
            return generate_agents(n, seed=None, policy_classification=policy_classification)
        except Exception as e:
            print(f"[agent_generator] Dynamic generation failed ({e}), falling back", flush=True)
            return None

    # Static fallback path (used when classification not available)
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                data = json.load(f)
            if data.get("n") == n and data.get("seed") == seed:
                agents = data["agents"]
                if len(agents) == n:
                    print(f"[agent_generator] Loaded {n} agents from cache", flush=True)
                    return agents
        except Exception as e:
            print(f"[agent_generator] Cache read failed ({e}), regenerating", flush=True)

    try:
        print("[agent_generator] Generating static agents from CHS 2022 PUMF...", flush=True)
        agents = generate_agents(n, seed)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        cache_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": n, "seed": seed, "pumf_rows_used": 37102, "agents": agents,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        print(f"[agent_generator] {n} agents generated and cached", flush=True)
        return agents
    except Exception as e:
        print(f"[agent_generator] Generation failed ({e})", flush=True)
        return None


if __name__ == "__main__":
    from collections import Counter

    print("=== NATIONAL PANEL ===")
    agents = generate_agents(50, seed=42)
    print(f"Renters: {sum(1 for a in agents if a['tenure']=='renter')}")
    print(f"Cities: {dict(Counter(a['city'] for a in agents))}")

    print("\n=== TORONTO MUNICIPAL PANEL (housing policy) ===")
    mock_classification = {
        "type": "supply",
        "geo_scope": {
            "scope_level": "municipal",
            "detected_cities": ["Toronto"],
            "detected_provinces": ["ON"],
            "primary_province": "ON",
            "chs_regions": [3],
            "city_weights": {"Toronto": 0.70, "Ottawa": 0.10, "Hamilton": 0.10, "Kitchener-Waterloo": 0.10},
        },
        "sampling_config": {
            "tenure_boost": {"renter": 2.5, "owner": 1.0},
            "income_boost": {"very_low": 2.5, "low": 2.0, "medium": 1.2, "high": 0.8, "very_high": 0.5},
            "guaranteed_slots": ["indigenous_renter", "senior_renter", "recent_immigrant_renter", "youth_renter"],
        },
    }
    agents_toronto = generate_agents(50, policy_classification=mock_classification)
    print(f"Renters: {sum(1 for a in agents_toronto if a['tenure']=='renter')}")
    print(f"Cities: {dict(Counter(a['city'] for a in agents_toronto))}")
    print(f"Guaranteed slots: {[a.get('guaranteed_slot') for a in agents_toronto if a.get('guaranteed_slot')]}")
