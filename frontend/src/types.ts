// ── New specialist/validator format ────────────────────────────────────────

export interface Citation {
  id: string;
  title: string;
  url: string;
}

export interface SpecialistRisk {
  source: string; // e.g. "labor_economist"
  risk: string;
  mechanism: string;
  severity: 1 | 2 | 3;
  category: string;
  most_exposed: string;
  cities_most_affected: string[];
  historical_precedent?: string | null;
  citations?: Citation[];
}

export interface SpecialistResult {
  specialist: string;
  risks: SpecialistRisk[];
}

export interface ValidatorValidation {
  risk_index: number; // 1-based, maps to specialist_risks array
  applies: boolean;
  severity_for_me: 0 | 1 | 2 | 3;
  reason: string;
}

export interface MissedRisk {
  risk: string;
  category: string;
  severity: 1 | 2 | 3;
}

export interface CityDataUsed {
  avg_rent_1br?: number;
  avg_rent_2br?: number;
  vacancy_rate?: number;
  median_household_income?: number;
  shelter_cost_to_income_ratio?: number;
  unemployment_rate?: number;
  population?: number;
  population_growth_rate?: number;
  housing_starts_annual?: number;
  income_for_age?: number;
}

export interface SectorProfile {
  most_likely_sector: string;
  sector_label: string;
  sector_ai_adoption_pct: number;
  weighted_ai_adoption_pct: number;
  exposure_level: 'high' | 'medium' | 'low';
  ai_exposure_context: string;
}

export interface PersonaProfile {
  financial_fragility: 'low' | 'medium' | 'high';
  policy_stance: 'supportive' | 'skeptical_of_benefit' | 'indifferent' | 'opposed';
  top_concerns: string[];
  lived_experience_note: string;
  sector_profile?: SectorProfile;
}

export interface CohortStats {
  n_matched_unweighted: number;
  n_matched_weighted: number;
  core_housing_need_pct: number | null;
  shelter_cost_30pct_plus_pct: number | null;
  shelter_cost_100pct_plus_pct: number | null;
  median_household_income: number | null;
  dwelling_issues_pct: number | null;
  social_housing_pct: number | null;
  on_waitlist_pct: number | null;
  no_employment_pct: number | null;
  filters_applied: string[];
}

export interface ValidatorResult {
  agent_id: number;
  city: string;
  tenure: 'renter' | 'owner';
  age_bracket: string;
  income_bracket: string;
  immigration_status: string;
  family_size: string;
  employment_type: string;
  population_weight: number;
  city_data_used: CityDataUsed;
  validations: ValidatorValidation[];
  missed_risk: MissedRisk | null;
  behavioral_profile?: PersonaProfile;
  cohort_stats?: CohortStats;
}

export interface DeliberativeRevision {
  dissent_index: number;
  now_applies: boolean;
  revised_severity: 0 | 1 | 2 | 3;
  reason: string;
}

export interface DeliberativeResult {
  agent_id: number;
  city: string;
  tenure: 'renter' | 'owner';
  age_bracket: string;
  income_bracket: string;
  revised_risks: DeliberativeRevision[];
  dissenting_risks_shown: Array<{
    risk: string;
    severity: number;
    from_tenure: string;
    city: string;
  }>;
}

export interface DemographicTension {
  risk_index: number;
  risk_title: string;
  dimension: 'tenure' | 'income' | 'geography' | 'age' | 'immigration';
  group_a: string;
  rate_a: number;
  group_b: string;
  rate_b: number;
  gap: number;
  interpretation: string;
}

export interface CascadeEffect {
  triggers: string | null;
  mechanism: string | null;
  likelihood: 'LOW' | 'MEDIUM' | 'HIGH' | null;
  evidence: string | null;
}

export interface RiskReportItem {
  rank: number;
  title: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  reasoning: string;
  affected_groups: string;
  confirmed_by: number;
  out_of: number;
  cities: string[];
  timeline: 'immediate' | 'short_term' | 'medium_term' | 'long_term' | 'escalating';
  timeline_detail: string;
  cascade_effect: CascadeEffect | string | null;
}

export interface BlindSpots {
  underrepresented_groups: string;
  unmodeled_effects: string;
  data_gaps: string;
  coverage_note: string;
  panel_skew_warning?: string;
}

// ── Benefits layer ──────────────────────────────────────────────────────────

export interface BenefitItem {
  benefit: string;
  mechanism: string;
  magnitude: 1 | 2 | 3;
  category: string;
  primary_beneficiaries: string;
  cities_most_affected: string[];
  caveat: string | null;
  source_specialist: string;
}

export interface NetImpactGroup {
  avg_net: number;
  avg_risk: number;
  avg_benefit: number;
  count: number;
}

export interface ValidatorNetImpact {
  agent_id: number;
  city: string;
  tenure: string;
  age_bracket: string;
  income_bracket: string;
  risk_score: number;
  benefit_score: number;
  net_impact: number;
  matched_benefits: string[];
}

export interface BenefitsData {
  benefit_items: BenefitItem[];
  net_impacts: ValidatorNetImpact[];
  net_by_tenure: Record<string, NetImpactGroup>;
  net_by_income: Record<string, NetImpactGroup>;
  net_by_age: Record<string, NetImpactGroup>;
  top_benefits: BenefitItem[];
  summary: {
    net_positive_validators: number;
    net_negative_validators: number;
    net_neutral_validators: number;
    total_benefit_items: number;
  };
}

export interface RiskReport {
  risks: RiskReportItem[];
  blind_spots: BlindSpots | string;
  overall_risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
  key_insight: string;
}

export interface SimulationOutput {
  policy: string;
  total_time_seconds: number;
  specialists_total: number;
  validators_total: number;
  models: {
    specialist: string;
    validator: string;
    coordinator: string;
  };
  round_1_specialists: SpecialistResult[];
  specialist_risks: SpecialistRisk[];
  round_2_validators: ValidatorResult[];
  round_2b_deliberative?: DeliberativeResult[];
  risk_report: RiskReport;
  confidence?: {
    score: number;
    out_of: number;
    summary: string;
    caveat: string;
    checks: { status: 'pass' | 'warn' | 'fail' | 'info'; label: string }[];
    reason: string;
  };
  policy_classification?: {
    type: string;
    primary_affected: string;
    market: string;
    geography: string;
    time_horizon: string;
    key_attributes: string[];
  };
  seal_id?: string;
  demographic_tensions?: DemographicTension[];
  benefits?: BenefitsData;
}

// ── Stage2 animation entry ──────────────────────────────────────────────────

export interface AnimationEntry {
  id: number;
  label: string;      // city or specialist title (short)
  sublabel: string;   // tenure/age or specialist category
  concern: string;    // top risk text
  signal: 'positive' | 'negative' | 'mixed';
}

// ── SSE events from server ──────────────────────────────────────────────────

export type SimulationEvent =
  | { type: 'status'; message: string }
  | { type: 'r1_complete'; specialists: SpecialistResult[]; specialist_risks: SpecialistRisk[] }
  | { type: 'r2_complete'; validators: ValidatorResult[] }
  | { type: 'r2b_complete'; deliberative: DeliberativeResult[] }
  | { type: 'done'; data: SimulationOutput }
  | { type: 'error'; message: string };
