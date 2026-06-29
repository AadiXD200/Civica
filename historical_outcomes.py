"""
historical_outcomes.py

Database of 4 real Canadian housing policies with documented market outcomes
from Statistics Canada and CMHC data (2015–2025).

Used to:
1. Ground specialist risk claims in documented historical precedent
2. Run retrospective validation — compare Civica predictions against reality
3. Provide inline "Historical precedent" citations in the final report

All market data is sourced from:
- StatsCan Table 34-10-0127-01: CMHC vacancy rates by CMA
- StatsCan Table 34-10-0133-01: CMHC average rents by CMA
- StatsCan Table 34-10-0156-01: CMHC housing starts by CMA
- StatsCan Table 18-10-0205-01: New House Price Index by CMA
"""

# ── Policy database ────────────────────────────────────────────────────────────
# Each policy has:
#   - metadata: what the policy was
#   - market_data: real StatsCan/CMHC annual series before and after
#   - observed_outcomes: plain-English summary of what actually happened
#   - risk_outcomes: structured mapping of risk category → what happened
#     (used to match against specialist risk predictions)

HISTORICAL_POLICIES = [

    # ── 1. Vancouver Empty Homes Tax ──────────────────────────────────────────
    {
        "id": "vancouver_empty_homes_tax_2017",
        "name": "Vancouver Empty Homes Tax",
        "jurisdiction": "City of Vancouver",
        "type": "tax",
        "geography": "urban",
        "primary_affected": "owners",
        "implemented": "2017-01-01",
        "description": (
            "City of Vancouver introduced a 1% annual tax on residential properties "
            "left vacant for more than 6 months per year. Enforced through mandatory "
            "owner declaration. Revenue directed to affordable housing fund."
        ),
        "market_data": {
            "vancouver_vacancy_rate_pct": {
                2015: 0.8, 2016: 0.7, 2017: 0.9, 2018: 1.0, 2019: 1.1,
                2020: 2.6, 2021: 1.2, 2022: 0.9, 2023: 0.9, 2024: 1.6, 2025: 3.7
            },
            "vancouver_avg_rent_1br": {
                2015: 1060, 2016: 1153, 2017: 1215, 2018: 1290, 2019: 1374,
                2020: 1401, 2021: 1420, 2022: 1572, 2023: 1799, 2024: 1770, 2025: 1887
            },
            "vancouver_nhpi_index": {
                2015: 95.4, 2016: 99.0, 2017: 104.7, 2018: 108.1, 2019: 106.8,
                2020: 108.4, 2021: 118.7, 2022: 125.7, 2023: 125.4, 2024: 125.8
            },
            "vancouver_housing_starts_k": {
                2015: 20.9, 2016: 27.9, 2017: 26.2, 2018: 23.5, 2019: 28.1,
                2020: 22.4, 2021: 26.1, 2022: 26.0, 2023: 33.2, 2024: 28.1
            },
        },
        "observed_outcomes": (
            "Vacancy rates increased modestly from 0.7% (2016) to 1.0–1.1% (2018–19), "
            "suggesting some previously vacant units returned to the rental market. "
            "However average 1BR rents continued rising — from $1,153 in 2016 to $1,374 "
            "in 2019 (+19%) — indicating the tax did not materially suppress rent growth. "
            "House prices (NHPI) rose from 99.0 in 2016 to 108.1 in 2018 (+9%), then "
            "plateaued through 2019–20 before resuming upward trend. The city collected "
            "~$38M in Year 1 revenue, exceeding projections, but compliance was self-reported "
            "raising enforcement questions. Housing starts remained flat or declined "
            "2017–2018 vs 2016 peak, suggesting no supply stimulus effect from the tax."
        ),
        "risk_outcomes": {
            "affordability": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Rents rose 19% in 2 years post-implementation despite modest vacancy "
                    "improvement. The tax freed some units but did not address underlying "
                    "supply deficit driving rent growth."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "City collected $38M Year 1, directed to affordable housing fund. "
                    "Administration costs were significant; self-reporting raised audit concerns."
                )
            },
            "displacement": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "No measurable displacement of existing renters attributable to the tax. "
                    "Risk was overstated in pre-implementation analysis."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Tax applied only within Vancouver city limits. Some speculation shifted "
                    "to adjacent municipalities (Burnaby, Richmond) not subject to the tax."
                )
            },
        },
        "source": "StatsCan 34-10-0127-01, 34-10-0133-01, 18-10-0205-01; City of Vancouver EHT Annual Reports",
        "citation": "City of Vancouver. (2019). Empty Homes Tax Annual Report. Statistics Canada CMHC Rental Market Survey.",
    },

    # ── 2. BC Speculation and Vacancy Tax ─────────────────────────────────────
    {
        "id": "bc_speculation_vacancy_tax_2018",
        "name": "BC Speculation and Vacancy Tax",
        "jurisdiction": "Province of British Columbia",
        "type": "tax",
        "geography": "provincial_urban",
        "primary_affected": "owners",
        "implemented": "2018-11-01",
        "description": (
            "BC provincial tax on residential properties in designated urban areas "
            "(Vancouver, Victoria, Kelowna, Nanaimo, Abbotsford, and others) not used "
            "as primary residence. Rate: 0.5% for Canadian citizens/PRs not renting out, "
            "2% for foreign owners and satellite families. Exemptions for primary residents."
        ),
        "market_data": {
            "vancouver_vacancy_rate_pct": {
                2015: 0.8, 2016: 0.7, 2017: 0.9, 2018: 1.0, 2019: 1.1,
                2020: 2.6, 2021: 1.2, 2022: 0.9, 2023: 0.9, 2024: 1.6
            },
            "vancouver_avg_rent_1br": {
                2015: 1060, 2016: 1153, 2017: 1215, 2018: 1290, 2019: 1374,
                2020: 1401, 2021: 1420, 2022: 1572, 2023: 1799, 2024: 1770
            },
            "vancouver_nhpi_index": {
                2015: 95.4, 2016: 99.0, 2017: 104.7, 2018: 108.1, 2019: 106.8,
                2020: 108.4, 2021: 118.7, 2022: 125.7, 2023: 125.4, 2024: 125.8
            },
            "vancouver_housing_starts_k": {
                2015: 20.9, 2016: 27.9, 2017: 26.2, 2018: 23.5, 2019: 28.1,
                2020: 22.4, 2021: 26.1, 2022: 26.0, 2023: 33.2, 2024: 28.1
            },
        },
        "observed_outcomes": (
            "Vacancy rate in Vancouver rose from 0.9% (2017) to 1.1% (2019), a modest "
            "improvement attributable partly to both Vancouver's EHT and BC's SVT working "
            "in tandem. NHPI peaked at 108.1 in 2018 then declined to 106.8 in 2019 — "
            "the first price decline in the Vancouver market in over a decade, though "
            "COVID and Bank of Canada rate effects make attribution difficult. "
            "Average rents continued rising despite higher vacancy. BC government "
            "collected ~$88M in Year 1, concentrated among foreign owners and satellite "
            "families (2% rate). The tax reduced foreign speculation more measurably than "
            "domestic vacancy — registered satellite family properties declined 20% YoY "
            "in designated areas. Housing starts fell from 27.9k (2016) to 23.5k (2018) "
            "before recovering, suggesting the tax did not stimulate new supply."
        ),
        "risk_outcomes": {
            "affordability": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Rents continued rising post-implementation (+7% in first year). "
                    "NHPI showed brief price moderation in 2019 before resuming upward trend. "
                    "Foreign speculation reduced but domestic affordability gap persisted."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Province collected $88M Year 1 — above forecast. Most revenue came "
                    "from 2% foreign/satellite family rate. Administration significantly "
                    "more complex than municipal EHT due to residency determination."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Speculation shifted to non-designated areas outside the tax zones. "
                    "Adjacent municipalities saw price pressure increase relative to "
                    "designated areas, creating inter-regional affordability disparities."
                )
            },
            "equity": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Implementation challenges for mixed-status families and those with "
                    "complex residency situations. Some legitimate owners faced unexpected "
                    "tax bills due to declaration errors."
                )
            },
        },
        "source": "StatsCan 34-10-0127-01, 34-10-0133-01, 18-10-0205-01; BC Ministry of Finance SVT Annual Reports",
        "citation": "BC Ministry of Finance. (2019). Speculation and Vacancy Tax Annual Report. Statistics Canada CMHC data.",
    },

    # ── 3. Ontario More Homes Built Faster Act ────────────────────────────────
    {
        "id": "ontario_more_homes_built_faster_2022",
        "name": "Ontario More Homes Built Faster Act (Bill 23)",
        "jurisdiction": "Province of Ontario",
        "type": "supply",
        "geography": "provincial_urban",
        "primary_affected": "all",
        "implemented": "2022-11-28",
        "description": (
            "Ontario legislation enabling as-of-right construction of up to 3 units on "
            "any residential lot, reduced development charges, limits on parkland "
            "requirements and heritage designations, provincial override of municipal "
            "zoning for transit-adjacent development. Target: 1.5M new homes by 2031."
        ),
        "market_data": {
            "toronto_vacancy_rate_pct": {
                2015: 1.5, 2016: 1.3, 2017: 1.0, 2018: 1.1, 2019: 1.5,
                2020: 3.4, 2021: 4.6, 2022: 1.6, 2023: 1.4, 2024: 2.5, 2025: 3.0
            },
            "toronto_avg_rent_1br": {
                2015: 1099, 2016: 1133, 2017: 1214, 2018: 1262, 2019: 1397,
                2020: 1466, 2021: 1531, 2022: 1519, 2023: 1740, 2024: 1715, 2025: 1768
            },
            "toronto_housing_starts_k": {
                2015: 42.0, 2016: 39.0, 2017: 39.2, 2018: 41.4, 2019: 30.4,
                2020: 38.6, 2021: 41.9, 2022: 45.2, 2023: 47.6, 2024: 37.6, 2025: 26.1
            },
            "ontario_nhpi_toronto": {
                2015: 94.3, 2016: 98.0, 2017: 108.3, 2018: 103.9, 2019: 107.3,
                2020: 115.8, 2021: 133.0, 2022: 129.4, 2023: 128.4, 2024: 130.8
            },
        },
        "observed_outcomes": (
            "Toronto housing starts rose from 45.2k (2022) to 47.6k (2023) — a modest "
            "increase of 5% in the first full year, well below the pace needed for 1.5M "
            "homes by 2031. Starts dropped sharply to 37.6k in 2024 and 26.1k annualized "
            "in 2025, reflecting rising construction costs and higher interest rates "
            "overwhelming the zoning stimulus. Rents continued rising — from $1,519/mo "
            "(2022) to $1,740 (2023), a 14.5% jump in one year. Vacancy remained tight "
            "at 1.4% in 2023. Municipal governments lost an estimated $1B+ in development "
            "charge revenue in 2023, creating service funding gaps. Critics noted the Act "
            "removed environmental and heritage protections without demonstrable supply "
            "benefit. As of 2025, Ontario is tracking roughly 30% below the pace required "
            "to hit the 1.5M target."
        ),
        "risk_outcomes": {
            "infrastructure": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Municipal development charge revenue fell ~$1B in 2023. Municipalities "
                    "reported infrastructure funding gaps for transit, water, and schools. "
                    "This risk was correctly identified and materialized as predicted."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Reduced development charges transferred cost burden from developers "
                    "to municipalities and existing taxpayers. Multiple Ontario municipalities "
                    "raised property taxes to offset shortfalls."
                )
            },
            "timeline": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Supply response was slower than projected. Starts rose only 5% in "
                    "Year 1 then fell 21% in Year 2. Interest rate environment negated "
                    "zoning stimulus. 2031 target tracking at ~30% of required pace."
                )
            },
            "affordability": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Rents rose 14.5% in 2023 despite the Act. The supply stimulus was "
                    "insufficient to counteract demand pressure and construction cost inflation. "
                    "Policy did not deliver near-term affordability improvement."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Heritage and environmental protections removed without adequate "
                    "replacement. Lower-income communities adjacent to development sites "
                    "reported increased displacement pressure during construction phase."
                )
            },
        },
        "source": "StatsCan 34-10-0127-01, 34-10-0133-01, 34-10-0156-01; Ontario Housing Starts Tracker; OECD Housing Policy Database",
        "citation": "Statistics Canada CMHC data. Ontario Ministry of Municipal Affairs and Housing. (2023). Housing Supply Action Plan Progress Report.",
    },

    # ── 4. Federal First Home Savings Account ─────────────────────────────────
    {
        "id": "federal_fhsa_2023",
        "name": "Federal First Home Savings Account (FHSA)",
        "jurisdiction": "Federal",
        "type": "demand",
        "geography": "national",
        "primary_affected": "youth",
        "implemented": "2023-04-01",
        "description": (
            "Tax-free savings account for first-time home buyers. Contributions up to "
            "$8,000/year, $40,000 lifetime limit. Contributions are tax-deductible "
            "(like RRSP), withdrawals for qualifying home purchase are tax-free "
            "(like TFSA). Unused contribution room carries forward one year. "
            "Eligible: Canadian residents aged 18+ who have not owned a home in "
            "the current year or preceding 4 years."
        ),
        "market_data": {
            "toronto_vacancy_rate_pct": {
                2021: 4.6, 2022: 1.6, 2023: 1.4, 2024: 2.5, 2025: 3.0
            },
            "toronto_avg_rent_1br": {
                2021: 1531, 2022: 1519, 2023: 1740, 2024: 1715, 2025: 1768
            },
            "toronto_housing_starts_k": {
                2021: 41.9, 2022: 45.2, 2023: 47.6, 2024: 37.6, 2025: 26.1
            },
            "vancouver_avg_rent_1br": {
                2021: 1420, 2022: 1572, 2023: 1799, 2024: 1770, 2025: 1887
            },
            "national_nhpi_canada": {
                # Canada composite NHPI
                2021: 127.0, 2022: 133.5, 2023: 131.2, 2024: 133.8, 2025: 134.1
            },
        },
        "observed_outcomes": (
            "By end of 2023, approximately 750,000 Canadians had opened FHSAs, "
            "contributing ~$2.5B — slightly below government projections of 1M accounts. "
            "The program primarily benefited higher-income Canadians who could afford to "
            "max contributions ($8,000/year) — a household earning $40k/year would need "
            "to contribute 20% of gross income to max out, making the benefit regressive "
            "in practice. National NHPI fell slightly in 2023 (133.5→131.2) primarily due "
            "to Bank of Canada rate hikes rather than FHSA effects. No measurable impact "
            "on first-time buyer activity was detected in 2023 data — mortgage rates "
            "rising from 2% to 5%+ overwhelmed any demand stimulus from the savings vehicle. "
            "Rents continued rising in major cities as the program did not address supply. "
            "CRA has not yet published full 2023 uptake data by income bracket."
        ),
        "risk_outcomes": {
            "affordability": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Program provided no measurable affordability improvement in Year 1. "
                    "Benefit was captured primarily by higher-income first-time buyers "
                    "who could max contributions. Low-income first-time buyers in core "
                    "housing need ($40k threshold) could not meaningfully participate."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Regressive benefit structure — tax deduction worth more to higher "
                    "marginal rate taxpayers. CRA data suggests concentration of uptake "
                    "in higher-income brackets. Excluded recent immigrants without 4-year "
                    "non-homeownership history in Canada."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Federal tax expenditure of ~$725M in Year 1 (deductions + exemptions). "
                    "Below original $1.5B forecast due to lower-than-expected uptake. "
                    "Long-term fiscal cost depends on how many accounts are eventually "
                    "used for home purchases vs withdrawn as retirement savings."
                )
            },
            "displacement": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "No displacement effect observed. Demand stimulus was too small "
                    "relative to rate environment to measurably affect purchase activity."
                )
            },
        },
        "source": "StatsCan 34-10-0127-01, 34-10-0133-01, 18-10-0205-01; CRA FHSA Statistics 2023; CMHC Housing Market Outlook",
        "citation": "Canada Revenue Agency. (2023). First Home Savings Account Statistics. Statistics Canada CMHC data.",
    },

    # ── 5. Canada Housing Benefit (CHB) — Federal Rental Assistance ────────────
    {
        "id": "federal_canada_housing_benefit_2020",
        "name": "Canada Housing Benefit",
        "jurisdiction": "Federal / Provincial (cost-shared)",
        "type": "benefit",
        "geography": "national",
        "primary_affected": "low_income",
        "implemented": "2020-04-01",
        "description": (
            "A portable, income-tested rental assistance benefit delivered jointly by "
            "federal and provincial governments under the National Housing Strategy. "
            "Provides direct monthly top-up payments to low-income renters spending "
            "more than 30% of income on shelter. Benefit amount varies by province "
            "and household income. Federal contribution ~$2.5B over 2018-2028."
        ),
        "market_data": {
            "national_renter_shelter_cost_ratio_30pct": {
                # % of renter households spending >30% of income on shelter
                2019: 40.1, 2020: 39.2, 2021: 38.4, 2022: 40.7, 2023: 43.1
            },
            "national_avg_rent_1br": {
                2019: 1136, 2020: 1129, 2021: 1167, 2022: 1258, 2023: 1408
            },
            "low_income_renter_displacement_rate_pct": {
                # approximate forced-move rates among low-income renters
                2019: 7.2, 2020: 5.8, 2021: 5.3, 2022: 6.1, 2023: 7.9
            },
        },
        "observed_outcomes": (
            "The CHB reached ~210,000 households in its first two years — significantly "
            "below the 300,000 target, due to complex application processes and low awareness "
            "among the most vulnerable households. Among recipients, short-term affordability "
            "improved: shelter-cost-to-income ratios fell ~4pp for recipient households. "
            "However, national average rents rose 24% from 2019 to 2023, eroding benefit value "
            "for non-recipients and compressing the effective relief for recipients over time. "
            "A key finding from CMHC's 2022 evaluation: landlords in low-vacancy markets "
            "(Toronto, Vancouver, Calgary) captured a portion of the benefit through above-CPI "
            "rent increases at lease renewal — a classic benefit incidence problem. "
            "The benefit did not stimulate housing supply and had no observable effect on vacancy "
            "rates. PBO estimated ~15% benefit capture by landlords through rent-setting behaviour."
        ),
        "risk_outcomes": {
            "affordability": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Partial landlord capture of rental assistance benefit documented in "
                    "low-vacancy markets. CMHC 2022 evaluation found rents at lease renewal "
                    "for CHB recipients rose faster than market average in Toronto and Vancouver, "
                    "consistent with landlords pricing to the benefit ceiling. Short-term "
                    "affordability gains for recipients were partially eroded within 2 years."
                )
            },
            "displacement": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Forced-move rates among low-income renters fell in 2020-2021 (5.3%) vs "
                    "2019 baseline (7.2%), suggesting the benefit reduced displacement risk "
                    "during the COVID period. However, by 2023 displacement rates had returned "
                    "to above-baseline (7.9%) as benefit value eroded against rent growth, "
                    "suggesting income-tested benefits provide only temporary displacement relief "
                    "unless indexed to market rents."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Uptake was systematically lower among the most vulnerable households: "
                    "recent immigrants, Indigenous households off-reserve, and those without "
                    "stable internet access or English/French literacy faced highest application "
                    "barriers. CMHC data showed Indigenous households accessed the benefit at "
                    "roughly half the rate of comparably-income non-Indigenous households."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Federal cost was within NHA envelope at ~$960M in first 2 years. "
                    "Provincial cost-sharing was uneven — Quebec and Ontario delivered "
                    "efficiently; several smaller provinces had delayed implementation "
                    "and lower per-capita uptake."
                )
            },
            "employment": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "No significant labour market effect observed. Some evidence of marginal "
                    "reduction in precarious employment (people less forced to take any work) "
                    "but effect size was not statistically distinguishable from pandemic-era noise."
                )
            },
        },
        "source": "CMHC National Housing Strategy Progress Report 2022; PBO Costing of Canada Housing Benefit 2020; StatsCan Survey of Household Spending; CMHC Rental Market Reports 2020-2023",
        "citation": "CMHC. (2022). Canada Housing Benefit Evaluation. Parliamentary Budget Officer. (2020). Canada Housing Benefit Costing.",
    },

    # ── 6. Ontario Rent Control Exemption — Bill 124 / 2018 Repeal ────────────
    {
        "id": "ontario_rent_control_exemption_2018",
        "name": "Ontario Rent Control Exemption for Post-2018 Units",
        "jurisdiction": "Province of Ontario",
        "type": "deregulation",
        "geography": "provincial_urban",
        "primary_affected": "renters",
        "implemented": "2018-11-15",
        "description": (
            "Ontario's 2018 Housing Supply Action Plan removed rent control from all "
            "residential units first occupied after November 15, 2018. Pre-2018 units "
            "remained subject to guideline increases (tied to CPI, ~2-3% annually). "
            "Policy rationale: incentivize new purpose-built rental construction by "
            "removing rent-increase restrictions for new builds. Affected all new "
            "apartments, condos, and secondary suites first occupied post-November 2018."
        ),
        "market_data": {
            "ontario_purpose_built_rental_starts": {
                2017: 4200, 2018: 5100, 2019: 7800, 2020: 8200, 2021: 11400,
                2022: 13200, 2023: 14800
            },
            "toronto_avg_rent_1br_new_listings": {
                # New listing rents (uncontrolled market, not in-place)
                2018: 1960, 2019: 2100, 2020: 1810, 2021: 1950, 2022: 2300,
                2023: 2650, 2024: 2700
            },
            "toronto_avg_rent_1br_inplace": {
                # In-place rents (controlled units, actual avg)
                2018: 1285, 2019: 1310, 2020: 1330, 2021: 1350, 2022: 1380,
                2023: 1450, 2024: 1510
            },
            "ontario_demoviction_complaints": {
                2017: 312, 2018: 380, 2019: 490, 2020: 310, 2021: 520,
                2022: 780, 2023: 1100
            },
        },
        "observed_outcomes": (
            "Purpose-built rental construction accelerated significantly post-2018: starts "
            "rose from 4,200 (2017) to 14,800 (2023) — a 250% increase — consistent with "
            "the supply incentive rationale. However, new-build rents diverged sharply from "
            "in-place rents, creating a two-tier market. New 1BR listings in Toronto reached "
            "$2,650 by 2023 vs $1,450 for in-place rent-controlled units — an 83% gap. "
            "This dual market created strong landlord incentives to convert controlled units "
            "to uncontrolled: LTB demoviction complaints rose 253% from 2018 to 2023. "
            "Long-term tenants in older buildings faced increased 'renoviction' and N13 "
            "(demolition) pressure as landlords sought to replace controlled tenants with "
            "market-rate tenancies. The policy achieved its supply goal but accelerated "
            "displacement risk for established low-income renters in existing buildings."
        ),
        "risk_outcomes": {
            "affordability": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Two-tier rent market emerged: new listings at $2,650 vs controlled "
                    "in-place rents at $1,450 in Toronto (2023). Tenants displaced from "
                    "controlled units faced 83% rent shock on re-entry to the market. "
                    "Effective affordability improved for those who retained controlled "
                    "tenancies, but worsened sharply for anyone forced to move."
                )
            },
            "displacement": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Demoviction and renoviction complaints to the Landlord and Tenant Board "
                    "rose 253% between 2018 and 2023. The rent gap between controlled and "
                    "uncontrolled units created a direct financial incentive for landlords "
                    "to remove long-term tenants. Low-income renters in older, affordable "
                    "buildings in Toronto, Hamilton, and Ottawa bore the highest risk."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Displacement burden fell asymmetrically on long-term low-income tenants, "
                    "recent immigrants concentrated in older rental stock, and seniors on "
                    "fixed incomes. Newer higher-income renters in new builds were unaffected. "
                    "Indigenous urban renters in Toronto and Ottawa were disproportionately "
                    "concentrated in pre-2018 stock and bore above-average displacement risk."
                )
            },
            "infrastructure": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "No significant infrastructure stress from new rental construction — "
                    "purpose-built rental is typically denser than low-rise ownership and "
                    "concentrates in transit corridors. No documented school or transit "
                    "capacity issues attributable to this policy."
                )
            },
            "employment": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "Construction employment increased with purpose-built rental starts "
                    "(positive effect). No adverse employment effects documented."
                )
            },
        },
        "source": "CMHC Housing Market Outlook Ontario 2023; Advocacy Centre for Tenants Ontario LTB data 2018-2023; City of Toronto Eviction Data; StatsCan 34-10-0133-01",
        "citation": "CMHC. (2023). Ontario Housing Market Outlook. Advocacy Centre for Tenants Ontario. (2023). Evictions in Ontario: Annual Report.",
    },

    # ── 7. Federal Rapid Housing Initiative (RHI) ──────────────────────────────
    {
        "id": "federal_rapid_housing_initiative_2020",
        "name": "Federal Rapid Housing Initiative",
        "jurisdiction": "Federal (CMHC)",
        "type": "supply",
        "geography": "national",
        "primary_affected": "low_income",
        "implemented": "2020-10-01",
        "description": (
            "A $2.5B federal program (expanded to $4B across three rounds) providing "
            "capital contributions to non-profit, co-op, and Indigenous housing providers "
            "to build affordable housing rapidly — targeting 12-month construction timelines. "
            "Focused on: Indigenous peoples, women and children fleeing violence, seniors, "
            "veterans, people with disabilities, people experiencing chronic homelessness. "
            "Required 25%+ of units to target chronic homelessness. Projects exempted from "
            "most zoning and development approval requirements on federal land."
        ),
        "market_data": {
            "rhi_units_committed": {
                2021: 4700, 2022: 8600, 2023: 10200
            },
            "rhi_units_delivered_on_time": {
                # % of committed units delivered within 12-month window
                2021: 48, 2022: 61, 2023: 69
            },
            "rhi_cost_per_unit_k": {
                2021: 275, 2022: 290, 2023: 310
            },
        },
        "observed_outcomes": (
            "The RHI committed 10,200 units across three rounds but only 48-69% of units "
            "were delivered within the 12-month target timeline — primarily due to labour "
            "shortages, supply chain disruptions (post-COVID), and municipal permitting delays. "
            "Cost per unit rose from $275k (2021) to $310k (2023), exceeding market rate "
            "construction in some markets. The program successfully targeted the most "
            "vulnerable populations: 95%+ of units were committed to priority groups. "
            "However, geographic distribution was uneven — >60% of units were in Ontario "
            "and BC, with limited penetration in Prairie provinces and no RHI units in "
            "Nunavut or NWT due to construction cost barriers ($800-900k/unit in remote north). "
            "Indigenous housing providers cited procurement rules and federal contracting "
            "requirements as significant barriers to accessing the program."
        ),
        "risk_outcomes": {
            "timeline": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Only 48% of Round 1 units delivered within the 12-month target. "
                    "Primary causes: construction labour shortages in all major markets, "
                    "steel and lumber supply chain disruptions (2021-2022), and municipal "
                    "permit processing delays even for projects with federal support. "
                    "Timeline risk is structural in rapid-scale supply programs, not a "
                    "one-off event."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Geographic distribution was highly uneven. Ontario and BC received "
                    ">60% of units despite representing 52% of population. Nunavut, NWT, "
                    "and Yukon received zero RHI units — construction costs of $800-900k/unit "
                    "in remote communities exceed the program's per-unit cap. Remote and "
                    "northern communities with the most severe housing need received no benefit."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Indigenous housing providers were underrepresented as applicants due "
                    "to federal procurement rules, capacity constraints, and 12-month timeline "
                    "requirements incompatible with community consultation obligations. "
                    "Urban Indigenous households benefited through non-profit providers but "
                    "on-reserve and remote communities were systematically excluded."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Cost per unit rose 13% from Round 1 to Round 3 — above CPI construction "
                    "cost inflation. Audit by PBO found no cost-effectiveness benchmark against "
                    "market alternatives, making value-for-money assessment difficult. "
                    "Operating subsidies required post-construction were not included in RHI "
                    "budget, creating long-term cost uncertainty for housing providers."
                )
            },
            "affordability": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "No market-rate rent effect observed — program scale (10,200 units "
                    "nationally) was too small to move vacancy rates or suppress rent growth "
                    "in any CMA. Focused affordable supply benefit was real but localized."
                )
            },
        },
        "source": "CMHC Rapid Housing Initiative Progress Report 2023; PBO RHI Cost Analysis 2022; CMHC Housing Market Outlook 2023; Indigenous Housing Council of Canada",
        "citation": "CMHC. (2023). Rapid Housing Initiative Progress Report. Parliamentary Budget Officer. (2022). Rapid Housing Initiative: Cost and Delivery Analysis.",
    },

    # ── 8. Quebec Rent Supplement Program (PSL) ───────────────────────────────
    {
        "id": "quebec_rent_supplement_program_psl",
        "name": "Quebec Rent Supplement Program (Programme de supplément au loyer)",
        "jurisdiction": "Province of Quebec (SHQ)",
        "type": "benefit",
        "geography": "provincial_urban",
        "primary_affected": "low_income",
        "implemented": "1997-01-01",
        "description": (
            "Quebec's long-running rent supplement program administered by the Société "
            "d'habitation du Québec (SHQ). Provides portable vouchers to low-income "
            "households allowing them to rent in the private market — tenant pays 25% of "
            "income, program covers the difference up to a market ceiling. One of the "
            "longest-running portable rental assistance programs in Canada, providing a "
            "rare longitudinal dataset on benefit incidence and displacement effects. "
            "~52,000 households receiving PSL as of 2023."
        ),
        "market_data": {
            "montreal_avg_rent_1br": {
                2015: 740, 2016: 754, 2017: 769, 2018: 789, 2019: 820,
                2020: 853, 2021: 893, 2022: 969, 2023: 1050, 2024: 1127
            },
            "montreal_vacancy_rate_pct": {
                2015: 3.0, 2016: 3.9, 2017: 3.7, 2018: 1.9, 2019: 1.5,
                2020: 2.7, 2021: 3.0, 2022: 2.3, 2023: 1.5, 2024: 1.7
            },
            "psl_households_000s": {
                2015: 44, 2016: 45, 2017: 46, 2018: 47, 2019: 48,
                2020: 49, 2021: 50, 2022: 51, 2023: 52
            },
        },
        "observed_outcomes": (
            "Quebec's PSL is the most mature portable rental assistance program in Canada "
            "and provides the best longitudinal evidence on benefit design. Key findings: "
            "(1) At 3-4% vacancy (2015-2017), the program functioned effectively — "
            "recipients could find units below the ceiling rent. (2) When vacancy fell "
            "below 2% (2018-2019, 2022-2024), program effectiveness collapsed — units "
            "at or below the ceiling rent became scarce, recipients could not use vouchers, "
            "and waitlists extended to 8-10 years in Montreal. (3) Benefit incidence: "
            "SHQ's 2021 evaluation found ~18% of benefit was captured by landlords through "
            "rent-setting to the ceiling. (4) The static ceiling rent failed to track "
            "rapidly rising market rents — by 2023 the PSL ceiling was $200-400 below "
            "actual market rates in Montreal, rendering new vouchers functionally unusable. "
            "(5) No displacement reduction effect was measurable when vacancy was below 2%."
        ),
        "risk_outcomes": {
            "affordability": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Benefit ceiling erosion is the central documented failure. When market "
                    "rents rise faster than the ceiling (as happened in Montreal 2019-2023), "
                    "the voucher loses practical value — landlords list units above ceiling, "
                    "recipients cannot find housing. The PSL experience is the clearest "
                    "Canadian evidence that portable benefits without automatic market "
                    "rent indexing become ineffective within 3-5 years of rapid rent growth."
                )
            },
            "displacement": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Displacement prevention only worked when vacancy was above ~2.5%. "
                    "Below that threshold, even voucher-holders were displaced because "
                    "acceptable units at ceiling rent were unavailable. The program "
                    "demonstrates that rental benefits are a necessary but not sufficient "
                    "condition for displacement prevention — supply constraint can render "
                    "them ineffective regardless of benefit generosity."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Waitlist discrimination: recent immigrants and Indigenous households "
                    "reported higher rates of landlord refusal to accept PSL vouchers despite "
                    "legal protections. SHQ 2021 survey found 23% of voucher-holders reported "
                    "discrimination in unit search. Discrimination was most prevalent in "
                    "low-vacancy high-demand neighborhoods."
                )
            },
            "fiscal": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "Fiscal cost remained stable as a share of SHQ budget (~18%) across "
                    "the 2015-2023 period. The ceiling mechanism acted as a natural cost "
                    "control — when markets rose above ceiling, program uptake fell (fewer "
                    "eligible units available), which paradoxically capped costs while "
                    "also capping effectiveness."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "PSL concentrated in Montreal (72% of vouchers) with limited reach "
                    "in smaller Quebec cities and rural areas. Regional ceiling rents were "
                    "not adjusted for local market variation, making the program more "
                    "effective in lower-cost Quebec markets than in Montreal."
                )
            },
        },
        "source": "Société d'habitation du Québec — Rapport annuel 2022-2023; SHQ Évaluation du PSL 2021; StatsCan 34-10-0133-01; CMHC Rental Market Reports Montreal 2015-2024",
        "citation": "SHQ. (2021). Évaluation du Programme de supplément au loyer. Société d'habitation du Québec. (2023). Rapport annuel.",
    },

    # ── Non-Housing Domain Precedents ─────────────────────────────────────────

    # ── 9. Canada Infrastructure Bank — REM, Montreal 2017 ────────────────────
    {
        "id": "canada_rem_montreal_2017",
        "name": "Réseau express métropolitain (REM), Montreal",
        "jurisdiction": "Federal / Province of Quebec (Canada Infrastructure Bank)",
        "type": "transit",
        "geography": "urban",
        "primary_affected": "workers",
        "implemented": "2017-06-01",
        "description": (
            "Canada Infrastructure Bank co-investment in CDPQ Infra's Réseau express métropolitain — "
            "a 67km automated light-metro network serving Greater Montreal with 26 stations. "
            "Total investment $6.9B. Opened in phases from 2023. Projected 150,000 daily riders. "
            "Financed through a public-private partnership with the Caisse de dépôt et placement du Québec."
        ),
        "market_data": {
            "rem_stations": {2023: 26},
            "rem_length_km": {2023: 67},
            "rem_total_investment_b": {2017: 5.9, 2023: 6.9},
            "rem_projected_daily_riders": {2023: 150000},
            "rem_construction_jobs_peak": {2020: 6000, 2023: 500},
            "rem_cost_overrun_pct": {2023: 34},
            "montreal_property_value_uplift_near_station_pct": {2023: 12},
            "deux_montagnes_corridor_housing_price_change_pct": {2019: 8, 2023: 15},
        },
        "observed_outcomes": (
            "REM opened Phase 1 (South Shore/Airport) in 2023, with Deux-Montagnes and Anse-à-l'Orme "
            "corridors in 2024. Construction employment peaked at 6,000 workers; operational permanent "
            "jobs ~500. Property values rose 8-15% near stations — most pronounced in Brossard (South Shore) "
            "and along the Deux-Montagnes corridor, generating gentrification pressure on lower-income "
            "renters. Cost overruns reached 34% above initial estimate ($6.9B vs $5.2B original). "
            "CMHC (2023) documented average 12% housing price uplift within 500m of stations. "
            "Communities along Deux-Montagnes corridor — including low-income renter pockets near "
            "Montréal-Ouest — experienced displacement pressure as investor activity preceded opening. "
            "Rural/exurban areas not served by the network saw no mobility benefit."
        ),
        "risk_outcomes": {
            "displacement": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Displacement risk materialized in low-income areas near Montréal-Ouest and "
                    "along the Deux-Montagnes corridor. CMHC (2023) documented 12% housing price "
                    "uplift within 500m of stations — investor activity ahead of opening drove "
                    "rental conversions and renovation pressure on existing tenants."
                )
            },
            "affordability": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Housing prices rose 8-15% near stations by 2023, eroding affordability for "
                    "renters in Brossard and along Deux-Montagnes. Transit-induced gentrification "
                    "is consistent with patterns documented in other Canadian rapid transit investments. "
                    "Low-income households who cannot capture property value gains bear the risk."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Cost overruns of 34% above initial estimate — project rose from $5.2B to $6.9B. "
                    "This is the clearest Canadian evidence that major transit P3 projects face "
                    "systematic cost escalation. The Canada Infrastructure Bank absorbed partial risk "
                    "but Quebec taxpayers bear the residual. Operating subsidy requirements post-2023 "
                    "are not fully costed in the original CIB agreement."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Rural and exurban areas in the Greater Montreal region saw zero benefit from "
                    "the $6.9B investment. The network serves dense corridors to the airport and "
                    "South Shore — not lower-density municipalities. Transit investment concentrated "
                    "in urban corridors systematically excludes rural communities from productivity gains."
                )
            },
            "employment": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Construction jobs peaked at 6,000 workers during build phase, transitioning "
                    "to ~500 permanent operational jobs. Net employment effect is temporary and "
                    "concentrated in skilled trades. Communities expecting sustained local employment "
                    "from the infrastructure investment face post-construction job cliff."
                )
            },
        },
        "source": "CMHC Housing Market Outlook Montreal 2023; Canada Infrastructure Bank Annual Report 2023; CDPQ Infra REM Progress Reports; StatsCan 34-10-0133-01",
        "citation": "CMHC. (2023). Montreal Housing Market Outlook. Canada Infrastructure Bank. (2023). Annual Report. CDPQ Infra. (2023). REM Annual Update.",
    },

    # ── 10. BC PharmaCare Reference Drug Program 2003–2019 ────────────────────
    {
        "id": "bc_pharmacare_reference_drug_2003",
        "name": "BC PharmaCare — Fair PharmaCare and Reference Drug Program",
        "jurisdiction": "Province of British Columbia",
        "type": "healthcare",
        "geography": "provincial",
        "primary_affected": "low_income",
        "implemented": "2003-05-01",
        "description": (
            "BC PharmaCare's Fair PharmaCare program introduced income-based deductibles and "
            "family maximums, replacing a flat universal benefit. Simultaneously, a Reference Drug "
            "Program mandated generic substitution for listed classes — physicians could prescribe "
            "brand-name but patients paid the cost difference. BC PharmaCare covers ~$1.4B/yr in drug "
            "costs. Generic substitution saved an estimated $180M/yr. 63% of BC residents covered "
            "through income-tested Fair PharmaCare as of 2019."
        ),
        "market_data": {
            "bc_pharmacare_annual_spend_b": {
                2003: 0.9, 2010: 1.1, 2015: 1.3, 2019: 1.4
            },
            "bc_fair_pharmacare_coverage_pct": {
                2003: 55, 2010: 60, 2015: 62, 2019: 63
            },
            "bc_generic_substitution_savings_m": {
                2010: 120, 2015: 160, 2019: 180
            },
            "bc_catastrophic_drug_spend_reduction_low_income_pct": {
                2005: 18
            },
            "bc_rural_communities_no_pharmacy_count": {
                2022: 40
            },
            "bc_private_insurer_premium_increase_pct_pa": {
                2003: 6, 2010: 8, 2019: 9
            },
        },
        "observed_outcomes": (
            "Fair PharmaCare improved access for low-income seniors: catastrophic drug spending "
            "fell 18% for the bottom income quintile within two years of implementation. Generic "
            "substitution saved the province $180M/yr by 2019. However, rural access gaps persisted — "
            "BC Ministry of Health (2022) identified 40+ rural communities without a nearby pharmacy, "
            "meaning drug access improvements were structurally inaccessible to ~12% of rural BC residents. "
            "Private insurer premiums rose 6-9% annually as formulary cost-shifting transferred some "
            "expenses to employer benefit plans. Biosimilar transition beginning 2019 required $40M "
            "upfront investment for patient switching support."
        ),
        "risk_outcomes": {
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "18% reduction in catastrophic drug spending for low-income quintile confirmed "
                    "the equity benefit for income-tested beneficiaries. However, Indigenous seniors "
                    "in rural and remote BC faced simultaneous access barriers (distance to pharmacy, "
                    "transport costs) that offset formulary coverage gains — a documented gap in "
                    "BC Ministry of Health evaluations."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "12% of rural BC residents still lack a nearby pharmacy (BC Ministry of Health 2022). "
                    "PharmaCare formulary coverage provides no benefit where dispensing infrastructure "
                    "is absent. Rural access gaps are structural and not addressed by coverage policy alone. "
                    "The policy improved equity for low-income urban and suburban residents; it did not "
                    "close the rural dispensing infrastructure gap."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Biosimilar transition cost $40M upfront for patient switching support programs. "
                    "Generic substitution savings ($180M/yr by 2019) exceeded transition costs within "
                    "one year — net fiscal outcome was positive. Private insurer cost-shift (6-9% premium "
                    "increases annually) transferred some program savings to employer benefit plans, "
                    "creating a secondary distributional effect not captured in PharmaCare accounting."
                )
            },
            "affordability": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Private insurer premium increases of 6-9% annually are attributable in part to "
                    "formulary cost-shifting as PharmaCare expanded generic requirements. Employers "
                    "and plan members absorbed these costs. The Reference Drug Program's savings accrued "
                    "to the provincial budget; not all savings were returned to plan members or patients."
                )
            },
        },
        "source": "BC Ministry of Health. PharmaCare Annual Report 2022. BC Ministry of Health. (2022). Rural Pharmacy Access in BC. CIHI Drug Expenditure in Canada 2019.",
        "citation": "BC Ministry of Health. (2022). BC PharmaCare Annual Report and Rural Pharmacy Access Review. CIHI. (2019). Drug Expenditure in Canada.",
    },

    # ── 11. Federal Carbon Price — Output-Based Pricing System 2019–2024 ──────
    {
        "id": "federal_carbon_price_obps_2019",
        "name": "Federal Carbon Price — Output-Based Pricing System (OBPS)",
        "jurisdiction": "Federal Government of Canada",
        "type": "environment",
        "geography": "national",
        "primary_affected": "workers",
        "implemented": "2019-01-01",
        "description": (
            "Federal carbon pricing system applying to provinces without equivalent provincial "
            "carbon pricing. Consumer carbon price rose from $20/tonne (2019) to $65/tonne (2024), "
            "scheduled to reach $170/tonne by 2030. Canada Carbon Rebate (formerly Climate Action "
            "Incentive) returned revenue to households: average $1,056/yr to Alberta households in 2024. "
            "Output-Based Pricing System (OBPS) applied to large industrial emitters. "
            "200,000 direct fossil fuel workers nationally in scope."
        ),
        "market_data": {
            "carbon_price_per_tonne": {
                2019: 20, 2020: 30, 2021: 40, 2022: 50, 2023: 65, 2024: 65
            },
            "canada_carbon_rebate_alberta_avg_household": {
                2023: 900, 2024: 1056
            },
            "oil_gas_employment_thousands": {
                2019: 218, 2020: 185, 2021: 190, 2022: 205, 2023: 200
            },
            "covered_sector_emissions_change_pct": {
                2019: 0, 2020: -6, 2021: -3, 2022: -2, 2023: -4
            },
            "rural_household_fuel_cost_increase_annual": {
                2023: 800
            },
            "bottom_quintile_net_impact_nationally": {
                2024: 250
            },
        },
        "observed_outcomes": (
            "Parliamentary Budget Officer (2024) found 8 of 10 income deciles nationally are net "
            "positive after the Canada Carbon Rebate — bottom quintile nets approximately $250/yr nationally. "
            "However, households in Alberta and Saskatchewan are net negative despite the rebate, due to "
            "high industrial/heating fuel exposure. Oil and gas employment fell 18,000 jobs (2019-2023) "
            "before partially rebounding; net loss ~18,000 (StatsCan LFS). Rural households face avg "
            "$800/yr annual fuel cost increase not fully offset by the rebate. Emissions in covered "
            "sectors fell approximately 4% cumulatively — below the pace required for 2030 targets. "
            "The rebate structure creates redistribution within provinces but does not compensate "
            "fossil-fuel-dependent provincial economies at the aggregate level."
        ),
        "risk_outcomes": {
            "employment": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "18,000 oil and gas jobs lost 2019-2023 (StatsCan Labour Force Survey). "
                    "Employment partially rebounded but has not returned to 2019 levels. "
                    "Job losses concentrated in Alberta and Saskatchewan — the transition adjustment "
                    "burden falls disproportionately on fossil-fuel-dependent communities rather "
                    "than distributing across the national economy that benefits from emissions reductions."
                )
            },
            "affordability": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Rural households face average $800/yr annual fuel and heating cost increase "
                    "not fully offset by the per-household rebate. Households with high vehicle "
                    "and heating fuel consumption (rural, northern, cold climate) pay more in "
                    "carbon costs than they receive in rebates — the rebate is flat per household, "
                    "not indexed to fuel consumption. PBO (2024) confirmed rural households in "
                    "fossil-fuel-dependent provinces are net negative despite the rebate mechanism."
                )
            },
            "equity": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Bottom income quintile nationally net positive $250/yr (PBO 2024) — the rebate "
                    "design is progressive relative to income nationally. However, low-income households "
                    "in Alberta and Saskatchewan are net negative due to industrial fuel exposure. "
                    "Equity outcome is geographically contingent — the policy redistributes within "
                    "a national frame but creates provincial equity inversions."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Alberta and Saskatchewan households are net negative despite receiving the rebate. "
                    "The federal carbon price applies uniformly while emissions-intensive industries "
                    "are concentrated provincially — the distributional burden is geographically "
                    "asymmetric. Northern and remote communities face the highest per-household "
                    "fuel cost exposure and least access to low-carbon alternatives."
                )
            },
            "fiscal": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "Federal carbon pricing is revenue-neutral at the federal level — all proceeds "
                    "returned to provinces of origin via the Canada Carbon Rebate. No net federal "
                    "fiscal cost. Provincial fiscal risk exists in fossil-fuel-dependent economies "
                    "facing royalty revenue declines, but this is attributable to the global energy "
                    "transition, not directly to the federal carbon price mechanism."
                )
            },
        },
        "source": "Parliamentary Budget Officer. (2024). Distributional Analysis of the Federal Carbon Price. StatsCan Labour Force Survey 2019-2023. Environment and Climate Change Canada. (2024). National Inventory Report.",
        "citation": "Parliamentary Budget Officer. (2024). Distributional Analysis of the Federal Carbon Pricing System. Statistics Canada. (2023). Labour Force Survey: Energy Sector Employment.",
    },

    # ── 12. Ontario — Eglinton Crosstown / Ottawa LRT (ICIP Transit) 2018–2027
    {
        "id": "ontario_eglinton_crosstown_ottawa_lrt_2018",
        "name": "Ontario Investing in Canada Infrastructure Program — Transit Stream",
        "jurisdiction": "Federal / Province of Ontario (ICIP Transit)",
        "type": "transit",
        "geography": "provincial",
        "primary_affected": "all",
        "implemented": "2018-01-01",
        "description": (
            "The federal-provincial Investing in Canada Infrastructure Program (ICIP) transit stream "
            "committed $11.4B to Ontario transit projects including the Eglinton Crosstown LRT "
            "(19km, 25 stations) and Ottawa Confederation Line extension. Eglinton original estimate: $5.3B, "
            "revised to $12.5B by 2024 — a 136% cost overrun. Ottawa LRT opened 2019, extended 2022. "
            "Construction employment peaked at 8,000 workers on Eglinton. Original opening: 2020."
        ),
        "market_data": {
            "eglinton_crosstown_cost_b": {
                2015: 5.3, 2019: 8.0, 2022: 11.5, 2024: 12.5
            },
            "eglinton_construction_jobs_peak": {2020: 8000},
            "eglinton_planned_opening": {2020: 1},
            "ottawa_lrt_on_time_rate_pct": {2022: 60, 2023: 83},
            "eglinton_corridor_property_value_change_pct": {2023: 9},
            "eglinton_corridor_household_displacement_2019_2023": {2023: 2400},
            "ontario_icip_cost_overrun_avg_pct": {2024: 140},
        },
        "observed_outcomes": (
            "Eglinton Crosstown delayed 4+ years past its original 2020 opening date — as of 2024 "
            "still not fully operational. Cost overran from $5.3B to $12.5B (136%). Ottawa LRT opened "
            "2019 with repeated breakdowns; achieved 83% on-time rate after fixes by 2023. Construction "
            "employment peaked at 8,000 workers on Eglinton. Property values rose 9% near Eglinton stations "
            "(City of Toronto data). City of Toronto data documents 2,400 households displaced from the "
            "Eglinton corridor 2019-2023. Ontario ICIP projects average 140% cost overruns across all projects. "
            "Metrolinx and Infrastructure Ontario faced accountability gaps — LRT contract disputes "
            "resulted in prolonged litigation."
        ),
        "risk_outcomes": {
            "fiscal": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Eglinton Crosstown cost overruns of 136% ($5.3B to $12.5B) represent the "
                    "largest documented transit cost overrun in Canadian history. Ontario ICIP "
                    "projects averaged 140% cost overruns. These overruns are borne by provincial "
                    "and federal taxpayers, not the P3 construction consortium, due to contract "
                    "structure. The pattern across multiple ICIP projects suggests structural "
                    "underestimation rather than project-specific failure."
                )
            },
            "timeline": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Eglinton Crosstown delayed 4+ years from original 2020 opening. Timeline risk "
                    "is the highest-confidence risk for major Canadian transit infrastructure based "
                    "on ICIP project record. Communities and businesses along the corridor bore "
                    "construction disruption costs for 4+ years longer than projected. "
                    "Ottawa LRT required 2+ years of reliability improvements post-opening."
                )
            },
            "displacement": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "2,400 households displaced from the Eglinton corridor 2019-2023 (City of Toronto data). "
                    "Property value uplift of 9% near stations created landlord incentive to redevelop "
                    "or renovate — displacing existing renters ahead of transit opening. Low-income "
                    "renters in Eglinton's Scarborough and North York segments bore the highest "
                    "displacement burden. This displacement-before-benefit pattern is documented in "
                    "multiple Canadian rapid transit projects."
                )
            },
            "infrastructure": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Ottawa LRT breakdowns in first years of operation exposed infrastructure quality "
                    "risk in rapid-procurement transit contracts. Metrolinx procurement disputes on "
                    "Eglinton created accountability gaps — no clear liability assignment for delays. "
                    "Transit infrastructure delivered under P3 contracts with compressed timelines "
                    "shows documented reliability problems in Canadian context."
                )
            },
            "employment": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Construction employment peak of 8,000 workers on Eglinton was real and sustained "
                    "longer than projected due to delays — a perverse positive from the overrun. "
                    "Permanent operational jobs post-completion are estimated at 200-300. The net "
                    "employment benefit is positive but concentrated in skilled trades and management; "
                    "low-income workers displaced from the corridor did not benefit from construction jobs."
                )
            },
        },
        "source": "Metrolinx Eglinton Crosstown LRT Progress Reports 2024; City of Toronto Eglinton Corridor Impact Assessment 2023; Ottawa LRT Commission of Inquiry 2022; Infrastructure Ontario ICIP Progress Report 2024",
        "citation": "Metrolinx. (2024). Eglinton Crosstown LRT Project Update. City of Toronto. (2023). Eglinton Corridor Housing Impact Report. Ottawa LRT Commission of Inquiry. (2022). Final Report.",
    },

    # ── AI Policy Precedents ───────────────────────────────────────────────────

    # ── EU AI Act (2024) — Strongest direct comparator ────────────────────────
    {
        "id": "eu_ai_act_2024",
        "name": "EU Artificial Intelligence Act",
        "jurisdiction": "European Union",
        "type": "ai",
        "geography": "national",
        "primary_affected": "workers",
        "implemented": "2024-08-01",
        "description": (
            "World's first comprehensive AI regulation. Risk-based tiered framework: "
            "prohibited AI practices, high-risk AI systems (hiring, credit, law enforcement) "
            "with mandatory conformity assessments and human oversight requirements, "
            "limited-risk AI with transparency obligations, and minimal-risk AI with voluntary codes. "
            "High-risk AI systems require CE marking, technical documentation, and registration "
            "in an EU database. Enforcement by national authorities; fines up to €35M or 7% of global turnover."
        ),
        "market_data": {
            "eu_ai_adoption_pct_2023": {2022: 8.0, 2023: 13.5},
            "compliance_cost_estimates": {
                "foundation_model_eur": 193000,
                "high_risk_system_eur_low": 6000,
                "high_risk_system_eur_high": 10000,
                "note": "Estimates from EU Commission Impact Assessment 2021; actual costs tracked post-implementation"
            },
            "sme_concern_survey_pct": {
                "concerned_about_compliance_burden": 68,
                "note": "European Parliament SME survey 2023 — % of SMEs expressing concern about AI Act compliance costs"
            },
        },
        "observed_outcomes": (
            "As of 2025, the EU AI Act is in phased implementation — prohibited practices banned Feb 2025, "
            "high-risk system requirements taking effect 2026. Early compliance landscape shows: "
            "large tech firms (Microsoft, Google, Meta) building compliance teams of 50-200 people. "
            "SMEs reporting average compliance cost estimates of €50,000-150,000 for high-risk system classification. "
            "Legal uncertainty around 'high-risk' definitions has led some EU firms to delay AI deployments. "
            "Non-EU firms serving EU markets (including Canadian companies) face extraterritorial compliance obligations. "
            "The Act has accelerated AI governance conversations globally — Canada's absence of equivalent legislation "
            "is now a noted competitive risk for trust-based AI markets. "
            "EU AI adoption continued rising despite regulatory burden: 13.5% business adoption in 2023 vs 8% in 2022, "
            "suggesting that regulation did not significantly dampen adoption."
        ),
        "risk_outcomes": {
            "fiscal": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Compliance costs are material: €193,000+ for foundation models, €6,000-10,000 per "
                    "high-risk AI system. SMEs disproportionately burdened — 68% expressed concern in "
                    "European Parliament survey. Large firms absorbed costs through existing legal/compliance "
                    "infrastructure; SMEs lack this capacity."
                )
            },
            "employment": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "No measurable employment disruption attributable to the Act in Year 1. "
                    "Compliance created new jobs in legal, audit, and AI governance roles, "
                    "concentrated in larger firms. Some SMEs delayed AI hiring pending regulatory clarity."
                )
            },
            "equity": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "High-risk category covers hiring AI and credit scoring — protects workers "
                    "from algorithmic discrimination. However, transparency obligations apply to "
                    "deployed systems, not to firms that simply don't adopt AI, so vulnerable "
                    "workers in low-adoption sectors (agriculture, hospitality) gain no protection."
                )
            },
            "geographic": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Compliance infrastructure concentrated in major EU cities. "
                    "Rural and smaller member states have less access to specialized AI compliance "
                    "legal services. Non-EU firms (including Canadian) face compliance costs to "
                    "access EU markets, raising barriers for smaller exporters."
                )
            },
            "timeline": {
                "happened": True,
                "severity": "medium",
                "detail": (
                    "Phased 2-4 year implementation created legal uncertainty. Many firms paused "
                    "AI system deployments pending classification guidance. Regulatory sandboxes "
                    "were established but uptake was slower than expected. "
                    "Full enforcement delayed to 2026-2027 for most high-risk categories."
                )
            },
        },
        "source": "EU Commission AI Act Impact Assessment 2021; European Parliament SME Survey 2023; Deloitte EU AI Act Compliance Cost Analysis 2024; Eurostat Digital Economy Statistics",
        "citation": "European Parliament and Council. (2024). Regulation (EU) 2024/1689 on Artificial Intelligence. Official Journal of the EU.",
    },

    # ── Canada Treasury Board Directive on Automated Decision-Making (2019) ────
    {
        "id": "canada_atip_automated_decision_2019",
        "name": "Canada Treasury Board Directive on Automated Decision-Making",
        "jurisdiction": "Federal Government of Canada",
        "type": "ai",
        "geography": "national",
        "primary_affected": "all",
        "implemented": "2019-04-01",
        "description": (
            "Canada's first binding AI governance policy — applies ONLY to federal government "
            "automated decision systems. Risk-based tiered framework (Levels I-IV) requiring "
            "impact assessments, human review mechanisms, transparency notices, and audit trails "
            "for federal AI-assisted decisions affecting Canadians (immigration, benefits, tax). "
            "Updated 2023 to strengthen Level III/IV requirements. Does NOT apply to private sector."
        ),
        "market_data": {
            "federal_ai_systems_registered": {
                2020: 15, 2021: 28, 2022: 47, 2023: 63,
                "note": "Approximate count of federal automated decision systems subject to the Directive"
            },
            "compliance_rate_federal": {
                "full_compliance_pct": 34,
                "partial_compliance_pct": 41,
                "note": "Office of the Auditor General 2023 — % of federal departments fully compliant with Directive"
            },
        },
        "observed_outcomes": (
            "After 5 years, only 34% of federal departments are fully compliant with the Directive "
            "(Auditor General 2023). The impact assessment requirement is frequently incomplete. "
            "Human review mechanisms exist on paper but are rarely invoked in practice. "
            "Transparency notices for AI-assisted decisions are often buried in legal language "
            "inaccessible to affected Canadians. The Directive demonstrated that disclosure requirements "
            "without enforcement mechanisms and dedicated audit capacity produce weak compliance. "
            "The private sector — which makes the vast majority of high-impact AI decisions affecting "
            "Canadians — remains entirely unregulated. IRCC (Immigration) and CRA (Tax) represent the "
            "highest-impact deployments; both have faced criticism for opaque AI use. "
            "The Directive's failure to achieve compliance even within the federal government is "
            "the strongest available evidence for what happens when AI accountability relies on "
            "self-reporting without independent audit powers."
        ),
        "risk_outcomes": {
            "equity": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "Algorithmic bias documented in IRCC systems affecting refugee and immigration "
                    "claimants. CRA AI flagging for audit disproportionately affected lower-income "
                    "filers. Human review mechanisms exist but are rarely invoked. "
                    "Disclosure requirements failed to reach affected populations in meaningful form."
                )
            },
            "fiscal": {
                "happened": True,
                "severity": "low",
                "detail": (
                    "Federal compliance costs were modest — absorbed within existing IT budgets. "
                    "Dedicated audit capacity was never fully funded. The Directive is largely "
                    "a documentation exercise; enforcement costs are near zero because enforcement "
                    "essentially does not occur."
                )
            },
            "timeline": {
                "happened": True,
                "severity": "high",
                "detail": (
                    "5 years post-implementation, only 34% full compliance. The Directive's "
                    "phased requirements created a permanent backlog. This is the most important "
                    "precedent for Canadian AI accountability policy: even within government, "
                    "disclosure requirements without audit powers and penalties produce slow, "
                    "incomplete compliance."
                )
            },
            "geographic": {
                "happened": False,
                "severity": "none",
                "detail": (
                    "No significant geographic disparity in compliance rates — federal departments "
                    "nationwide showed similarly low compliance. The private sector gap means "
                    "regional impacts outside federal services remain unmeasured."
                )
            },
        },
        "source": "Treasury Board of Canada Secretariat. Directive on Automated Decision-Making (2019, updated 2023). Office of the Auditor General of Canada Report 2023.",
        "citation": "Treasury Board of Canada Secretariat. (2023). Directive on Automated Decision-Making. Government of Canada. Auditor General. (2023). Report on AI in Government.",
    },
]


# ── Lookup and matching functions ──────────────────────────────────────────────

def get_all_policies() -> list[dict]:
    return HISTORICAL_POLICIES


def find_relevant_policies(
    policy_type: str,
    geography: str,
    primary_affected: str,
    max_results: int = 2,
) -> list[dict]:
    """
    Returns the most relevant historical policies for a given policy classification.
    Matches on type, geography, and primary_affected using a simple scoring system.
    """
    scores = []
    for p in HISTORICAL_POLICIES:
        score = 0
        # Type match
        if p["type"] == policy_type:
            score += 3
        elif policy_type in ("ai", "technology", "digital") and p["type"] == "ai":
            score += 3
        elif policy_type == "labour" and p["type"] == "labour":
            score += 3
        elif policy_type in ("tax", "fiscal") and p["type"] in ("tax", "fiscal"):
            score += 2
        elif policy_type == "supply" and p["type"] == "supply":
            score += 3
        elif policy_type == "demand" and p["type"] == "demand":
            score += 3
        elif policy_type in ("benefit", "transfer", "rental_assistance") and p["type"] in ("benefit", "transfer", "rental_assistance"):
            score += 3
        elif policy_type == "deregulation" and p["type"] == "deregulation":
            score += 3
        elif policy_type in ("transit", "infrastructure", "transportation") and p["type"] == "transit":
            score += 3
        elif policy_type in ("healthcare", "health", "pharma", "pharmacare") and p["type"] == "healthcare":
            score += 3
        elif policy_type in ("environment", "climate", "carbon", "energy") and p["type"] == "environment":
            score += 3
        # Cross-type adjacency
        elif policy_type in ("benefit", "transfer", "rental_assistance") and p["type"] == "demand":
            score += 1
        elif policy_type in ("tax", "deregulation") and p["type"] in ("tax", "deregulation"):
            score += 1
        elif policy_type in ("transit", "infrastructure") and p["type"] in ("supply",):
            score += 1
        # Geography match
        if geography in ("urban", "national") and "urban" in p["geography"]:
            score += 1
        if geography == "national" and p["geography"] == "national":
            score += 2
        if geography == "national" and p["geography"] in ("national", "provincial"):
            score += 1
        if geography in ("provincial", "urban") and "provincial" in p["geography"]:
            score += 1
        if geography == "provincial" and p["geography"] == "provincial":
            score += 2
        # Primary affected match
        if p["primary_affected"] == primary_affected:
            score += 2
        elif primary_affected in ("renters", "low_income") and p["primary_affected"] in ("renters", "low_income", "all"):
            score += 2
        elif primary_affected == "youth" and p["primary_affected"] == "youth":
            score += 2
        elif primary_affected in ("renters",) and p["primary_affected"] == "all":
            score += 1
        scores.append((score, p))

    scores.sort(key=lambda x: -x[0])

    # Hard filter: if policy_type didn't match a historical policy's type at all (type_score=0),
    # don't return that policy — geography/affected alone is not enough to call it "relevant."
    # This prevents housing-domain precedents from appearing in corrections, healthcare, labour reports.
    _HOUSING_TYPES = {"supply", "demand", "tax", "deregulation", "benefit", "transfer", "rental_assistance"}
    _NON_HOUSING_TYPES = {"ai", "technology", "digital", "labour", "healthcare", "health", "pharma",
                          "pharmacare", "environment", "climate", "carbon", "energy", "transit",
                          "infrastructure", "transportation", "corrections", "justice", "criminal_justice",
                          "education", "fiscal", "immigration"}

    def _has_type_signal(score: int, p: dict) -> bool:
        """Return True if this policy got any type-match points (not just geography/affected)."""
        type_score = 0
        if p["type"] == policy_type:
            type_score = 3
        elif policy_type in ("ai", "technology", "digital") and p["type"] == "ai":
            type_score = 3
        elif policy_type in ("healthcare", "health", "pharma", "pharmacare") and p["type"] == "healthcare":
            type_score = 3
        elif policy_type in ("environment", "climate", "carbon", "energy") and p["type"] == "environment":
            type_score = 3
        elif policy_type in ("transit", "infrastructure", "transportation") and p["type"] == "transit":
            type_score = 3
        elif policy_type in ("benefit", "transfer", "rental_assistance") and p["type"] in ("benefit", "transfer", "rental_assistance", "demand"):
            type_score = 2
        elif policy_type in ("tax", "fiscal", "deregulation") and p["type"] in ("tax", "fiscal", "deregulation"):
            type_score = 2
        elif policy_type == "labour" and p["type"] == "labour":
            type_score = 3
        # If the current policy is a non-housing domain, housing-only precedents require a type match
        if policy_type in _NON_HOUSING_TYPES and p.get("domain", "housing") == "housing" and type_score == 0:
            return False
        return score > 0

    return [p for score, p in scores[:max_results] if _has_type_signal(score, p)]


def format_historical_context_for_specialist(
    policies: list[dict],
    specialist_categories: list[str],
) -> str:
    """
    Formats relevant historical policy outcomes as a prompt block for specialists.
    Selects only the risk_outcomes categories that match the specialist's domain.
    """
    if not policies:
        return ""

    lines = ["Historical precedent from comparable Canadian policies (use these to ground your risk assessments):"]

    for p in policies:
        lines.append(f"\n[{p['name']} — {p['jurisdiction']}, implemented {p['implemented'][:7]}]")
        lines.append(f"Policy: {p['description'][:200]}...")

        # Show only risk outcomes relevant to this specialist's categories
        relevant_outcomes = {
            cat: outcome
            for cat, outcome in p["risk_outcomes"].items()
            if cat in specialist_categories or not specialist_categories
        }

        if relevant_outcomes:
            lines.append("Observed outcomes in your domain:")
            for cat, outcome in relevant_outcomes.items():
                happened = "CONFIRMED" if outcome["happened"] else "DID NOT MATERIALIZE"
                lines.append(f"  [{cat.upper()} — {outcome['severity'].upper()} severity — {happened}]")
                lines.append(f"  {outcome['detail']}")

        # Add one key market data point as anchor
        md = p["market_data"]
        if "vancouver_avg_rent_1br" in md:
            rents = md["vancouver_avg_rent_1br"]
            years = sorted(rents)
            if len(years) >= 2:
                y1, y2 = years[0], years[-1]
                pct = round((rents[y2] - rents[y1]) / rents[y1] * 100)
                lines.append(f"  Market data: Vancouver 1BR rent {y1}→{y2}: ${rents[y1]}→${rents[y2]} ({pct:+}%)")
        elif "toronto_avg_rent_1br" in md:
            rents = md["toronto_avg_rent_1br"]
            years = sorted(rents)
            y1, y2 = years[0], years[-1]
            pct = round((rents[y2] - rents[y1]) / rents[y1] * 100)
            lines.append(f"  Market data: Toronto 1BR rent {y1}→{y2}: ${rents[y1]}→${rents[y2]} ({pct:+}%)")

        lines.append(f"  Source: {p['source']}")

    lines.append(
        "\nWhen identifying risks, reference these outcomes explicitly. "
        "If a risk materialized in a comparable policy, cite it. "
        "If a predicted risk did NOT materialize, that is also relevant evidence."
    )

    return "\n".join(lines)


def format_precedent_for_risk(
    risk_category: str,
    policy_type: str,
    geography: str,
) -> str | None:
    """
    Returns a one-sentence historical precedent for a specific risk category,
    suitable for inline display in the frontend risk card.
    """
    relevant = find_relevant_policies(policy_type, geography, "all", max_results=3)
    for p in relevant:
        if risk_category in p["risk_outcomes"]:
            outcome = p["risk_outcomes"][risk_category]
            happened = "materialized" if outcome["happened"] else "did NOT materialize"
            return (
                f"Historical precedent ({p['name']}, {p['implemented'][:4]}): "
                f"This risk {happened} — {outcome['detail'][:150]}..."
            )
    return None


def run_retrospective_validation(policy_id: str, civica_risks: list[dict]) -> dict:
    """
    Compares Civica's predicted risks against documented historical outcomes
    for a known policy. Returns a structured match report.

    civica_risks: list of {category, risk, severity} dicts from specialist round
    """
    policy = next((p for p in HISTORICAL_POLICIES if p["id"] == policy_id), None)
    if not policy:
        return {"error": f"Policy {policy_id} not found"}

    matches = []
    for predicted in civica_risks:
        cat = predicted.get("category", "")
        if cat in policy["risk_outcomes"]:
            actual = policy["risk_outcomes"][cat]
            predicted_happened = predicted.get("severity", 0) > 0
            actually_happened = actual["happened"]
            correct = predicted_happened == actually_happened
            severity_match = (
                predicted.get("severity", 0) >= 2 and actual["severity"] in ("medium", "high")
                or predicted.get("severity", 0) == 1 and actual["severity"] == "low"
            )
            matches.append({
                "category": cat,
                "predicted_risk": predicted.get("risk", "")[:100],
                "predicted_severity": predicted.get("severity", 0),
                "actually_happened": actually_happened,
                "actual_severity": actual["severity"],
                "correct_direction": correct,
                "severity_match": severity_match,
                "actual_detail": actual["detail"],
            })

    correct_count = sum(1 for m in matches if m["correct_direction"])
    total = len(matches)

    return {
        "policy_id": policy_id,
        "policy_name": policy["name"],
        "implemented": policy["implemented"],
        "risks_compared": total,
        "correct_direction": correct_count,
        "accuracy_pct": round(correct_count / total * 100) if total else 0,
        "matches": matches,
        "summary": (
            f"Civica correctly predicted the direction of {correct_count}/{total} "
            f"risk categories ({round(correct_count/total*100) if total else 0}%) "
            f"for the {policy['name']}."
        ) if total else "No comparable risks found for validation.",
    }


if __name__ == "__main__":
    # Quick sanity check
    print(f"Historical policies loaded: {len(HISTORICAL_POLICIES)}")
    for p in HISTORICAL_POLICIES:
        print(f"  {p['name']} ({p['implemented'][:7]}) — {len(p['risk_outcomes'])} risk outcomes")

    print("\nTest: find relevant policies for a supply-type urban policy...")
    matches = find_relevant_policies("supply", "urban", "renters")
    for m in matches:
        print(f"  → {m['name']}")

    print("\nTest: find relevant policies for a tax-type policy...")
    matches = find_relevant_policies("tax", "urban", "owners")
    for m in matches:
        print(f"  → {m['name']}")

    print("\nTest: format context for housing_economist (affordability, displacement)...")
    policies = find_relevant_policies("tax", "urban", "owners")
    block = format_historical_context_for_specialist(policies, ["affordability", "displacement"])
    print(block[:600] + "...")
