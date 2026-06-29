import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { PolicyIntake } from '../types';
import '../stage1.css';

interface Props {
  onSubmit: (policy: string, intake: PolicyIntake) => void;
  loading?: boolean;
  statusMessage?: string;
  error?: string;
}

type Screen = 'policy' | 'intake';
type InputMode = 'paste' | 'structured';

interface ChipGroupProps {
  label: string;
  options: { value: string; display: string }[];
  selected: string;
  onChange: (v: string) => void;
}

const ChipGroup: React.FC<ChipGroupProps> = ({ label, options, selected, onChange }) => (
  <div className="chip-group">
    <div className="chip-label">{label}</div>
    <div className="chip-row">
      {options.map(opt => (
        <button
          key={opt.value}
          className={`chip ${selected === opt.value ? 'chip-active' : ''}`}
          onClick={() => onChange(selected === opt.value ? '' : opt.value)}
          type="button"
        >
          {opt.display}
        </button>
      ))}
    </div>
  </div>
);

const PRIMARY_AFFECTED_OPTIONS = [
  { value: 'all', display: 'Everyone' },
  { value: 'renters', display: 'Renters' },
  { value: 'owners', display: 'Homeowners' },
  { value: 'low_income', display: 'Low-income' },
  { value: 'workers', display: 'Workers' },
  { value: 'immigrants', display: 'Immigrants' },
  { value: 'seniors', display: 'Seniors' },
  { value: 'youth', display: 'Youth' },
  { value: 'indigenous', display: 'Indigenous' },
];

const GEOGRAPHY_OPTIONS = [
  { value: 'national', display: 'National' },
  { value: 'provincial', display: 'Provincial' },
  { value: 'urban', display: 'Urban' },
  { value: 'rural', display: 'Rural/Remote' },
  { value: 'regional', display: 'Regional' },
];

const TIME_HORIZON_OPTIONS = [
  { value: 'immediate', display: 'Immediate (<6mo)' },
  { value: 'short_term', display: 'Short-term (6mo–2yr)' },
  { value: 'long_term', display: 'Long-term (2yr+)' },
];

const MECHANISM_OPTIONS = [
  { value: 'supply', display: 'Build / Supply' },
  { value: 'tax', display: 'Tax / Subsidy' },
  { value: 'regulation', display: 'Regulation' },
  { value: 'transfer', display: 'Cash Transfer' },
  { value: 'services', display: 'Services' },
];

const MECHANISM_TYPE_OPTIONS = [
  { value: 'grant/subsidy', display: 'Grant / Subsidy' },
  { value: 'tax/levy', display: 'Tax / Levy' },
  { value: 'regulation/mandate', display: 'Regulation / Mandate' },
  { value: 'benefit/transfer', display: 'Benefit / Transfer' },
  { value: 'procurement', display: 'Procurement' },
  { value: 'other', display: 'Other' },
];

interface StructuredFields {
  policy_title: string;
  affected_entity: string;
  mechanism_type: string;
  mechanism_detail: string;
  trigger_threshold: string;
  penalty_or_incentive: string;
  exemptions: string;
  timeline: string;
  funding_mechanism: string;
  jurisdiction_notes: string;
  known_exclusions: string;
}

const emptyStructured = (): StructuredFields => ({
  policy_title: '',
  affected_entity: '',
  mechanism_type: '',
  mechanism_detail: '',
  trigger_threshold: '',
  penalty_or_incentive: '',
  exemptions: '',
  timeline: '',
  funding_mechanism: '',
  jurisdiction_notes: '',
  known_exclusions: '',
});

function serializeStructured(f: StructuredFields): string {
  const mechLine = f.mechanism_type
    ? `${f.mechanism_type}${f.mechanism_detail ? ' — ' + f.mechanism_detail : ''}`
    : f.mechanism_detail || 'Not specified';
  return [
    '[STRUCTURED POLICY INTAKE]',
    `Title: ${f.policy_title}`,
    `Affected Entity: ${f.affected_entity}`,
    `Mechanism: ${mechLine}`,
    `Trigger/Threshold: ${f.trigger_threshold || 'Not specified'}`,
    `Penalty/Incentive: ${f.penalty_or_incentive || 'Not specified'}`,
    `Exemptions: ${f.exemptions || 'None stated'}`,
    `Timeline: ${f.timeline || 'Not specified'}`,
    `Funding Mechanism: ${f.funding_mechanism || 'Not specified'}`,
    `Jurisdiction Notes: ${f.jurisdiction_notes || 'None stated'}`,
    `Known Exclusions: ${f.known_exclusions || 'None stated'}`,
  ].join('\n');
}

function structuredIsValid(f: StructuredFields): boolean {
  return f.policy_title.trim() !== '' && f.affected_entity.trim() !== '';
}

export const Stage1Input: React.FC<Props> = ({ onSubmit, loading = false, statusMessage, error }) => {
  const [screen, setScreen] = useState<Screen>('policy');
  const [inputMode, setInputMode] = useState<InputMode>('paste');
  const [policy, setPolicy] = useState('');
  const [structured, setStructured] = useState<StructuredFields>(emptyStructured());
  const [intake, setIntake] = useState<PolicyIntake>({});
  const [enablePeerReview, setEnablePeerReview] = useState(false);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (policy.trim() && !loading) setScreen('intake');
    }
  };

  const handleSubmit = () => {
    if (loading) return;
    const intakeWithPR = { ...intake, enable_peer_review: enablePeerReview };
    if (inputMode === 'paste') {
      if (policy.trim()) onSubmit(policy.trim(), intakeWithPR);
    } else {
      if (structuredIsValid(structured)) {
        onSubmit(serializeStructured(structured), intakeWithPR);
      }
    }
  };

  const setField = (field: keyof PolicyIntake) => (value: string) =>
    setIntake(prev => ({ ...prev, [field]: value || undefined }));

  const setSField = (field: keyof StructuredFields) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => setStructured(prev => ({ ...prev, [field]: e.target.value }));

  const canAdvance =
    inputMode === 'paste' ? policy.trim() !== '' : structuredIsValid(structured);

  const handleNext = () => {
    if (canAdvance && !loading) setScreen('intake');
  };

  const policyEcho =
    inputMode === 'paste'
      ? policy
      : structured.policy_title
        ? structured.policy_title
        : '[structured intake]';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 1, transition: { duration: 0 } }}
      transition={{ duration: 0.3 }}
      className="stage1-container"
    >
      <div className="meta-timestamp left-top">SYS_TIME: {new Date().toISOString()}</div>
      <div className="meta-stamp right-top">SPECIALISTS: 8 | VALIDATORS: 50</div>

      <div className="center-content">
        <AnimatePresence mode="wait">
          {/* ── Screen 1: Policy text ── */}
          {screen === 'policy' && !loading && (
            <motion.div
              key="policy-screen"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              style={{ width: '100%' }}
            >
              <motion.h1
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="prompt-header"
              >
                ENTER POLICY
              </motion.h1>

              {/* Mode toggle */}
              <div className="mode-toggle">
                <button
                  type="button"
                  className={`mode-tab ${inputMode === 'paste' ? 'mode-tab-active' : ''}`}
                  onClick={() => setInputMode('paste')}
                >
                  PASTE POLICY
                </button>
                <button
                  type="button"
                  className={`mode-tab ${inputMode === 'structured' ? 'mode-tab-active' : ''}`}
                  onClick={() => setInputMode('structured')}
                >
                  STRUCTURED INPUT
                </button>
              </div>

              <AnimatePresence mode="wait">
                {inputMode === 'paste' ? (
                  <motion.div
                    key="paste-mode"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    <motion.div
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ delay: 0.1, duration: 0.4 }}
                      className="input-wrapper"
                    >
                      <span className="caret">{'>_'}</span>
                      <textarea
                        autoFocus
                        value={policy}
                        onChange={(e) => setPolicy(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Awaiting directive..."
                        rows={3}
                        spellCheck={false}
                      />
                    </motion.div>
                  </motion.div>
                ) : (
                  <motion.div
                    key="structured-mode"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="structured-form"
                  >
                    <div className="sf-section-label">REQUIRED</div>

                    <div className="sf-field">
                      <label className="sf-label">POLICY TITLE</label>
                      <input
                        type="text"
                        className="sf-input"
                        placeholder="Short name for this policy..."
                        value={structured.policy_title}
                        onChange={setSField('policy_title')}
                        spellCheck={false}
                        autoFocus
                      />
                    </div>

                    <div className="sf-field">
                      <label className="sf-label">AFFECTED ENTITY</label>
                      <input
                        type="text"
                        className="sf-input"
                        placeholder='e.g. "landlords of buildings 5+ units", "employers with 50+ employees"'
                        value={structured.affected_entity}
                        onChange={setSField('affected_entity')}
                        spellCheck={false}
                      />
                    </div>

                    <div className="sf-field">
                      <label className="sf-label">MECHANISM</label>
                      <div className="sf-mechanism-row">
                        <select
                          className="sf-select"
                          value={structured.mechanism_type}
                          onChange={setSField('mechanism_type')}
                        >
                          <option value="">Select type...</option>
                          {MECHANISM_TYPE_OPTIONS.map(o => (
                            <option key={o.value} value={o.value}>{o.display}</option>
                          ))}
                        </select>
                        <input
                          type="text"
                          className="sf-input sf-mechanism-detail"
                          placeholder="Describe the specific mechanism..."
                          value={structured.mechanism_detail}
                          onChange={setSField('mechanism_detail')}
                          spellCheck={false}
                        />
                      </div>
                    </div>

                    <div className="sf-section-label sf-section-optional">OPTIONAL</div>

                    <div className="sf-optional-grid">
                      <div className="sf-field">
                        <label className="sf-label">TRIGGER / THRESHOLD</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder='e.g. "rents exceeding 110% of median", "$45/tonne CO2"'
                          value={structured.trigger_threshold}
                          onChange={setSField('trigger_threshold')}
                          spellCheck={false}
                        />
                      </div>

                      <div className="sf-field">
                        <label className="sf-label">PENALTY / INCENTIVE</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder='e.g. "$15,000/unit/year non-compliance penalty"'
                          value={structured.penalty_or_incentive}
                          onChange={setSField('penalty_or_incentive')}
                          spellCheck={false}
                        />
                      </div>

                      <div className="sf-field">
                        <label className="sf-label">EXEMPTIONS</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder='e.g. "new construction <10 years old"'
                          value={structured.exemptions}
                          onChange={setSField('exemptions')}
                          spellCheck={false}
                        />
                      </div>

                      <div className="sf-field">
                        <label className="sf-label">TIMELINE</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder='e.g. "Year 1: essential drugs. Year 3: full formulary."'
                          value={structured.timeline}
                          onChange={setSField('timeline')}
                          spellCheck={false}
                        />
                      </div>

                      <div className="sf-field">
                        <label className="sf-label">FUNDING MECHANISM</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder='e.g. "federal transfer to provinces", "carbon levy revenue recycling"'
                          value={structured.funding_mechanism}
                          onChange={setSField('funding_mechanism')}
                          spellCheck={false}
                        />
                      </div>

                      <div className="sf-field">
                        <label className="sf-label">JURISDICTION NOTES</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder='e.g. "requires provincial opt-in", "health is provincial jurisdiction"'
                          value={structured.jurisdiction_notes}
                          onChange={setSField('jurisdiction_notes')}
                          spellCheck={false}
                        />
                      </div>

                      <div className="sf-field sf-field-full">
                        <label className="sf-label">KNOWN EXCLUSIONS</label>
                        <input
                          type="text"
                          className="sf-input"
                          placeholder="Groups not covered by this policy (feeds into blind spots analysis)..."
                          value={structured.known_exclusions}
                          onChange={setSField('known_exclusions')}
                          spellCheck={false}
                        />
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="input-actions">
                <button
                  className="btn-submit"
                  disabled={!canAdvance}
                  onClick={handleNext}
                >
                  [ NEXT ]
                </button>
                {inputMode === 'paste' ? (
                  <span className="submit-hint">ENTER to continue · SHIFT+ENTER for new line</span>
                ) : (
                  <span className="submit-hint">Fill required fields to continue</span>
                )}
              </div>
            </motion.div>
          )}

          {/* ── Screen 2: Contextual framing ── */}
          {screen === 'intake' && !loading && (
            <motion.div
              key="intake-screen"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
              style={{ width: '100%' }}
            >
              <motion.h1
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.1 }}
                className="prompt-header intake-header"
              >
                FRAME POLICY
              </motion.h1>

              <div className="intake-policy-echo">
                <span className="caret">{'>_'}</span>
                <span className="intake-policy-text">"{policyEcho}"</span>
              </div>

              <div className="intake-layout">
                {/* ── Left: chip groups ── */}
                <div className="intake-chips">
                  <div className="intake-row-label">SPECIALIST AXIS</div>
                  <ChipGroup
                    label="WHAT IS THE MAIN MECHANISM?"
                    options={MECHANISM_OPTIONS}
                    selected={intake.mechanism ?? ''}
                    onChange={setField('mechanism')}
                  />

                  <div className="intake-row-label intake-row-label-gap">PERSONA AXES</div>
                  <ChipGroup
                    label="WHO DOES THIS PRIMARILY TARGET?"
                    options={PRIMARY_AFFECTED_OPTIONS}
                    selected={intake.primary_affected ?? ''}
                    onChange={setField('primary_affected')}
                  />
                  <ChipGroup
                    label="WHERE DOES IT APPLY?"
                    options={GEOGRAPHY_OPTIONS}
                    selected={intake.geography ?? ''}
                    onChange={setField('geography')}
                  />
                  <ChipGroup
                    label="WHEN DO EFFECTS KICK IN?"
                    options={TIME_HORIZON_OPTIONS}
                    selected={intake.time_horizon ?? ''}
                    onChange={setField('time_horizon')}
                  />

                  <div className="chip-group">
                    <div className="chip-label">KNOWN EXCLUSIONS <span className="chip-optional">(OPTIONAL)</span></div>
                    <textarea
                      className="intake-exclusions"
                      placeholder="Populations this policy intentionally excludes..."
                      rows={2}
                      value={intake.known_exclusions ?? ''}
                      onChange={(e) => setField('known_exclusions')(e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                </div>

                {/* ── Right: live intelligence panel ── */}
                <div className="intake-intel">
                  <div className="intel-header">LIVE INTELLIGENCE FED</div>
                  <div className="intel-block">
                    <div className="intel-block-label">SPECIALIST PANEL</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Labor Economist</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Housing Analyst</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Fiscal Analyst</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Public Health Expert</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Environmental Scientist</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Urban Planner</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Policy Critic</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />Benefits Analyst</div>
                  </div>
                  <div className="intel-block">
                    <div className="intel-block-label">VALIDATOR PANEL</div>
                    <div className="intel-item"><span className="intel-dot intel-dot-on" />50 demographic agents</div>
                    <div className="intel-item intel-sub">CHS 2022 PUMF microdata</div>
                    <div className="intel-item intel-sub">20 Canadian cities</div>
                    <div className="intel-item intel-sub">Weighted by population</div>
                  </div>
                  <div className="intel-block">
                    <div className="intel-block-label">DATA SOURCES</div>
                    <div className="intel-item intel-sub">StatsCan NHS 2021</div>
                    <div className="intel-item intel-sub">CMHC Housing Data</div>
                    <div className="intel-item intel-sub">CIHI Health Indicators</div>
                    <div className="intel-item intel-sub">LFS Labour Data</div>
                    <div className="intel-item intel-sub">IMDB Immigration DB</div>
                  </div>
                </div>
              </div>

              <div className="input-actions">
                <button className="btn-back" onClick={() => setScreen('policy')} type="button">
                  [ BACK ]
                </button>
                <button className="btn-submit" onClick={handleSubmit}>
                  [ SIMULATE ]
                </button>
                <label className="peer-review-toggle">
                  <input
                    type="checkbox"
                    checked={enablePeerReview}
                    onChange={(e) => setEnablePeerReview(e.target.checked)}
                  />
                  <span className="peer-review-label">
                    ADVERSARIAL REVIEW
                    <span className="peer-review-sub">(+30–60s)</span>
                  </span>
                </label>
                <span className="submit-hint">All fields optional — skip to run with inferred context</span>
              </div>
            </motion.div>
          )}

          {/* ── Loading state ── */}
          {loading && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="loading-block"
            >
              <div className="loading-policy">"{policyEcho}"</div>
              <div className="loading-status blink">
                {statusMessage || 'CONNECTING TO BACKBOARD...'}
              </div>
              <div className="loading-bar">
                <div className="loading-bar-fill" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="error-block"
          >
            <span className="error-label">ERROR —</span> {error}
            <button className="btn-retry" onClick={handleSubmit}>[ RETRY ]</button>
          </motion.div>
        )}
      </div>

      <div className="meta-stamp left-bottom">VER: 2.0.0-PROD</div>
      <div className="meta-stamp right-bottom">SCOPE: NATIONAL</div>
    </motion.div>
  );
};
