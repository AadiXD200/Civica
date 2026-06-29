import { jsPDF } from 'jspdf';
import type { SimulationOutput, RiskReportItem, BenefitItem, ValidatorResult } from '../types';

// ── Palette (light / print-ready) ────────────────────────────────────────────
const BLACK   = '#0a0a0a';
const INK     = '#1a1a1a';
const BODY    = '#2c2c2c';
const MUTED   = '#555555';
const SUBTLE  = '#888888';
const RULE    = '#cccccc';
const PANEL   = '#f4f4f2';
const PANEL2  = '#eaeae7';
const WHITE   = '#ffffff';

const ACCENT  = '#0a3d62';   // deep navy — headers, labels
const RED     = '#c0392b';   // HIGH risk
const AMBER   = '#d68910';   // MEDIUM / warn
const GREEN   = '#1e8449';   // LOW / positive
const BLUE    = '#1a5276';   // insight accent

function hexToRgb(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b];
}
const sf = (pdf: jsPDF, hex: string) => pdf.setFillColor(...hexToRgb(hex));
const sd = (pdf: jsPDF, hex: string) => pdf.setDrawColor(...hexToRgb(hex));
const st = (pdf: jsPDF, hex: string) => pdf.setTextColor(...hexToRgb(hex));

const W      = 210;
const MARGIN = 16;
const CW     = W - MARGIN * 2;

// ── Severity helpers ──────────────────────────────────────────────────────────
function sevColor(s: string | number): string {
  if (s === 'HIGH' || s === 3) return RED;
  if (s === 'LOW'  || s === 1) return GREEN;
  return AMBER;
}
function sevLabel(s: string | number): string {
  if (s === 3) return 'HIGH';
  if (s === 1) return 'LOW';
  if (s === 'HIGH' || s === 'MEDIUM' || s === 'LOW') return String(s);
  return 'MED';
}

// ── Main export ───────────────────────────────────────────────────────────────
export async function exportReportPDF(data: SimulationOutput): Promise<void> {
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const PH  = pdf.internal.pageSize.getHeight(); // 297mm
  let y = 0;
  let pageNum = 0;

  // ── Low-level helpers ────────────────────────────────────────────────────────

  function whitePage() {
    sf(pdf, WHITE); pdf.rect(0, 0, W, PH, 'F');
  }

  function newPage() {
    pdf.addPage();
    whitePage();
    pageNum++;
    y = 18;
  }

  function chk(needed = 20) {
    if (y + needed > PH - 16) newPage();
  }

  function hRule(color = RULE, lw = 0.3) {
    sd(pdf, color); pdf.setLineWidth(lw);
    pdf.line(MARGIN, y, W - MARGIN, y);
    y += 3;
  }

  function vRule(x: number, y1: number, y2: number, color = RULE) {
    sd(pdf, color); pdf.setLineWidth(0.2);
    pdf.line(x, y1, x, y2);
  }

  // Minimal coloured bar — tracks y
  function sectionLabel(text: string, color = ACCENT) {
    chk(8);
    pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold');
    st(pdf, color);
    pdf.text(text.toUpperCase(), MARGIN, y);
    y += 5;
  }

  // Inline badge (filled rect + white text, no border)
  function badge(text: string, x: number, by: number, color: string): number {
    const tw = pdf.getStringUnitWidth(text) * 6.5 / pdf.internal.scaleFactor + 5;
    sf(pdf, color); pdf.rect(x, by - 3.5, tw, 5, 'F');
    pdf.setFontSize(6); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
    pdf.text(text.toUpperCase(), x + 2.5, by);
    return tw + 2;
  }

  // Outline tag
  function tag(text: string, x: number, by: number, color: string): number {
    const tw = pdf.getStringUnitWidth(text) * 6.5 / pdf.internal.scaleFactor + 4;
    sd(pdf, color); pdf.setLineWidth(0.3); pdf.rect(x, by - 3.5, tw, 5, 'S');
    pdf.setFontSize(6); pdf.setFont('helvetica', 'bold'); st(pdf, color);
    pdf.text(text.toUpperCase(), x + 2, by);
    return tw + 2;
  }

  // Thin confirmation bar under a risk title
  function confBar(x: number, by: number, width: number, pct: number, color: string) {
    sf(pdf, PANEL2); pdf.rect(x, by, width, 1.8, 'F');
    sf(pdf, color);  pdf.rect(x, by, width * Math.min(Math.max(pct, 0), 1), 1.8, 'F');
  }

  // Wrapped body text, advances y
  function bodyText(text: string, color = BODY, maxW = CW, indent = 0, size = 8) {
    pdf.setFontSize(size); pdf.setFont('helvetica', 'normal'); st(pdf, color);
    const lines = pdf.splitTextToSize(text, maxW - indent);
    for (const line of lines) {
      chk(5);
      pdf.text(line, MARGIN + indent, y);
      y += 4.2;
    }
  }

  // ── Page 1 — Cover / Executive Brief ─────────────────────────────────────────
  whitePage();
  pageNum = 1;

  // Navy header bar
  sf(pdf, ACCENT);
  pdf.rect(0, 0, W, 38, 'F');

  // Civica wordmark
  pdf.setFontSize(22); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
  pdf.text('CIVICA', MARGIN, 16);
  pdf.setFontSize(7.5); pdf.setFont('helvetica', 'normal'); st(pdf, '#a8c8e8');
  pdf.text('CANADIAN POLICY SIMULATION ENGINE', MARGIN, 23);

  // Seal / date top-right
  const now = new Date().toISOString().split('T')[0];
  pdf.setFontSize(7); st(pdf, WHITE);
  if (data.seal_id) {
    pdf.text(`SEAL ${data.seal_id}`, W - MARGIN, 13, { align: 'right' });
  }
  pdf.text(`Generated ${now}`, W - MARGIN, 19, { align: 'right' });
  pdf.text(`${data.specialists_total} specialists · ${data.validators_total} validators`, W - MARGIN, 25, { align: 'right' });

  // Overall risk badge — large, top-right
  const orColor = sevColor(data.risk_report.overall_risk_level);
  sf(pdf, orColor); pdf.rect(W - MARGIN - 36, 28, 36, 9, 'F');
  pdf.setFontSize(8); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
  pdf.text(`OVERALL RISK: ${data.risk_report.overall_risk_level}`, W - MARGIN - 34, 34);

  y = 46;

  // Policy directive block
  sf(pdf, PANEL); pdf.rect(MARGIN, y, CW, 2, 'F'); // top accent line
  sf(pdf, ACCENT); pdf.rect(MARGIN, y, 2, 22, 'F');
  sf(pdf, PANEL); pdf.rect(MARGIN + 2, y, CW - 2, 22, 'F');
  pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, ACCENT);
  pdf.text('POLICY DIRECTIVE', MARGIN + 6, y + 5);
  const policyLines = pdf.splitTextToSize(data.policy, CW - 10) as string[];
  pdf.setFontSize(8.5); pdf.setFont('helvetica', 'normal'); st(pdf, INK);
  policyLines.slice(0, 3).forEach((l, i) => pdf.text(l, MARGIN + 6, y + 11 + i * 4.5));
  y += 26;

  // Classification chips row
  if (data.policy_classification) {
    const pc = data.policy_classification;
    const chips = [
      { label: pc.type, color: ACCENT },
      { label: pc.geography?.replace(/_/g, ' '), color: MUTED },
      { label: pc.time_horizon?.replace(/_/g, ' '), color: AMBER },
      { label: pc.primary_affected?.replace(/_/g, ' '), color: GREEN },
    ].filter(c => c.label);
    let cx = MARGIN;
    chips.forEach(({ label, color }) => {
      cx += tag(label!, cx, y + 3, color);
    });
    y += 9;
  }

  y += 3; hRule(RULE, 0.4);

  // Two-column executive section: KEY INSIGHT left, NET IMPACT right
  const colMid = MARGIN + CW * 0.62;
  const leftW  = CW * 0.62 - 6;
  const rightW = CW * 0.36;

  // Left: Key Insight
  pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, ACCENT);
  pdf.text('KEY FINDING', MARGIN, y + 4);
  const kiLines = pdf.splitTextToSize(data.risk_report.key_insight, leftW) as string[];
  pdf.setFontSize(9); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
  const kiStartY = y + 8;
  kiLines.slice(0, 4).forEach((l, i) => pdf.text(l, MARGIN, kiStartY + i * 5));
  const kiH = Math.min(4, kiLines.length) * 5 + 8;

  // Right: Net impact summary
  if (data.benefits) {
    const { net_positive_validators: pos, net_negative_validators: neg, net_neutral_validators: neu } = data.benefits.summary;
    const total = pos + neg + neu || 1;
    pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, ACCENT);
    pdf.text('NET IMPACT ON VALIDATORS', colMid + 2, y + 4);

    const barRows = [
      { label: 'Net gain',    count: pos, color: GREEN },
      { label: 'Neutral',     count: neu, color: SUBTLE },
      { label: 'Net loss',    count: neg, color: RED   },
    ];
    let ry = y + 9;
    barRows.forEach(({ label, count, color }) => {
      const pct = count / total;
      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
      pdf.text(label, colMid + 2, ry);
      sf(pdf, PANEL2); pdf.rect(colMid + 24, ry - 2.5, rightW - 26, 3.5, 'F');
      sf(pdf, color);  pdf.rect(colMid + 24, ry - 2.5, (rightW - 26) * pct, 3.5, 'F');
      pdf.setFontSize(6); st(pdf, color); pdf.setFont('helvetica', 'bold');
      pdf.text(`${count}`, colMid + 24 + (rightW - 26) * pct + 2, ry);
      ry += 5.5;
    });
  }

  y += Math.max(kiH, 24) + 4;
  hRule();

  // Risk summary table (all risks in a single compact table)
  sectionLabel('RISK REGISTER — SUMMARY', ACCENT);
  y += 1;

  // Table header
  sf(pdf, ACCENT); pdf.rect(MARGIN, y, CW, 6, 'F');
  const cols = { rank: 8, title: 60, sev: 18, conf: 22, timeline: 26, groups: CW - 8 - 60 - 18 - 22 - 26 };
  let cx2 = MARGIN + 2;
  pdf.setFontSize(6); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
  pdf.text('#',           cx2, y + 4); cx2 += cols.rank;
  pdf.text('RISK TITLE',  cx2, y + 4); cx2 += cols.title;
  pdf.text('SEVERITY',    cx2, y + 4); cx2 += cols.sev;
  pdf.text('CONFIRMED',   cx2, y + 4); cx2 += cols.conf;
  pdf.text('TIMELINE',    cx2, y + 4); cx2 += cols.timeline;
  pdf.text('AFFECTED',    cx2, y + 4);
  y += 6;

  data.risk_report.risks.forEach((risk: RiskReportItem, i: number) => {
    const rowColor = i % 2 === 0 ? WHITE : PANEL;
    const rColor = sevColor(risk.severity);
    const confPct = risk.confirmed_by / (risk.out_of || 50);
    const confColor = confPct >= 0.5 ? RED : confPct >= 0.25 ? AMBER : SUBTLE;

    // Estimate row height from title wrap
    const titleWrap = pdf.splitTextToSize(risk.title, cols.title - 2) as string[];
    const rowH = Math.max(7, titleWrap.length * 4 + 3);
    chk(rowH);

    sf(pdf, rowColor); pdf.rect(MARGIN, y, CW, rowH, 'F');
    sd(pdf, RULE); pdf.setLineWidth(0.1); pdf.rect(MARGIN, y, CW, rowH, 'S');
    // Severity stripe on left
    sf(pdf, rColor); pdf.rect(MARGIN, y, 1.5, rowH, 'F');

    let rx = MARGIN + 3;
    // Rank
    pdf.setFontSize(7.5); pdf.setFont('helvetica', 'bold'); st(pdf, rColor);
    pdf.text(`${i + 1}`, rx + 1, y + rowH / 2 + 1.5); rx += cols.rank;
    // Title (may wrap)
    pdf.setFontSize(7); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
    titleWrap.forEach((l, li) => pdf.text(l, rx, y + 4 + li * 4));
    rx += cols.title;
    // Severity badge
    badge(sevLabel(risk.severity), rx, y + rowH / 2, rColor); rx += cols.sev;
    // Confirmed
    pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, confColor);
    pdf.text(`${risk.confirmed_by}/${risk.out_of}`, rx, y + rowH / 2 + 1.5);
    confBar(rx, y + rowH / 2 + 2.5, cols.conf - 4, confPct, confColor);
    rx += cols.conf;
    // Timeline
    const tlLabel = (risk.timeline || '').replace(/_/g, ' ');
    pdf.setFontSize(6); pdf.setFont('helvetica', 'normal'); st(pdf, MUTED);
    pdf.text(tlLabel, rx, y + rowH / 2 + 1.5); rx += cols.timeline;
    // Affected groups (truncate)
    if (risk.affected_groups) {
      const agWrap = pdf.splitTextToSize(risk.affected_groups, cols.groups - 2) as string[];
      pdf.setFontSize(6); st(pdf, SUBTLE);
      agWrap.slice(0, 2).forEach((l, li) => pdf.text(l, rx, y + 4 + li * 3.5));
    }
    y += rowH;
  });

  y += 4;

  // Confidence strip at bottom of cover
  if (data.confidence) {
    hRule();
    const c = data.confidence;
    const confPct = c.score / c.out_of;
    const cColor = confPct >= 0.7 ? GREEN : confPct >= 0.4 ? AMBER : RED;
    pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, ACCENT);
    pdf.text('CONFIDENCE', MARGIN, y + 4);
    pdf.setFontSize(11); pdf.setFont('helvetica', 'bold'); st(pdf, cColor);
    pdf.text(`${c.score}/${c.out_of}`, MARGIN + 24, y + 4);
    confBar(MARGIN + 44, y + 1.5, CW / 2 - 44, confPct, cColor);
    pdf.setFontSize(7); pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
    pdf.text(c.summary, MARGIN + 44, y + 7);
    y += 12;
  }

  // ── Page 2+ — Risk Register (full detail) ────────────────────────────────────
  newPage();
  // Section title bar
  sf(pdf, ACCENT); pdf.rect(MARGIN, y - 6, CW, 10, 'F');
  pdf.setFontSize(10); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
  pdf.text('RISK REGISTER', MARGIN + 4, y);
  pdf.setFontSize(7); pdf.setFont('helvetica', 'normal'); st(pdf, '#a8c8e8');
  pdf.text('Full analysis — ranked by severity and validator confirmation', MARGIN + 50, y);
  y += 8;

  data.risk_report.risks.forEach((risk: RiskReportItem, i: number) => {
    const rColor = sevColor(risk.severity);
    const cascade = typeof risk.cascade_effect === 'object' && risk.cascade_effect !== null
      ? risk.cascade_effect : null;
    const confPct = risk.confirmed_by / (risk.out_of || 50);

    // Pre-compute all line counts for block height
    const reasoningLines = pdf.splitTextToSize(risk.reasoning ?? '', CW - 6) as string[];
    const hasTimeline = !!(risk.timeline_detail);
    const timelineLines = hasTimeline ? pdf.splitTextToSize(risk.timeline_detail, CW - 30) as string[] : [];
    const hasCascade = !!(cascade?.mechanism);
    const cascadeLines = hasCascade ? pdf.splitTextToSize(cascade!.mechanism!, CW - 20) as string[] : [];
    const hasEvidence = hasCascade && !!(cascade?.evidence);
    const evidenceLines = hasEvidence ? pdf.splitTextToSize(`Evidence: ${cascade!.evidence}`, CW - 20) as string[] : [];

    const headerH  = 22;
    const reasonH  = reasoningLines.length * 4;
    const tlH      = hasTimeline  ? 3 + timelineLines.length * 3.8  : 0;
    const cascadeH = hasCascade   ? 4 + cascadeLines.length * 3.8   : 0;
    const evidH    = hasEvidence  ? evidenceLines.length * 3.5       : 0;
    const blockH   = headerH + reasonH + tlH + cascadeH + evidH + 8;

    chk(blockH + 4);

    const bTop = y;

    // Background
    sf(pdf, WHITE); pdf.rect(MARGIN, bTop, CW, blockH, 'F');
    sd(pdf, RULE); pdf.setLineWidth(0.3); pdf.rect(MARGIN, bTop, CW, blockH, 'S');

    // Left severity stripe (full height)
    sf(pdf, rColor); pdf.rect(MARGIN, bTop, 3, blockH, 'F');

    // Header area background tint
    sf(pdf, PANEL); pdf.rect(MARGIN + 3, bTop, CW - 3, headerH, 'F');

    // Rank number (large, in stripe)
    pdf.setFontSize(16); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
    pdf.text(`${i + 1}`, MARGIN + 0.3, bTop + 11);

    // Title
    const titleLines = pdf.splitTextToSize(risk.title, CW - 60) as string[];
    pdf.setFontSize(9.5); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
    titleLines.slice(0, 2).forEach((l, li) => pdf.text(l, MARGIN + 7, bTop + 6 + li * 5));

    // Severity badge + timeline tag top-right
    let tagX = W - MARGIN - 2;
    tagX -= badge(sevLabel(risk.severity), tagX - 16, bTop + 5, rColor) + 1;
    if (risk.timeline) {
      tagX -= tag((risk.timeline).replace(/_/g, ' '), tagX - 22, bTop + 5, MUTED) + 1;
    }

    // Confirmation bar + label
    confBar(MARGIN + 7, bTop + 14, CW - 70, confPct, rColor);
    pdf.setFontSize(6.5); pdf.setFont('helvetica', 'normal');
    const confColor2 = confPct >= 0.5 ? RED : confPct >= 0.25 ? AMBER : SUBTLE;
    st(pdf, confColor2);
    pdf.text(`${risk.confirmed_by} / ${risk.out_of} validators confirmed (${Math.round(confPct * 100)}%)`,
      MARGIN + 7, bTop + 19);

    // Affected groups right of conf bar
    if (risk.affected_groups) {
      pdf.setFontSize(6); st(pdf, SUBTLE);
      const agW = pdf.splitTextToSize(`Affects: ${risk.affected_groups}`, 60) as string[];
      agW.slice(0, 2).forEach((l, li) => pdf.text(l, W - MARGIN - 62, bTop + 13 + li * 3.5));
    }

    // Cities
    if (risk.cities?.length) {
      let cx3 = MARGIN + 7;
      pdf.setFontSize(5.5); pdf.setFont('helvetica', 'normal'); st(pdf, SUBTLE);
      risk.cities.slice(0, 6).forEach(city => {
        pdf.text(city, cx3, bTop + headerH - 2);
        cx3 += pdf.getStringUnitWidth(city) * 5.5 / pdf.internal.scaleFactor + 5;
      });
    }

    // Body content
    let ry = bTop + headerH + 4;
    pdf.setFontSize(7.5); pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
    reasoningLines.forEach(l => { pdf.text(l, MARGIN + 6, ry); ry += 4; });

    if (hasTimeline) {
      ry += 2;
      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, AMBER);
      pdf.text('TIMELINE', MARGIN + 6, ry); ry += 3.8;
      pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
      timelineLines.forEach(l => { pdf.text(l, MARGIN + 6, ry); ry += 3.8; });
    }

    if (hasCascade) {
      ry += 2;
      const cColor = cascade!.likelihood === 'HIGH' ? RED : cascade!.likelihood === 'MEDIUM' ? AMBER : SUBTLE;
      // Cascade bar
      sf(pdf, PANEL2); pdf.rect(MARGIN + 6, ry - 2, CW - 12, 0.5, 'F');
      ry += 1;
      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, cColor);
      pdf.text(`CASCADE EFFECT  [${cascade!.likelihood ?? '—'}]`, MARGIN + 6, ry); ry += 3.8;
      pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
      cascadeLines.forEach(l => { pdf.text(l, MARGIN + 6, ry); ry += 3.8; });
      if (hasEvidence) {
        ry += 1;
        pdf.setFontSize(6); st(pdf, SUBTLE);
        evidenceLines.forEach(l => { pdf.text(l, MARGIN + 6, ry); ry += 3.5; });
      }
    }

    y = bTop + blockH + 5;
  });

  // ── Benefits page ────────────────────────────────────────────────────────────
  if (data.benefits && data.benefits.benefit_items.length > 0) {
    newPage();
    const { summary, top_benefits, net_by_tenure, net_by_income, net_by_age } = data.benefits;

    sf(pdf, GREEN); pdf.rect(MARGIN, y - 6, CW, 10, 'F');
    pdf.setFontSize(10); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
    pdf.text('BENEFITS ANALYSIS', MARGIN + 4, y);
    y += 10;

    // Summary stats row
    const pos = summary.net_positive_validators;
    const neg = summary.net_negative_validators;
    const neu = summary.net_neutral_validators;
    const tot = pos + neg + neu || 1;

    const bStats = [
      { k: 'Net Positive', v: `${pos}`, sub: `${Math.round(pos/tot*100)}% of validators`, c: GREEN },
      { k: 'Neutral',      v: `${neu}`, sub: `${Math.round(neu/tot*100)}% of validators`, c: SUBTLE },
      { k: 'Net Negative', v: `${neg}`, sub: `${Math.round(neg/tot*100)}% of validators`, c: RED   },
      { k: 'Benefit Items', v: `${summary.total_benefit_items}`, sub: 'identified by specialists', c: ACCENT },
    ];
    const bColW = CW / bStats.length;
    chk(22);
    bStats.forEach(({ k, v, sub, c }, i) => {
      const sx = MARGIN + i * bColW;
      sf(pdf, PANEL); pdf.rect(sx, y, bColW - 2, 18, 'F');
      pdf.setFontSize(18); pdf.setFont('helvetica', 'bold'); st(pdf, c);
      pdf.text(v, sx + 4, y + 12);
      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, BODY);
      pdf.text(k.toUpperCase(), sx + 4, y + 16);
      pdf.setFontSize(5.5); pdf.setFont('helvetica', 'normal'); st(pdf, SUBTLE);
      pdf.text(sub, sx + 4, y + 19.5);
    });
    y += 23;

    // Net impact breakdown — three columns as a proper table
    const breakdowns = [
      { label: 'By Tenure', data: net_by_tenure },
      { label: 'By Income', data: net_by_income },
      { label: 'By Age',    data: net_by_age    },
    ].filter(b => b.data && Object.keys(b.data).length > 0);

    if (breakdowns.length > 0) {
      hRule(RULE, 0.3);
      sectionLabel('NET IMPACT BY DEMOGRAPHIC GROUP', ACCENT);

      const bdColW = CW / breakdowns.length;
      const maxRows = Math.max(...breakdowns.map(b => Object.keys(b.data).length));
      chk(maxRows * 7 + 12);

      breakdowns.forEach(({ label, data: bd }, bdi) => {
        const bx = MARGIN + bdi * bdColW;
        // Column header
        sf(pdf, PANEL2); pdf.rect(bx, y, bdColW - 2, 6, 'F');
        pdf.setFontSize(7); pdf.setFont('helvetica', 'bold'); st(pdf, ACCENT);
        pdf.text(label.toUpperCase(), bx + 3, y + 4.5);

        let ry2 = y + 7;
        Object.entries(bd).forEach(([group, g]) => {
          const groupLabel = group.replace(/_/g, ' ');
          pdf.setFontSize(7); pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
          pdf.text(groupLabel, bx + 3, ry2);

          if (g.count < 5) {
            pdf.setFontSize(6); st(pdf, SUBTLE); pdf.setFont('helvetica', 'italic');
            pdf.text('n<5 — suppressed', bx + bdColW - 32, ry2);
          } else {
            const netColor = g.avg_net > 0.3 ? GREEN : g.avg_net < -0.3 ? RED : SUBTLE;
            pdf.setFontSize(7.5); pdf.setFont('helvetica', 'bold'); st(pdf, netColor);
            const val = `${g.avg_net > 0 ? '+' : ''}${g.avg_net.toFixed(2)}`;
            pdf.text(val, bx + bdColW - 18, ry2);
            // Mini bar
            const barW = 20;
            const barX = bx + bdColW - 40;
            sf(pdf, PANEL2); pdf.rect(barX, ry2 - 2.5, barW, 2, 'F');
            const fillPct = Math.min(Math.abs(g.avg_net) / 2, 1);
            sf(pdf, netColor); pdf.rect(barX, ry2 - 2.5, barW * fillPct, 2, 'F');
          }
          ry2 += 6;
        });
        if (bdi < breakdowns.length - 1) {
          vRule(bx + bdColW, y, y + maxRows * 6 + 7, RULE);
        }
      });
      y += maxRows * 6 + 10;
      hRule(RULE, 0.3);
    }

    // Benefit items — two-column layout
    sectionLabel('BENEFIT ITEMS', GREEN);

    const halfIdx = Math.ceil(top_benefits.length / 2);
    const leftBenefits  = top_benefits.slice(0, halfIdx);
    const rightBenefits = top_benefits.slice(halfIdx);
    const bItemColW = CW / 2 - 3;
    const bItemColR = MARGIN + bItemColW + 6;

    function renderBenefitItem(b: BenefitItem, x: number, colW: number, idx: number) {
      const bLines  = pdf.splitTextToSize(b.benefit, colW - 20) as string[];
      const mLines  = pdf.splitTextToSize(b.mechanism, colW - 4) as string[] ;
      const bH = bLines.length * 4 + mLines.length * 3.5 + (b.primary_beneficiaries ? 4 : 0) + (b.caveat ? 4 : 0) + 6;
      chk(bH + 2);

      sf(pdf, PANEL); pdf.rect(x, y, colW, bH, 'F');
      sd(pdf, RULE); pdf.setLineWidth(0.2); pdf.rect(x, y, colW, bH, 'S');
      sf(pdf, GREEN); pdf.rect(x, y, 2, bH, 'F');

      // Benefit number
      pdf.setFontSize(8); pdf.setFont('helvetica', 'bold'); st(pdf, GREEN);
      pdf.text(`${idx + 1}`, x + 4, y + 5);

      // Magnitude badge top-right
      const magLabel = b.magnitude === 3 ? 'HIGH' : b.magnitude === 2 ? 'MED' : 'LOW';
      badge(magLabel, x + colW - 13, y + 4, b.magnitude === 3 ? GREEN : b.magnitude === 2 ? AMBER : SUBTLE);

      // Title
      pdf.setFontSize(7.5); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
      bLines.forEach((l, li) => pdf.text(l, x + 9, y + 5 + li * 4));
      let ry3 = y + 5 + bLines.length * 4 + 1;

      // Mechanism
      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
      mLines.forEach(l => { pdf.text(l, x + 4, ry3); ry3 += 3.5; });

      if (b.primary_beneficiaries) {
        pdf.setFontSize(6); st(pdf, GREEN);
        pdf.text(`↳ ${b.primary_beneficiaries}`, x + 4, ry3); ry3 += 3.5;
      }
      if (b.caveat) {
        pdf.setFontSize(6); pdf.setFont('helvetica', 'italic'); st(pdf, AMBER);
        const cvL = pdf.splitTextToSize(`⚠ ${b.caveat}`, colW - 8) as string[];
        cvL.slice(0, 1).forEach(l => { pdf.text(l, x + 4, ry3); ry3 += 3.5; });
      }
      y += bH + 3;
    }

    // Render left and right columns interleaved (each item advances y together)
    const maxItems = Math.max(leftBenefits.length, rightBenefits.length);
    // Since we can't do true two-column with advancing y, render as a numbered list instead
    top_benefits.forEach((b, idx) => {
      renderBenefitItem(b, MARGIN, CW, idx);
    });
  }

  // ── Specialist panel findings ────────────────────────────────────────────────
  if (data.round_1_specialists?.length) {
    newPage();
    sf(pdf, '#4a235a'); pdf.rect(MARGIN, y - 6, CW, 10, 'F');
    pdf.setFontSize(10); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
    pdf.text('SPECIALIST PANEL FINDINGS', MARGIN + 4, y);
    pdf.setFontSize(7); pdf.setFont('helvetica', 'normal'); st(pdf, '#d2b4de');
    pdf.text(`${data.round_1_specialists.length} domain specialists · click specialist name to see full findings in web report`, MARGIN + 60, y);
    y += 10;

    data.round_1_specialists.forEach(s => {
      const topRisks = (s.risks ?? []).slice(0, 3);
      if (!topRisks.length) return;

      const specName = s.specialist.replace(/_/g, ' ').toUpperCase();
      chk(10);

      // Specialist header
      sf(pdf, PANEL); pdf.rect(MARGIN, y, CW, 7, 'F');
      pdf.setFontSize(7.5); pdf.setFont('helvetica', 'bold'); st(pdf, '#4a235a');
      pdf.text(specName, MARGIN + 4, y + 5);
      pdf.setFontSize(6); pdf.setFont('helvetica', 'normal'); st(pdf, SUBTLE);
      pdf.text(`${topRisks.length} risks identified`, W - MARGIN - 30, y + 5);
      y += 7;

      topRisks.forEach((risk, ri) => {
        const sColor = risk.severity >= 3 ? RED : risk.severity === 1 ? GREEN : AMBER;
        const rLines  = pdf.splitTextToSize(risk.risk ?? '', CW - 50) as string[];
        const hpLines = risk.historical_precedent
          ? pdf.splitTextToSize(`${risk.historical_precedent}`, CW - 50) as string[]
          : [];
        const rowH = rLines.length * 4 + (hpLines.length > 0 ? hpLines.length * 3.5 + 2 : 0) + 6;
        chk(rowH);

        sf(pdf, ri % 2 === 0 ? WHITE : PANEL);
        pdf.rect(MARGIN, y, CW, rowH, 'F');
        sd(pdf, RULE); pdf.setLineWidth(0.1); pdf.rect(MARGIN, y, CW, rowH, 'S');
        sf(pdf, sColor); pdf.rect(MARGIN, y, 2, rowH, 'F');

        badge(sevLabel(risk.severity), MARGIN + 4, y + 5, sColor);

        pdf.setFontSize(7.5); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
        let ry4 = y + 4;
        rLines.forEach(l => { pdf.text(l, MARGIN + 22, ry4); ry4 += 4; });

        if (risk.most_exposed) {
          pdf.setFontSize(6); pdf.setFont('helvetica', 'normal'); st(pdf, SUBTLE);
          pdf.text(`Exposed: ${risk.most_exposed}`, W - MARGIN - 70, y + 5);
        }

        if (hpLines.length > 0) {
          ry4 += 1;
          pdf.setFontSize(6); pdf.setFont('helvetica', 'italic'); st(pdf, BLUE);
          hpLines.forEach(l => { pdf.text(l, MARGIN + 22, ry4); ry4 += 3.5; });
        }
        y += rowH;
      });
      y += 3;
    });
  }

  // ── Demographic panel page ────────────────────────────────────────────────────
  if (data.round_2_validators?.length) {
    newPage();
    sf(pdf, INK); pdf.rect(MARGIN, y - 6, CW, 10, 'F');
    pdf.setFontSize(10); pdf.setFont('helvetica', 'bold'); st(pdf, WHITE);
    pdf.text('DEMOGRAPHIC VALIDATOR PANEL', MARGIN + 4, y);
    y += 10;

    // Validator grid — 3 columns
    const vColW = CW / 3 - 2;
    const sorted = [...data.round_2_validators]
      .sort((a, b) =>
        b.validations.filter(v => v.applies).length - a.validations.filter(v => v.applies).length
      )
      .slice(0, 30);

    let col = 0;
    let rowStartY = y;
    let colHeights = [y, y, y];

    sorted.forEach((v: ValidatorResult) => {
      const confirmed = v.validations.filter(val => val.applies).length;
      const total = v.validations.length;
      const confPct = total > 0 ? confirmed / total : 0;
      const vColor = confPct > 0.6 ? RED : confPct > 0.3 ? AMBER : GREEN;

      const stance = v.behavioral_profile?.policy_stance ?? '';
      const stanceLabel: Record<string, string> = {
        supportive: 'SUPPORT', opposed: 'OPPOSE',
        indifferent: 'INDIFF', skeptical_of_benefit: 'SKEPT',
      };
      const sLabel = stanceLabel[stance] ?? '—';
      const sColor = stance === 'supportive' ? GREEN : stance === 'opposed' ? RED : SUBTLE;

      const cardH = v.missed_risk ? 18 : 14;
      const colX = MARGIN + col * (vColW + 3);

      if (colHeights[col] + cardH > PH - 20) {
        col = (col + 1) % 3;
        if (col === 0) {
          y = Math.max(...colHeights) + 3;
          colHeights = [y, y, y];
        }
      }

      const cy = colHeights[col];
      sf(pdf, PANEL); pdf.rect(colX, cy, vColW, cardH, 'F');
      sd(pdf, RULE); pdf.setLineWidth(0.1); pdf.rect(colX, cy, vColW, cardH, 'S');
      sf(pdf, vColor); pdf.rect(colX, cy, 1.5, cardH, 'F');

      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
      pdf.text(`#${String(v.agent_id).padStart(2,'0')} ${v.city}`, colX + 3, cy + 4.5);
      pdf.setFontSize(5.5); pdf.setFont('helvetica', 'normal'); st(pdf, SUBTLE);
      pdf.text(`${v.tenure} · ${v.age_bracket} · ${v.income_bracket}`, colX + 3, cy + 8);

      confBar(colX + 3, cy + 10, vColW * 0.45, confPct, vColor);
      pdf.setFontSize(5.5); pdf.setFont('helvetica', 'bold'); st(pdf, vColor);
      pdf.text(`${confirmed}/${total}`, colX + 3 + vColW * 0.45 + 2, cy + 11.5);

      badge(sLabel, colX + vColW - 16, cy + 4.5, sColor);

      if (v.missed_risk) {
        pdf.setFontSize(5.5); pdf.setFont('helvetica', 'italic'); st(pdf, AMBER);
        const mrL = pdf.splitTextToSize(`+ ${v.missed_risk.risk}`, vColW - 6) as string[];
        pdf.text(mrL[0], colX + 3, cy + 16);
      }

      colHeights[col] += cardH + 2;
      col = (col + 1) % 3;
    });

    y = Math.max(...colHeights) + 5;

    // Demographic tensions
    if (data.demographic_tensions && data.demographic_tensions.length > 0) {
      chk(20);
      hRule();
      sectionLabel('DEMOGRAPHIC FAULT LINES', AMBER);

      data.demographic_tensions.forEach(t => {
        const gapColor = t.gap > 0.3 ? RED : t.gap > 0.15 ? AMBER : GREEN;
        const rowH = 14;
        chk(rowH + 2);

        sf(pdf, PANEL); pdf.rect(MARGIN, y, CW, rowH, 'F');
        sd(pdf, RULE); pdf.setLineWidth(0.15); pdf.rect(MARGIN, y, CW, rowH, 'S');

        pdf.setFontSize(7.5); pdf.setFont('helvetica', 'bold'); st(pdf, INK);
        pdf.text(t.risk_title, MARGIN + 4, y + 5);
        tag(t.dimension, W - MARGIN - 30, y + 4, AMBER);

        const barW = (CW / 2) - 20;
        sf(pdf, PANEL2); pdf.rect(MARGIN + 4, y + 7, barW, 2.5, 'F');
        sf(pdf, SUBTLE);  pdf.rect(MARGIN + 4, y + 7, barW * t.rate_a, 2.5, 'F');
        sf(pdf, PANEL2); pdf.rect(MARGIN + 4 + barW + 4, y + 7, barW, 2.5, 'F');
        sf(pdf, gapColor); pdf.rect(MARGIN + 4 + barW + 4, y + 7, barW * t.rate_b, 2.5, 'F');

        pdf.setFontSize(6); pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
        pdf.text(`${t.group_a}: ${Math.round(t.rate_a * 100)}%`, MARGIN + 4, y + 13);
        pdf.text(`${t.group_b}: ${Math.round(t.rate_b * 100)}%`, MARGIN + 4 + barW + 4, y + 13);
        pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, gapColor);
        pdf.text(`Δ ${Math.round(t.gap * 100)}%`, W - MARGIN - 20, y + 13);

        y += rowH + 2;
      });
    }
  }

  // ── Appendix — Methodology & Confidence ──────────────────────────────────────
  newPage();
  sf(pdf, PANEL); pdf.rect(MARGIN, y - 6, CW, 10, 'F');
  pdf.setFontSize(10); pdf.setFont('helvetica', 'bold'); st(pdf, ACCENT);
  pdf.text('APPENDIX — METHODOLOGY & CONFIDENCE', MARGIN + 4, y);
  y += 12;

  // Model metadata
  sectionLabel('SIMULATION METADATA', ACCENT);
  const meta = [
    { k: 'Specialist model',  v: data.models?.specialist ?? '—'  },
    { k: 'Validator model',   v: data.models?.validator  ?? '—'  },
    { k: 'Coordinator model', v: data.models?.coordinator ?? '—' },
    { k: 'Runtime',           v: `${Math.round(data.total_time_seconds)}s` },
    { k: 'Panel scope',       v: data.panel_scope ?? 'Standard'  },
    ...(data.risk_stability ? [{
      k: 'Risk stability',
      v: `${data.risk_stability.score}/${data.risk_stability.out_of} — ${data.risk_stability.label}`,
    }] : []),
  ];
  meta.forEach(({ k, v }) => {
    chk(7);
    const colX2 = MARGIN + 52;
    pdf.setFontSize(7); pdf.setFont('helvetica', 'bold'); st(pdf, MUTED);
    pdf.text(k.toUpperCase(), MARGIN, y);
    pdf.setFont('helvetica', 'normal'); st(pdf, INK);
    pdf.text(v, colX2, y);
    y += 5.5;
  });

  y += 3; hRule();

  // Confidence checks
  if (data.confidence) {
    const c = data.confidence;
    sectionLabel('CONFIDENCE CHECKS', ACCENT);

    const checks = c.checks ?? [];
    checks.forEach(ck => {
      const ckColor = ck.status === 'pass' ? GREEN : ck.status === 'warn' ? AMBER : ck.status === 'fail' ? RED : SUBTLE;
      const ckLines = pdf.splitTextToSize(ck.label, CW - 20) as string[];
      const ckH = ckLines.length * 4 + 2;
      chk(ckH);

      const statusStr = `[${ck.status.toUpperCase()}]`;
      pdf.setFontSize(6.5); pdf.setFont('helvetica', 'bold'); st(pdf, ckColor);
      pdf.text(statusStr, MARGIN, y);
      pdf.setFont('helvetica', 'normal'); st(pdf, BODY);
      ckLines.forEach((l, li) => pdf.text(l, MARGIN + 18, y + li * 4));
      y += ckH;
    });

    if (c.caveat) {
      y += 2;
      bodyText(c.caveat, SUBTLE, CW, 0, 7);
    }
    y += 3; hRule();
  }

  // Blind spots
  sectionLabel('LIMITATIONS & BLIND SPOTS', RED);
  if (typeof data.risk_report.blind_spots === 'object') {
    const bs = data.risk_report.blind_spots;
    const bsFields = [
      { k: 'Underrepresented groups', v: bs.underrepresented_groups },
      { k: 'Unmodeled effects',       v: bs.unmodeled_effects       },
      { k: 'Data gaps',               v: bs.data_gaps               },
      { k: 'Coverage note',           v: bs.coverage_note           },
      ...(bs.panel_skew_warning ? [{ k: 'Panel skew', v: bs.panel_skew_warning }] : []),
    ];
    bsFields.forEach(({ k, v }) => {
      if (!v) return;
      chk(12);
      pdf.setFontSize(7); pdf.setFont('helvetica', 'bold'); st(pdf, MUTED);
      pdf.text(k.toUpperCase(), MARGIN, y); y += 4;
      bodyText(v, BODY, CW, 4, 7.5);
      y += 2;
    });
  } else {
    bodyText(String(data.risk_report.blind_spots), BODY, CW, 0, 7.5);
  }

  // ── Footer on all pages ───────────────────────────────────────────────────────
  const totalPages = (pdf as unknown as { internal: { pages: unknown[] } }).internal.pages.length - 1;
  const footerDate = new Date().toISOString().split('T')[0];
  for (let p = 1; p <= totalPages; p++) {
    pdf.setPage(p);
    sd(pdf, RULE); pdf.setLineWidth(0.3); pdf.line(MARGIN, PH - 10, W - MARGIN, PH - 10);
    sf(pdf, WHITE); pdf.rect(0, PH - 10, W, 10, 'F');
    pdf.setFontSize(6); pdf.setFont('helvetica', 'normal'); st(pdf, SUBTLE);
    pdf.text(`CIVICA — Policy Simulation Engine`, MARGIN, PH - 5);
    if (data.seal_id) pdf.text(`Seal: ${data.seal_id}`, W / 2, PH - 5, { align: 'center' });
    pdf.text(`${p} / ${totalPages}`, W - MARGIN, PH - 5, { align: 'right' });
    pdf.text(footerDate, W - MARGIN - 22, PH - 5);
  }

  const filename = data.seal_id ? `civica-${data.seal_id}.pdf` : 'civica-report.pdf';
  pdf.save(filename);
}
