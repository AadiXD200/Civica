import React, { useState } from 'react';
import { motion } from 'framer-motion';
import type {
  BenefitItem, BenefitsData, Citation, CityDataUsed, CohortStats,
  DemographicTension, NetImpactGroup, PersonaProfile,
  SimulationOutput, SpecialistRisk, ValidatorResult,
} from '../types';
import { exportReportPDF } from '../utils/exportPDF';
import './Stage3.css';

const SPECIALIST_LABELS: Record<string, string> = {
  labor_economist: 'Labor Economist',
  urban_planner: 'Urban Planner',
  fiscal_analyst: 'Fiscal Analyst',
  housing_economist: 'Housing Economist',
  social_equity_researcher: 'Equity Researcher',
  regional_development_analyst: 'Regional Analyst',
  construction_industry_analyst: 'Construction Analyst',
  demographic_economist: 'Demographic Economist',
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function severityColor(sev: number | string): string {
  if (sev === 3 || sev === 'HIGH') return 'var(--signal-negative)';
  if (sev === 2 || sev === 'MEDIUM') return 'var(--signal-mixed)';
  return 'var(--signal-positive)';
}

function severityLabel(sev: number): string {
  return sev === 3 ? 'HIGH' : sev === 2 ? 'MED' : 'LOW';
}

function magnitudeColor(mag: number): string {
  if (mag === 3) return 'var(--signal-positive)';
  if (mag === 2) return 'var(--accent-blue, #4a9eff)';
  return 'var(--text-muted)';
}

function magnitudeLabel(mag: number): string {
  return mag === 3 ? 'SUBSTANTIAL' : mag === 2 ? 'MODERATE' : 'MINOR';
}

function netColor(net: number): string {
  if (net > 0.5) return 'var(--signal-positive)';
  if (net > 0) return 'var(--accent-blue, #4a9eff)';
  if (net < -0.5) return 'var(--signal-negative)';
  if (net < 0) return 'var(--signal-mixed)';
  return 'var(--text-muted)';
}

function getConfirmingValidators(validators: ValidatorResult[], riskIndex: number) {
  return validators.filter(v =>
    v.validations.some(val => val.risk_index === riskIndex && val.applies)
  );
}

function getTopValidationForAgent(v: ValidatorResult) {
  return v.validations
    .filter(val => val.applies && val.severity_for_me > 0)
    .sort((a, b) => b.severity_for_me - a.severity_for_me)[0] ?? null;
}

// ── Donut Chart (pure SVG) ────────────────────────────────────────────────────

interface DonutSlice { label: string; value: number; color: string; }

const DonutChart: React.FC<{ slices: DonutSlice[]; total: number; label: string; size?: number }> = ({
  slices, total, label, size = 80,
}) => {
  const r = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  let offset = 0;

  const segments = slices.filter(s => s.value > 0).map(s => {
    const pct = s.value / total;
    const dashArray = `${pct * circumference} ${circumference}`;
    const rotation = offset * 360 - 90;
    offset += pct;
    return { ...s, dashArray, rotation };
  });

  return (
    <div className="donut-chart">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-sharp)" strokeWidth="8" />
        {segments.map((seg, i) => (
          <circle
            key={i}
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={seg.color}
            strokeWidth="8"
            strokeDasharray={seg.dashArray}
            strokeDashoffset="0"
            transform={`rotate(${seg.rotation} ${cx} ${cy})`}
            style={{ transition: 'stroke-dasharray 0.3s ease' }}
          />
        ))}
      </svg>
      <div className="donut-label">{label}</div>
    </div>
  );
};

// ── Net Impact Bar ────────────────────────────────────────────────────────────

const NetImpactBar: React.FC<{ group: string; data: NetImpactGroup; maxAbsNet: number }> = ({
  group, data, maxAbsNet,
}) => {
  const scale = maxAbsNet > 0 ? Math.abs(data.avg_net) / maxAbsNet : 0;
  const pct = Math.round(scale * 50); // max 50% of bar width per side
  const isPositive = data.avg_net >= 0;
  const col = netColor(data.avg_net);
  const label = data.avg_net > 0.3 ? 'net gain' : data.avg_net < -0.3 ? 'net loss' : 'neutral';

  return (
    <div className="net-impact-row">
      <span className="net-group-label">{group}</span>
      <div className="net-bar-container">
        <div className="net-bar-center" />
        <div
          className="net-bar-fill"
          style={{
            width: `${pct}%`,
            backgroundColor: col,
            left: isPositive ? '50%' : undefined,
            right: isPositive ? undefined : `${50 - pct}%`,
            marginLeft: isPositive ? 0 : undefined,
          }}
        />
      </div>
      <span className="net-bar-value" style={{ color: col }}>
        {data.avg_net > 0 ? '+' : ''}{data.avg_net.toFixed(1)} <span className="net-bar-sublabel">({label})</span>
      </span>
      <span className="net-bar-count">{data.count} validators</span>
    </div>
  );
};

// ── Timeline Swimlane ─────────────────────────────────────────────────────────

const TIMELINE_ORDER = ['immediate', 'short_term', 'medium_term', 'long_term', 'escalating'];
const TIMELINE_LABELS: Record<string, string> = {
  immediate: '0–6 mo',
  short_term: '6mo–2yr',
  medium_term: '2–5yr',
  long_term: '5yr+',
  escalating: 'escalating',
};

interface TimelineRisk {
  title: string;
  severity: string;
  timeline: string;
  confirmed_by: number;
  out_of: number;
}

const TimelineSwimlane: React.FC<{ risks: TimelineRisk[] }> = ({ risks }) => {
  const byTimeline: Record<string, TimelineRisk[]> = {};
  for (const t of TIMELINE_ORDER) byTimeline[t] = [];
  for (const r of risks) {
    const key = r.timeline || 'short_term';
    if (!byTimeline[key]) byTimeline[key] = [];
    byTimeline[key].push(r);
  }

  const hasAny = risks.length > 0;
  if (!hasAny) return null;

  return (
    <div className="timeline-swimlane">
      <div className="timeline-header-row">
        {TIMELINE_ORDER.map(t => (
          <div key={t} className="timeline-col-header">{TIMELINE_LABELS[t]}</div>
        ))}
      </div>
      <div className="timeline-body-row">
        {TIMELINE_ORDER.map(t => (
          <div key={t} className="timeline-col">
            {(byTimeline[t] || []).map((r, i) => (
              <div
                key={i}
                className="timeline-risk-pill"
                style={{ borderColor: severityColor(r.severity) }}
                title={`${r.title} — ${r.confirmed_by}/${r.out_of} confirmed`}
              >
                <span
                  className="timeline-pill-dot"
                  style={{ backgroundColor: severityColor(r.severity) }}
                />
                <span className="timeline-pill-text">
                  {r.title.length > 40 ? r.title.substring(0, 40) + '…' : r.title}
                </span>
                <span className="timeline-pill-conf">{r.confirmed_by}/{r.out_of}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

// ── City Exposure Heatmap ─────────────────────────────────────────────────────

const CityHeatmap: React.FC<{ validators: ValidatorResult[]; specialistRisks: SpecialistRisk[] }> = ({
  validators, specialistRisks: _specialistRisks,
}) => {
  // Score each city: sum of (severity × population_weight) for confirmed risks
  const cityScores: Record<string, { score: number; count: number; confirmed: number }> = {};

  for (const v of validators) {
    const city = v.city;
    if (!cityScores[city]) cityScores[city] = { score: 0, count: 0, confirmed: 0 };
    cityScores[city].count++;
    const pw = v.population_weight || 1;
    for (const val of v.validations) {
      if (val.applies && val.severity_for_me > 0) {
        cityScores[city].score += val.severity_for_me * pw;
        cityScores[city].confirmed++;
      }
    }
  }

  const sorted = Object.entries(cityScores)
    .map(([city, d]) => ({ city, ...d }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 15);

  if (sorted.length === 0) return null;
  const maxScore = sorted[0].score;

  return (
    <div className="city-heatmap">
      {sorted.map(({ city, score, confirmed }) => {
        const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
        const intensity = pct / 100;
        const col = `rgba(${Math.round(220 * intensity)}, ${Math.round(50 * (1 - intensity))}, ${Math.round(50 * (1 - intensity))}, ${0.3 + intensity * 0.7})`;
        return (
          <div key={city} className="heatmap-row">
            <span className="heatmap-city">{city}</span>
            <div className="heatmap-bar-track">
              <div
                className="heatmap-bar-fill"
                style={{ width: `${pct}%`, backgroundColor: col }}
              />
            </div>
            <span className="heatmap-stat">{confirmed} confirmations</span>
          </div>
        );
      })}
    </div>
  );
};

// ── Confidence Panel ──────────────────────────────────────────────────────────

const STATUS_ICON: Record<string, string> = {
  pass: '✓', warn: '⚠', fail: '✕', info: '○',
};
const STATUS_COLOR: Record<string, string> = {
  pass: 'var(--signal-positive)',
  warn: 'var(--signal-mixed)',
  fail: 'var(--signal-negative)',
  info: 'var(--text-muted)',
};

const ConfidencePanel: React.FC<{ confidence: NonNullable<SimulationOutput['confidence']> }> = ({ confidence }) => {
  const [open, setOpen] = useState(false);
  const pct = Math.round((confidence.score / confidence.out_of) * 100);

  return (
    <div className="confidence-panel">
      <button className="confidence-header" onClick={() => setOpen(o => !o)}>
        <div className="confidence-score-row">
          <span className="confidence-score-label">CONFIDENCE</span>
          <span className="confidence-score-value">{confidence.score}/{confidence.out_of}</span>
          <div className="confidence-bar-track">
            <div
              className="confidence-bar-fill"
              style={{
                width: `${pct}%`,
                backgroundColor: pct >= 85 ? 'var(--signal-positive)' : pct >= 65 ? 'var(--signal-mixed)' : 'var(--signal-negative)',
              }}
            />
          </div>
          <span className="confidence-expand-hint">{open ? '[−]' : '[+]'}</span>
        </div>
        <p className="confidence-summary">{confidence.summary}</p>
      </button>
      {open && (
        <div className="confidence-checks">
          {confidence.checks.map((check, i) => (
            <div key={i} className="confidence-check-row">
              <span className="confidence-check-icon" style={{ color: STATUS_COLOR[check.status] }}>
                {STATUS_ICON[check.status]}
              </span>
              <span className="confidence-check-label" style={{ color: check.status === 'fail' ? 'var(--signal-negative)' : check.status === 'pass' ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
                {check.label}
              </span>
            </div>
          ))}
          <p className="confidence-caveat">{confidence.caveat}</p>
        </div>
      )}
    </div>
  );
};

// ── City Data Panel ───────────────────────────────────────────────────────────

const STATSCAN_URL = 'https://www150.statcan.gc.ca/n1/pub/71-607-x/71-607-x2018004-eng.htm';

function formatCityDataRow(label: string, value: string | number | undefined, unit?: string): { label: string; value: string } | null {
  if (value === undefined || value === null) return null;
  const formatted = typeof value === 'number'
    ? (unit === '$' ? `$${value.toLocaleString()}` : `${value.toLocaleString()}${unit ?? ''}`)
    : String(value);
  return { label, value: formatted };
}

const CityDataPanel: React.FC<{ city: string; data: CityDataUsed; ageBracket: string }> = ({ city, data, ageBracket }) => {
  const [open, setOpen] = useState(false);
  const rows = [
    formatCityDataRow('Avg rent (1BR)', data.avg_rent_1br, ' $/mo' as string),
    formatCityDataRow('Avg rent (2BR)', data.avg_rent_2br, ' $/mo' as string),
    formatCityDataRow('Vacancy rate', data.vacancy_rate, '%'),
    formatCityDataRow('Median household income', data.median_household_income, '$' as string),
    formatCityDataRow(`Median income (${ageBracket})`, data.income_for_age, '$' as string),
    formatCityDataRow('Shelter cost ratio', data.shelter_cost_to_income_ratio !== undefined ? Math.round(data.shelter_cost_to_income_ratio * 100) : undefined, '% of income'),
    formatCityDataRow('Unemployment rate', data.unemployment_rate, '%'),
    formatCityDataRow('Housing starts (annual)', data.housing_starts_annual),
    formatCityDataRow('Population growth', data.population_growth_rate, '%/yr'),
  ].filter(Boolean) as { label: string; value: string }[];
  if (rows.length === 0) return null;
  return (
    <div className="city-data-panel">
      <button className="city-data-toggle" onClick={() => setOpen(o => !o)}>
        <span className="city-data-toggle-icon">{open ? '▾' : '▸'}</span>
        <span>STATSCAN DATA — {city.toUpperCase()}</span>
      </button>
      {open && (
        <div className="city-data-rows">
          {rows.map(({ label, value }) => (
            <div key={label} className="city-data-row">
              <span className="city-data-label">{label}</span>
              <span className="city-data-value">{value}</span>
            </div>
          ))}
          <a className="city-data-source" href={STATSCAN_URL} target="_blank" rel="noopener noreferrer">
            Source: Statistics Canada ↗
          </a>
        </div>
      )}
    </div>
  );
};

// ── Persona Profile Panel ─────────────────────────────────────────────────────

const FRAGILITY_COLOR: Record<string, string> = {
  high: 'var(--signal-negative)', medium: 'var(--signal-mixed)', low: 'var(--signal-positive)',
};
const STANCE_LABEL: Record<string, string> = {
  supportive: 'supportive',
  skeptical_of_benefit: 'skeptical of benefit',
  indifferent: 'indifferent',
  opposed: 'opposed',
};

const PersonaPanel: React.FC<{ profile: PersonaProfile; cohortStats?: CohortStats }> = ({ profile, cohortStats }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="persona-panel">
      <button className="persona-toggle" onClick={() => setOpen(o => !o)}>
        <span className="persona-toggle-icon">{open ? '▾' : '▸'}</span>
        <span>PERSONA PROFILE</span>
        <span className="persona-fragility-chip" style={{ color: FRAGILITY_COLOR[profile.financial_fragility] }}>
          {profile.financial_fragility} fragility
        </span>
      </button>
      {open && (
        <div className="persona-body">
          <div className="persona-row">
            <span className="persona-label">STANCE</span>
            <span className="persona-value">{STANCE_LABEL[profile.policy_stance] ?? profile.policy_stance}</span>
          </div>
          {profile.top_concerns.length > 0 && (
            <div className="persona-row">
              <span className="persona-label">CONCERNS</span>
              <div className="persona-concerns">
                {profile.top_concerns.map((c, i) => <span key={i} className="persona-concern-chip">{c}</span>)}
              </div>
            </div>
          )}
          {profile.lived_experience_note && (
            <div className="persona-row">
              <span className="persona-label">CONTEXT</span>
              <p className="persona-note">"{profile.lived_experience_note}"</p>
            </div>
          )}
          {profile.sector_profile ? (
            <div className="persona-chs-block">
              <span className="persona-label">AI SECTOR EXPOSURE</span>
              <div className="persona-chs-stats">
                <span className="chs-stat">sector: {profile.sector_profile.sector_label}</span>
                <span className={`chs-stat ${profile.sector_profile.exposure_level === 'high' ? 'chs-stat-severe' : ''}`}>
                  {profile.sector_profile.sector_ai_adoption_pct}% AI adoption in sector (national avg: 6.1%)
                </span>
                <span className={`chs-stat fragility-${profile.sector_profile.exposure_level}`}>
                  {profile.sector_profile.exposure_level.toUpperCase()} AI exposure
                </span>
              </div>
              <span className="chs-source">Source: Statistics Canada AI Adoption Survey Q2 2024</span>
            </div>
          ) : cohortStats && cohortStats.n_matched_unweighted > 0 ? (
            <div className="persona-chs-block">
              <span className="persona-label">CHS 2022 MICRODATA</span>
              <div className="persona-chs-stats">
                {cohortStats.core_housing_need_pct != null && (
                  <span className="chs-stat">{cohortStats.core_housing_need_pct}% core housing need</span>
                )}
                {cohortStats.shelter_cost_30pct_plus_pct != null && (
                  <span className="chs-stat">{cohortStats.shelter_cost_30pct_plus_pct}% spend ≥30% on shelter</span>
                )}
                {cohortStats.shelter_cost_100pct_plus_pct != null && cohortStats.shelter_cost_100pct_plus_pct > 0 && (
                  <span className="chs-stat chs-stat-severe">{cohortStats.shelter_cost_100pct_plus_pct}% spend entire income on shelter</span>
                )}
                {cohortStats.median_household_income != null && (
                  <span className="chs-stat">median income ${cohortStats.median_household_income.toLocaleString()}</span>
                )}
                {cohortStats.on_waitlist_pct != null && cohortStats.on_waitlist_pct > 0 && (
                  <span className="chs-stat">{cohortStats.on_waitlist_pct}% on social housing waitlist</span>
                )}
              </div>
              <span className="chs-source">
                n={cohortStats.n_matched_weighted.toLocaleString(undefined, { maximumFractionDigits: 0 })} weighted households
                {cohortStats.filters_applied.length > 0 ? ` · matched on ${cohortStats.filters_applied.join(', ')}` : ' · national average'}
              </span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

// ── Benefits Section ──────────────────────────────────────────────────────────

const BenefitCard: React.FC<{ benefit: BenefitItem }> = ({ benefit }) => {
  const [open, setOpen] = useState(false);
  const col = magnitudeColor(benefit.magnitude);
  return (
    <div className="benefit-card" style={{ borderLeftColor: col }}>
      <div className="benefit-card-header">
        <div className="benefit-card-badges">
          <span className="badge-specialist">{SPECIALIST_LABELS[benefit.source_specialist] || benefit.source_specialist}</span>
          <span className="badge-category">{benefit.category}</span>
          <span className="badge-severity" style={{ color: col }}>{magnitudeLabel(benefit.magnitude)}</span>
        </div>
        <button className="btn-expand" onClick={() => setOpen(e => !e)}>[{open ? '−' : '+'}]</button>
      </div>
      <p className="risk-card-text">{benefit.benefit}</p>
      <p className="benefit-beneficiaries">↑ {benefit.primary_beneficiaries}</p>
      {open && (
        <div className="risk-card-expanded">
          <div className="mechanism-block">
            <span className="mechanism-label">MECHANISM</span>
            <p className="mechanism-text">{benefit.mechanism}</p>
          </div>
          {benefit.caveat && (
            <div className="mechanism-block">
              <span className="mechanism-label">CAVEAT / LIMITATION</span>
              <p className="mechanism-text" style={{ color: 'var(--signal-mixed)' }}>{benefit.caveat}</p>
            </div>
          )}
          {benefit.cities_most_affected.length > 0 && (
            <div className="mechanism-block">
              <span className="mechanism-label">CITIES MOST AFFECTED</span>
              <div className="cities-list">
                {benefit.cities_most_affected.map(c => <span key={c} className="city-chip">{c}</span>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const BenefitsSection: React.FC<{ benefits: BenefitsData }> = ({ benefits }) => {

  const { benefit_items, net_by_tenure, net_by_income, net_by_age, summary } = benefits;
  if (benefit_items.length === 0) return null;

  const allNetGroups = { ...net_by_tenure, ...net_by_income, ...net_by_age };
  const maxAbsNet = Math.max(...Object.values(allNetGroups).map(g => Math.abs(g.avg_net)), 0.1);

  // Donut for net impact distribution
  const donutSlices = [
    { label: 'Net gain', value: summary.net_positive_validators, color: 'var(--signal-positive)' },
    { label: 'Neutral', value: summary.net_neutral_validators, color: 'var(--text-muted)' },
    { label: 'Net loss', value: summary.net_negative_validators, color: 'var(--signal-negative)' },
  ];

  return (
    <section className="section-benefits">
      <h4>WHO BENEFITS — {benefit_items.length} BENEFITS IDENTIFIED</h4>
      <p className="section-subheader">
        Direct gains this policy creates, identified by domain specialists. Net impact scores compare benefit gains against risk burden per demographic group.
      </p>

      {/* Net impact summary row */}
      <div className="benefits-summary-row">
        <div className="benefits-net-donut">
          <DonutChart
            slices={donutSlices}
            total={summary.net_positive_validators + summary.net_neutral_validators + summary.net_negative_validators}
            label="NET IMPACT"
            size={100}
          />
          <div className="donut-legend">
            {donutSlices.map(s => (
              <div key={s.label} className="donut-legend-item">
                <span className="donut-legend-dot" style={{ backgroundColor: s.color }} />
                <span style={{ color: s.color }}>{s.label}</span>
                <span className="donut-legend-count">{s.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="benefits-net-bars">
          <div className="net-bars-section">
            <span className="net-bars-title">BY TENURE</span>
            {Object.entries(net_by_tenure).sort((a, b) => b[1].avg_net - a[1].avg_net).map(([g, d]) => (
              <NetImpactBar key={g} group={g} data={d} maxAbsNet={maxAbsNet} />
            ))}
          </div>
          <div className="net-bars-section">
            <span className="net-bars-title">BY INCOME</span>
            {Object.entries(net_by_income).sort((a, b) => b[1].avg_net - a[1].avg_net).map(([g, d]) => (
              <NetImpactBar key={g} group={g} data={d} maxAbsNet={maxAbsNet} />
            ))}
          </div>
          <div className="net-bars-section">
            <span className="net-bars-title">BY AGE</span>
            {Object.entries(net_by_age).sort((a, b) => b[1].avg_net - a[1].avg_net).map(([g, d]) => (
              <NetImpactBar key={g} group={g} data={d} maxAbsNet={maxAbsNet} />
            ))}
          </div>
        </div>
      </div>

      {/* Benefit cards */}
      <div className="risk-cards-list" style={{ marginTop: '1.5rem' }}>
        {benefit_items.map((b, i) => <BenefitCard key={i} benefit={b} />)}
      </div>
    </section>
  );
};

// ── Demographic Breakdown Donuts ──────────────────────────────────────────────

const DemographicBreakdown: React.FC<{ validators: ValidatorResult[] }> = ({ validators }) => {
  const byTenure: Record<string, number> = {};
  const byIncome: Record<string, number> = {};
  const byAge: Record<string, number> = {};
  const byFragility: Record<string, number> = {};

  for (const v of validators) {
    byTenure[v.tenure] = (byTenure[v.tenure] || 0) + 1;
    const incGroup = ['very_low', 'low'].includes(v.income_bracket) ? 'low'
      : ['high', 'very_high'].includes(v.income_bracket) ? 'high' : 'medium';
    byIncome[incGroup] = (byIncome[incGroup] || 0) + 1;
    const ageGroup = ['18-24', '25-34'].includes(v.age_bracket) ? 'young'
      : v.age_bracket === '35-49' ? 'middle'
      : v.age_bracket === '50-64' ? 'older' : 'senior';
    byAge[ageGroup] = (byAge[ageGroup] || 0) + 1;
    const frag = v.behavioral_profile?.financial_fragility ?? 'medium';
    byFragility[frag] = (byFragility[frag] || 0) + 1;
  }

  const total = validators.length;

  const tenureSlices = [
    { label: 'renter', value: byTenure['renter'] || 0, color: 'var(--signal-mixed)' },
    { label: 'owner', value: byTenure['owner'] || 0, color: 'var(--accent-blue, #4a9eff)' },
  ];
  const incomeSlices = [
    { label: 'low', value: byIncome['low'] || 0, color: 'var(--signal-negative)' },
    { label: 'medium', value: byIncome['medium'] || 0, color: 'var(--signal-mixed)' },
    { label: 'high', value: byIncome['high'] || 0, color: 'var(--signal-positive)' },
  ];
  const ageSlices = [
    { label: 'young', value: byAge['young'] || 0, color: '#a78bfa' },
    { label: 'middle', value: byAge['middle'] || 0, color: '#60a5fa' },
    { label: 'older', value: byAge['older'] || 0, color: '#34d399' },
    { label: 'senior', value: byAge['senior'] || 0, color: '#f59e0b' },
  ];
  const fragilitySlices = [
    { label: 'high', value: byFragility['high'] || 0, color: 'var(--signal-negative)' },
    { label: 'medium', value: byFragility['medium'] || 0, color: 'var(--signal-mixed)' },
    { label: 'low', value: byFragility['low'] || 0, color: 'var(--signal-positive)' },
  ];

  return (
    <div className="demographic-breakdown">
      <div className="breakdown-donut-row">
        {[
          { slices: tenureSlices, label: 'TENURE' },
          { slices: incomeSlices, label: 'INCOME' },
          { slices: ageSlices, label: 'AGE' },
          { slices: fragilitySlices, label: 'FRAGILITY' },
        ].map(({ slices, label }) => (
          <div key={label} className="breakdown-donut-item">
            <DonutChart slices={slices} total={total} label={label} size={90} />
            <div className="donut-legend small">
              {slices.filter(s => s.value > 0).map(s => (
                <div key={s.label} className="donut-legend-item">
                  <span className="donut-legend-dot" style={{ backgroundColor: s.color }} />
                  <span style={{ color: s.color }}>{s.label}</span>
                  <span className="donut-legend-count">{Math.round(s.value / total * 100)}%</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Demographic Tensions Section ──────────────────────────────────────────────

const DIMENSION_LABEL: Record<string, string> = {
  tenure: 'TENURE SPLIT', income: 'INCOME SPLIT', geography: 'GEOGRAPHY SPLIT',
  age: 'AGE SPLIT', immigration: 'IMMIGRATION SPLIT',
};

const TensionsSection: React.FC<{ tensions: DemographicTension[]; specialistRisks: SpecialistRisk[] }> = ({ tensions, specialistRisks }) => {
  if (tensions.length === 0) return null;
  const byRisk: Record<number, DemographicTension[]> = {};
  for (const t of tensions) {
    if (!byRisk[t.risk_index]) byRisk[t.risk_index] = [];
    byRisk[t.risk_index].push(t);
  }
  return (
    <section className="section-tensions">
      <h4>DEMOGRAPHIC FAULT LINES — {tensions.length} SPLITS DETECTED</h4>
      <p className="section-subheader">Where validators of different demographics disagreed significantly on risk confirmation</p>
      <div className="tensions-grid">
        {Object.entries(byRisk).map(([riskIdx, ts]) => {
          const risk = specialistRisks[parseInt(riskIdx) - 1];
          return (
            <div key={riskIdx} className="tension-card">
              <div className="tension-risk-title">
                <span className="tension-risk-num">RISK {riskIdx}</span>
                <span className="tension-risk-text">{risk?.risk?.substring(0, 80) ?? '—'}{(risk?.risk?.length ?? 0) > 80 ? '…' : ''}</span>
              </div>
              {ts.map((t, i) => (
                <div key={i} className="tension-row">
                  <span className="tension-dimension">{DIMENSION_LABEL[t.dimension] ?? t.dimension}</span>
                  <div className="tension-bars">
                    <div className="tension-group">
                      <span className="tension-group-label">{t.group_a}</span>
                      <div className="tension-bar-track">
                        <div className="tension-bar-fill tension-bar-a" style={{ width: `${Math.round(t.rate_a * 100)}%` }} />
                      </div>
                      <span className="tension-rate">{Math.round(t.rate_a * 100)}%</span>
                    </div>
                    <div className="tension-group">
                      <span className="tension-group-label">{t.group_b}</span>
                      <div className="tension-bar-track">
                        <div className="tension-bar-fill tension-bar-b" style={{ width: `${Math.round(t.rate_b * 100)}%` }} />
                      </div>
                      <span className="tension-rate">{Math.round(t.rate_b * 100)}%</span>
                    </div>
                  </div>
                  <p className="tension-interpretation">{t.interpretation}</p>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
};

// ── Specialist Risk Card ──────────────────────────────────────────────────────

interface RiskCardProps {
  risk: SpecialistRisk;
  riskIndex: number;
  validators: ValidatorResult[];
  cascadeEffect?: string | null;
}

const SpecialistRiskCard: React.FC<RiskCardProps> = ({ risk, riskIndex, validators, cascadeEffect }) => {
  const [expanded, setExpanded] = useState(false);

  const confirming = getConfirmingValidators(validators, riskIndex);
  const total = validators.length;
  const pct = total > 0 ? (confirming.length / total) * 100 : 0;

  const byTenure: Record<string, number> = {};
  const byAge: Record<string, number> = {};
  const byIncome: Record<string, number> = {};
  const byFragility: Record<string, number> = { high: 0, medium: 0, low: 0 };
  for (const v of confirming) {
    byTenure[v.tenure] = (byTenure[v.tenure] || 0) + 1;
    byAge[v.age_bracket] = (byAge[v.age_bracket] || 0) + 1;
    byIncome[v.income_bracket] = (byIncome[v.income_bracket] || 0) + 1;
    const frag = v.behavioral_profile?.financial_fragility ?? 'medium';
    byFragility[frag] = (byFragility[frag] ?? 0) + 1;
  }
  const topAges = Object.entries(byAge).sort((a, b) => b[1] - a[1]).slice(0, 2);
  const topIncome = Object.entries(byIncome).sort((a, b) => b[1] - a[1])[0];
  const hasFragilityData = confirming.some(v => v.behavioral_profile);

  const topForAgents = validators.filter(v => {
    const top = getTopValidationForAgent(v);
    return top?.risk_index === riskIndex;
  });

  const topConfirmations = confirming
    .map(v => ({
      v,
      val: v.validations.find(val => val.risk_index === riskIndex && val.applies)!,
    }))
    .sort((a, b) => b.val.severity_for_me - a.val.severity_for_me)
    .slice(0, 3);

  const color = severityColor(risk.severity);

  return (
    <div className="risk-card" style={{ borderLeftColor: color }}>
      <div className="risk-card-header">
        <div className="risk-card-badges">
          <span className="badge-specialist">{SPECIALIST_LABELS[risk.source] || risk.source}</span>
          <span className="badge-category">{risk.category}</span>
          <span className="badge-severity" style={{ color }}>{severityLabel(risk.severity)}</span>
        </div>
        <button className="btn-expand" onClick={() => setExpanded(e => !e)}>[{expanded ? '−' : '+'}]</button>
      </div>

      <p className="risk-card-text">{risk.risk}</p>

      <div className="agreement-section">
        <div className="agreement-label">
          <span>AGENT AGREEMENT</span>
          <span style={{ color }}>{confirming.length}/{total} agents</span>
        </div>
        <div className="agreement-bar-track">
          <div className="agreement-bar-fill" style={{ width: `${pct}%`, backgroundColor: color }} />
        </div>
        {hasFragilityData && confirming.length > 0 && (
          <div className="fragility-breakdown">
            {byFragility.high > 0 && <span className="fragility-chip fragility-high">{byFragility.high} high fragility</span>}
            {byFragility.medium > 0 && <span className="fragility-chip fragility-medium">{byFragility.medium} medium</span>}
            {byFragility.low > 0 && <span className="fragility-chip fragility-low">{byFragility.low} low</span>}
          </div>
        )}
      </div>

      <div className="demo-row">
        <span className="demo-chip">{byTenure['renter'] ?? 0} renters</span>
        <span className="demo-chip">{byTenure['owner'] ?? 0} owners</span>
        {topAges.map(([age, count]) => <span key={age} className="demo-chip">{count}× {age}</span>)}
        {topIncome && <span className="demo-chip">{topIncome[1]}× {topIncome[0]} income</span>}
      </div>

      {topForAgents.length > 0 && (
        <div className="top-for-section">
          <span className="top-for-label">TOP PRIORITY FOR {topForAgents.length} AGENT{topForAgents.length !== 1 ? 'S' : ''}:</span>
          <div className="top-for-agents">
            {topForAgents.slice(0, 7).map(v => (
              <span key={v.agent_id} className="top-for-chip">
                [{v.agent_id.toString().padStart(2, '0')}] {v.city.substring(0, 3).toUpperCase()} {v.tenure}/{v.age_bracket}
              </span>
            ))}
            {topForAgents.length > 7 && <span className="top-for-chip dimmed">+{topForAgents.length - 7} more</span>}
          </div>
        </div>
      )}

      {expanded && (
        <div className="risk-card-expanded">
          <div className="mechanism-block">
            <span className="mechanism-label">MECHANISM</span>
            <p className="mechanism-text">{risk.mechanism}</p>
          </div>
          {risk.historical_precedent && (
            <div className="mechanism-block historical-precedent-block">
              <span className="mechanism-label">HISTORICAL PRECEDENT</span>
              <p className="mechanism-text historical-precedent-text">{risk.historical_precedent}</p>
            </div>
          )}
          {risk.most_exposed && (
            <div className="mechanism-block">
              <span className="mechanism-label">MOST EXPOSED</span>
              <p className="mechanism-text">{risk.most_exposed}</p>
            </div>
          )}
          {risk.cities_most_affected.length > 0 && (
            <div className="mechanism-block">
              <span className="mechanism-label">CITIES AFFECTED</span>
              <div className="cities-list">
                {risk.cities_most_affected.map(c => <span key={c} className="city-chip">{c}</span>)}
              </div>
            </div>
          )}
          {cascadeEffect && (
            <div className="mechanism-block cascade-block">
              <span className="mechanism-label">CASCADE EFFECT</span>
              <div className="cascade-chain">
                <span className="cascade-source">{risk.risk.substring(0, 60)}{risk.risk.length > 60 ? '…' : ''}</span>
                <span className="cascade-arrow">→ triggers →</span>
                <span className="cascade-target">
                  {typeof cascadeEffect === 'string' ? cascadeEffect : (cascadeEffect as any).triggers ?? String(cascadeEffect)}
                </span>
              </div>
            </div>
          )}
          {risk.citations && risk.citations.length > 0 && (
            <div className="mechanism-block">
              <span className="mechanism-label">SOURCES</span>
              <div className="citations-list">
                {risk.citations.map((cite: Citation, i: number) => (
                  <a key={i} className="citation-link" href={cite.url} target="_blank" rel="noopener noreferrer">
                    <span className="citation-index">[{i + 1}]</span>
                    <span className="citation-title">{cite.title} ↗</span>
                  </a>
                ))}
              </div>
            </div>
          )}
          {topConfirmations.length > 0 && (
            <div className="mechanism-block">
              <span className="mechanism-label">AGENT VOICES</span>
              {topConfirmations.map(({ v, val }) => (
                <div key={v.agent_id} className="confirmation-entry">
                  <span className="conf-agent">
                    [{v.agent_id.toString().padStart(2, '0')}] {v.city} · {v.tenure} · {v.age_bracket} · {v.income_bracket}
                  </span>
                  <span className="conf-reason">"{val.reason}"</span>
                  <span className="conf-sev" style={{ color: severityColor(val.severity_for_me) }}>
                    severity {val.severity_for_me}/3
                  </span>
                  {v.city_data_used && Object.keys(v.city_data_used).length > 0 && (
                    <CityDataPanel city={v.city} data={v.city_data_used} ageBracket={v.age_bracket} />
                  )}
                  {v.behavioral_profile && (
                    <PersonaPanel profile={v.behavioral_profile} cohortStats={v.cohort_stats} />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Public Reception Bar ──────────────────────────────────────────────────────

const STANCE_ORDER = ['supportive', 'skeptical_of_benefit', 'indifferent', 'opposed'] as const;
const STANCE_COLOR: Record<string, string> = {
  supportive: 'var(--signal-positive)',
  skeptical_of_benefit: 'var(--signal-mixed)',
  indifferent: 'var(--text-muted)',
  opposed: 'var(--signal-negative)',
};
const STANCE_SHORT: Record<string, string> = {
  supportive: 'SUPPORTIVE',
  skeptical_of_benefit: 'SKEPTICAL',
  indifferent: 'INDIFFERENT',
  opposed: 'OPPOSED',
};

const PublicReceptionBar: React.FC<{ validators: ValidatorResult[] }> = ({ validators }) => {
  const counts: Record<string, number> = {};
  for (const v of validators) {
    const stance = v.behavioral_profile?.policy_stance ?? 'indifferent';
    counts[stance] = (counts[stance] ?? 0) + 1;
  }
  const total = validators.length;
  if (total === 0) return null;
  const segments = STANCE_ORDER.map(s => ({ stance: s, count: counts[s] ?? 0 })).filter(s => s.count > 0);

  return (
    <div className="reception-bar-container">
      <div className="reception-bar-label">
        <span>PUBLIC RECEPTION</span>
        <span className="reception-bar-note">{total} demographically representative Canadians</span>
      </div>
      <div className="reception-bar-track">
        {segments.map(({ stance, count }) => {
          const pct = (count / total) * 100;
          return (
            <div
              key={stance}
              className="reception-bar-segment"
              style={{ width: `${pct}%`, backgroundColor: STANCE_COLOR[stance] }}
              title={`${STANCE_SHORT[stance]}: ${count} validators (${Math.round(pct)}%)`}
            >
              {pct >= 14 && <span className="reception-bar-segment-label">{count}</span>}
            </div>
          );
        })}
      </div>
      <div className="reception-bar-legend">
        {segments.map(({ stance, count }) => (
          <span key={stance} className="reception-legend-item">
            <span className="reception-legend-dot" style={{ backgroundColor: STANCE_COLOR[stance] }} />
            <span style={{ color: STANCE_COLOR[stance] }}>{STANCE_SHORT[stance]}</span>
            <span className="reception-legend-count">{count}</span>
          </span>
        ))}
      </div>
    </div>
  );
};

// ── Main Stage3 ───────────────────────────────────────────────────────────────

interface Props {
  data: SimulationOutput;
  onRestart: () => void;
  onBack?: () => void;
}

export const Stage3Findings: React.FC<Props> = ({ data, onRestart, onBack }) => {
  const { risk_report, round_2_validators, specialist_risks } = data;
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try { await exportReportPDF(data.seal_id); }
    finally { setExporting(false); }
  };

  const riskLevelColor = severityColor(risk_report.overall_risk_level);
  const agentTopRisks = round_2_validators.map(v => {
    const top = getTopValidationForAgent(v);
    const topRisk = top ? specialist_risks[top.risk_index - 1] : null;
    return { validator: v, topValidation: top, topRisk };
  });
  const personaRisks = round_2_validators.filter(v => v.missed_risk != null);

  // Timeline data from coordinator risks
  const timelineRisks = risk_report.risks.map(r => ({
    title: r.title,
    severity: r.severity,
    timeline: r.timeline,
    confirmed_by: r.confirmed_by,
    out_of: r.out_of,
  }));

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 1, transition: { duration: 0 } }}
      transition={{ duration: 0.3 }}
      className="stage3-container"
    >
      <div className="stage3-inner">
        {/* ── Nav ── */}
        <div className="report-nav">
          <button className="btn-nav-report" onClick={onBack}>[ ← REVIEW SIMULATION ]</button>
          <button className="btn-nav-report" onClick={onRestart}>[ ✕ NEW SIMULATION ]</button>
          <button className="btn-nav-report btn-export" onClick={handleExport} disabled={exporting}>
            {exporting ? '[ GENERATING PDF... ]' : '[ ↓ EXPORT REPORT ]'}
          </button>
        </div>

        {/* ── Header ── */}
        <header className="report-header">
          <div className="report-meta">
            <span>CLASSIFIED INTELLIGENCE REPORT</span>
            <span>SEAL: {data.seal_id || '—'}</span>
          </div>
          <div className="report-policy">
            <h2>POLICY DIRECTIVE</h2>
            <p>{data.policy}</p>
          </div>
        </header>

        <div className="report-body">

          {/* ── Intelligence Summary ── */}
          <section className="section-summary">
            <h4>INTELLIGENCE SUMMARY</h4>
            <div className="summary-meta-row">
              <div className="summary-stat">
                <span className="summary-label">OVERALL RISK</span>
                <span className="risk-level-badge" style={{ color: riskLevelColor, borderColor: riskLevelColor }}>
                  {risk_report.overall_risk_level}
                </span>
              </div>
              <div className="summary-stat">
                <span className="summary-label">SPECIALISTS</span>
                <span className="summary-value">{data.specialists_total}</span>
              </div>
              <div className="summary-stat">
                <span className="summary-label">VALIDATORS</span>
                <span className="summary-value">{data.validators_total}</span>
              </div>
              {data.benefits && (
                <div className="summary-stat">
                  <span className="summary-label">BENEFITS IDENTIFIED</span>
                  <span className="summary-value" style={{ color: 'var(--signal-positive)' }}>
                    {data.benefits.summary.total_benefit_items}
                  </span>
                </div>
              )}
              {data.benefits && (
                <div className="summary-stat">
                  <span className="summary-label">NET POSITIVE</span>
                  <span className="summary-value" style={{ color: 'var(--signal-positive)' }}>
                    {data.benefits.summary.net_positive_validators}/{data.validators_total}
                  </span>
                </div>
              )}
            </div>

            <h1 className="emergent-headline">{risk_report.key_insight}</h1>

            <PublicReceptionBar validators={round_2_validators} />

            {/* Demographic breakdown donuts */}
            <DemographicBreakdown validators={round_2_validators} />

            {risk_report.blind_spots && (
              <div className="blind-spots-note">
                <span className="blind-label">BLIND SPOTS —</span>{' '}
                {typeof risk_report.blind_spots === 'string'
                  ? risk_report.blind_spots
                  : (
                    <span>
                      {risk_report.blind_spots.underrepresented_groups}
                      {risk_report.blind_spots.unmodeled_effects && <> · {risk_report.blind_spots.unmodeled_effects}</>}
                      {risk_report.blind_spots.coverage_note && <> · <em>{risk_report.blind_spots.coverage_note}</em></>}
                      {(risk_report.blind_spots as any).panel_skew_warning && (
                        <> · <em style={{ color: 'var(--signal-mixed)' }}>{(risk_report.blind_spots as any).panel_skew_warning}</em></>
                      )}
                    </span>
                  )
                }
              </div>
            )}

            {data.confidence && <ConfidencePanel confidence={data.confidence} />}
          </section>

          {/* ── Risk Timeline ── */}
          {timelineRisks.length > 0 && (
            <section className="section-timeline">
              <h4>RISK TIMELINE — WHEN RISKS MATERIALIZE</h4>
              <p className="section-subheader">
                Coordinator-ranked risks positioned by when they emerge after implementation
              </p>
              <TimelineSwimlane risks={timelineRisks} />
            </section>
          )}

          {/* ── Benefits Layer ── */}
          {data.benefits && data.benefits.benefit_items.length > 0 && (
            <BenefitsSection benefits={data.benefits} />
          )}

          {/* ── City Exposure Heatmap ── */}
          <section className="section-city-heatmap">
            <h4>CITY EXPOSURE — RISK BURDEN BY LOCATION</h4>
            <p className="section-subheader">Weighted risk confirmation score per city — higher = validators in that city confirmed more and higher-severity risks</p>
            <CityHeatmap validators={round_2_validators} specialistRisks={specialist_risks} />
          </section>

          {/* ── Specialist Risk Assessment ── */}
          <section className="section-specialist-risks">
            <h4>SPECIALIST RISK ASSESSMENT — {specialist_risks.length} RISKS IDENTIFIED · CLICK TO EXPAND</h4>
            <div className="risk-cards-list">
              {specialist_risks.map((risk, i) => {
                const ranked = risk_report.risks.find(rr =>
                  rr.title && (
                    risk.risk.toLowerCase().includes(rr.title.toLowerCase().split(' ').slice(0, 3).join(' ')) ||
                    rr.title.toLowerCase().includes(risk.risk.toLowerCase().split(' ').slice(0, 3).join(' '))
                  )
                );
                const cascade = ranked?.cascade_effect ?? null;
                const cascadeStr = cascade
                  ? typeof cascade === 'string' ? cascade : (cascade as any).triggers ?? null
                  : null;
                return (
                  <SpecialistRiskCard
                    key={i}
                    risk={risk}
                    riskIndex={i + 1}
                    validators={round_2_validators}
                    cascadeEffect={cascadeStr}
                  />
                );
              })}
            </div>
          </section>

          {/* ── Agent Top Priorities ── */}
          <section className="section-agent-priorities">
            <h4>AGENT TOP PRIORITIES — WHAT EACH VALIDATOR RANKED MOST CRITICAL</h4>
            <div className="archive-strip">
              {agentTopRisks.map(({ validator: v, topValidation, topRisk }) => (
                <div key={v.agent_id} className="priority-card">
                  <div className="a-id">[{v.agent_id.toString().padStart(2, '0')}] {v.city.substring(0, 3).toUpperCase()}</div>
                  <div className="a-demo">{v.tenure} / {v.age_bracket} / {v.income_bracket}</div>
                  {topRisk && topValidation ? (
                    <>
                      <div className="a-priority-risk" style={{ borderLeft: `2px solid ${severityColor(topValidation.severity_for_me)}` }}>
                        {topRisk.risk.length > 80 ? topRisk.risk.substring(0, 80) + '…' : topRisk.risk}
                      </div>
                      <div className="a-sev-dots">
                        {[1, 2, 3].map(n => (
                          <span key={n} className="sev-dot" style={{
                            backgroundColor: n <= topValidation.severity_for_me
                              ? severityColor(topValidation.severity_for_me)
                              : 'var(--border-sharp)',
                          }} />
                        ))}
                      </div>
                      <div className="a-reason">"{topValidation.reason.substring(0, 70)}{topValidation.reason.length > 70 ? '…' : ''}"</div>
                    </>
                  ) : (
                    <div className="a-no-priority">no risks confirmed</div>
                  )}
                  {v.missed_risk && <div className="a-proposed-badge">+ proposed own risk</div>}
                  {v.city_data_used && Object.keys(v.city_data_used).length > 0 && (
                    <CityDataPanel city={v.city} data={v.city_data_used} ageBracket={v.age_bracket} />
                  )}
                  {v.behavioral_profile && (
                    <PersonaPanel profile={v.behavioral_profile} cohortStats={v.cohort_stats} />
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* ── Demographic Fault Lines ── */}
          {data.demographic_tensions && data.demographic_tensions.length > 0 && (
            <TensionsSection tensions={data.demographic_tensions} specialistRisks={specialist_risks} />
          )}

          {/* ── Persona-Generated Risks ── */}
          {personaRisks.length > 0 && (
            <section className="section-persona-risks">
              <h4>PERSONA-GENERATED RISKS — {personaRisks.length} RISKS FLAGGED BY VALIDATORS</h4>
              <p className="section-subheader">Risks identified by demographic personas that specialists did not surface</p>
              <div className="persona-risk-grid">
                {personaRisks.map(v => (
                  <div key={v.agent_id} className="persona-risk-card">
                    <div className="persona-agent-header">
                      <span className="prc-id">[{v.agent_id.toString().padStart(2, '0')}]</span>
                      <span className="prc-city">{v.city}</span>
                      <span className="prc-demo">{v.tenure} · {v.age_bracket} · {v.income_bracket}</span>
                    </div>
                    <p className="prc-risk">"{v.missed_risk!.risk}"</p>
                    <div className="prc-footer">
                      <span className="badge-category">{v.missed_risk!.category}</span>
                      <span className="badge-severity" style={{ color: severityColor(v.missed_risk!.severity) }}>
                        {severityLabel(v.missed_risk!.severity)}
                      </span>
                      <span className="prc-employment">{v.employment_type}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="report-footer-nav">
            <button className="btn-nav-report" onClick={onBack}>[ ← REVIEW SIMULATION ]</button>
            <button className="btn-nav-report" onClick={onRestart}>[ INITIALIZE NEW SIMULATION ]</button>
          </div>
        </div>
      </div>
    </motion.div>
  );
};
