import { jsPDF } from 'jspdf';
import type { SimulationOutput } from '../types';

const DARK = '#080706';
const PANEL = '#111111';
const BORDER = '#2a2a2a';
const TEXT = '#ebe8e0';
const MUTED = '#a3a199';
const DIM = '#555555';
const GREEN = '#00ff41';
const RED = '#ff2a00';
const AMBER = '#ffaa00';
const BLUE = '#4a9eff';

function hexToRgb(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b];
}

function setFill(pdf: jsPDF, hex: string) {
  pdf.setFillColor(...hexToRgb(hex));
}

function setDraw(pdf: jsPDF, hex: string) {
  pdf.setDrawColor(...hexToRgb(hex));
}

function setTextColor(pdf: jsPDF, hex: string) {
  pdf.setTextColor(...hexToRgb(hex));
}

const W = 210; // A4 width mm
const MARGIN = 14;
const CONTENT_W = W - MARGIN * 2;

function severityColor(s: string): string {
  if (s === 'HIGH') return RED;
  if (s === 'LOW') return GREEN;
  return AMBER;
}

export async function exportReportPDF(data: SimulationOutput): Promise<void> {
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const H = pdf.internal.pageSize.getHeight();
  let y = 0;

  function newPage() {
    pdf.addPage();
    y = 0;
    // subtle grid lines on each page
    setDraw(pdf, '#111111');
    pdf.setLineWidth(0.1);
    for (let gx = 0; gx <= W; gx += 10) pdf.line(gx, 0, gx, H);
    for (let gy = 0; gy <= H; gy += 10) pdf.line(0, gy, W, gy);
    y = 10;
  }

  function checkPage(needed = 20) {
    if (y + needed > H - 10) newPage();
  }

  function rule(color = BORDER) {
    setDraw(pdf, color);
    pdf.setLineWidth(0.2);
    pdf.line(MARGIN, y, W - MARGIN, y);
    y += 4;
  }

  function label(text: string, color = DIM) {
    pdf.setFontSize(6.5);
    pdf.setFont('helvetica', 'normal');
    setTextColor(pdf, color);
    pdf.text(text.toUpperCase(), MARGIN, y);
    y += 4;
  }

  function body(text: string, color = MUTED, maxWidth = CONTENT_W) {
    pdf.setFontSize(8);
    pdf.setFont('helvetica', 'normal');
    setTextColor(pdf, color);
    const lines = pdf.splitTextToSize(text, maxWidth);
    for (const line of lines) {
      checkPage(5);
      pdf.text(line, MARGIN, y);
      y += 4.5;
    }
  }

  function tag(text: string, x: number, ty: number, color: string) {
    setDraw(pdf, color);
    pdf.setLineWidth(0.3);
    const tw = pdf.getStringUnitWidth(text) * 7 / pdf.internal.scaleFactor + 4;
    pdf.rect(x, ty - 3.5, tw, 5, 'S');
    pdf.setFontSize(6.5);
    pdf.setFont('helvetica', 'bold');
    setTextColor(pdf, color);
    pdf.text(text.toUpperCase(), x + 2, ty);
    return tw;
  }

  function bar(x: number, by: number, width: number, pct: number, color: string) {
    setFill(pdf, '#1a1a1a');
    pdf.rect(x, by, width, 2, 'F');
    setFill(pdf, color);
    pdf.rect(x, by, width * Math.min(pct, 1), 2, 'F');
  }

  // ── Page background ──────────────────────────────────────────────────────────
  setFill(pdf, DARK);
  pdf.rect(0, 0, W, H, 'F');

  // subtle grid on first page
  setDraw(pdf, '#111111');
  pdf.setLineWidth(0.1);
  for (let gx = 0; gx <= W; gx += 10) pdf.line(gx, 0, gx, H);
  for (let gy = 0; gy <= H; gy += 10) pdf.line(0, gy, W, gy);

  y = 16;

  // ── Header ───────────────────────────────────────────────────────────────────
  // Signal dot
  setFill(pdf, GREEN);
  pdf.circle(MARGIN + 2, y - 1, 1.5, 'F');

  pdf.setFontSize(18);
  pdf.setFont('helvetica', 'bold');
  setTextColor(pdf, TEXT);
  pdf.text('CIVICA', MARGIN + 6, y);

  pdf.setFontSize(7);
  pdf.setFont('helvetica', 'normal');
  setTextColor(pdf, DIM);
  pdf.text('POLICY SIMULATION ENGINE', MARGIN + 6, y + 4.5);

  // Overall risk badge top right
  const riskColor = severityColor(data.risk_report.overall_risk_level);
  const riskLabel = `OVERALL RISK: ${data.risk_report.overall_risk_level}`;
  const riskX = W - MARGIN - 40;
  tag(riskLabel, riskX, y, riskColor);

  y += 12;
  rule(BORDER);

  // ── Policy ───────────────────────────────────────────────────────────────────
  label('POLICY ANALYSED');
  body(data.policy, TEXT, CONTENT_W);
  y += 2;
  rule();

  // ── Stats row ────────────────────────────────────────────────────────────────
  const stats = [
    { k: 'Validators', v: String(data.validators_total) },
    { k: 'Specialists', v: String(data.specialists_total) },
    { k: 'Runtime', v: `${Math.round(data.total_time_seconds)}s` },
    { k: 'Seal ID', v: data.seal_id ?? 'N/A' },
  ];
  const colW = CONTENT_W / stats.length;
  stats.forEach(({ k, v }, i) => {
    const sx = MARGIN + i * colW;
    pdf.setFontSize(13);
    pdf.setFont('helvetica', 'bold');
    setTextColor(pdf, TEXT);
    pdf.text(v, sx, y + 5);
    pdf.setFontSize(6.5);
    pdf.setFont('helvetica', 'normal');
    setTextColor(pdf, DIM);
    pdf.text(k.toUpperCase(), sx, y + 9);
  });
  y += 16;
  rule();

  // ── Key Insight ──────────────────────────────────────────────────────────────
  label('KEY INSIGHT', BLUE);
  setFill(pdf, PANEL);
  const insightLines = pdf.splitTextToSize(data.risk_report.key_insight, CONTENT_W - 8);
  const insightH = insightLines.length * 4.5 + 8;
  pdf.rect(MARGIN, y, CONTENT_W, insightH, 'F');
  setDraw(pdf, BLUE);
  pdf.setLineWidth(0.5);
  pdf.line(MARGIN, y, MARGIN, y + insightH);
  pdf.setFontSize(8.5);
  pdf.setFont('helvetica', 'normal');
  setTextColor(pdf, TEXT);
  insightLines.forEach((line: string, i: number) => {
    pdf.text(line, MARGIN + 5, y + 5 + i * 4.5);
  });
  y += insightH + 6;

  // ── Risks ────────────────────────────────────────────────────────────────────
  checkPage(30);
  label('RISK REGISTER', DIM);
  y += 1;

  data.risk_report.risks.forEach((risk, i) => {
    const rColor = severityColor(risk.severity);
    const blockH = 32;
    checkPage(blockH + 4);

    setFill(pdf, PANEL);
    pdf.rect(MARGIN, y, CONTENT_W, blockH, 'F');
    setDraw(pdf, BORDER);
    pdf.setLineWidth(0.2);
    pdf.rect(MARGIN, y, CONTENT_W, blockH, 'S');

    // Left severity stripe
    setFill(pdf, rColor);
    pdf.rect(MARGIN, y, 1.5, blockH, 'F');

    // Rank
    pdf.setFontSize(18);
    pdf.setFont('helvetica', 'bold');
    setTextColor(pdf, '#1f1f1f');
    pdf.text(`${i + 1}`, MARGIN + 4, y + 12);

    // Title
    pdf.setFontSize(9);
    pdf.setFont('helvetica', 'bold');
    setTextColor(pdf, TEXT);
    const titleLines = pdf.splitTextToSize(risk.title, CONTENT_W - 50);
    titleLines.slice(0, 2).forEach((line: string, li: number) => {
      pdf.text(line, MARGIN + 14, y + 6 + li * 4.5);
    });

    // Severity tag
    tag(risk.severity, W - MARGIN - 22, y + 5, rColor);

    // Confirmation bar
    const confPct = risk.confirmed_by / (risk.out_of || 50);
    bar(MARGIN + 14, y + 14, CONTENT_W - 50, confPct, rColor);
    pdf.setFontSize(6.5);
    setTextColor(pdf, MUTED);
    pdf.text(`${risk.confirmed_by}/${risk.out_of} validators confirmed`, MARGIN + 14, y + 20);

    // Timeline
    tag(risk.timeline?.replace('_', ' ') ?? '', W - MARGIN - 30, y + 20, DIM);

    // Reasoning excerpt
    const reasoning = pdf.splitTextToSize(risk.reasoning, CONTENT_W - 16);
    pdf.setFontSize(7);
    pdf.setFont('helvetica', 'normal');
    setTextColor(pdf, MUTED);
    reasoning.slice(0, 2).forEach((line: string, li: number) => {
      pdf.text(line, MARGIN + 4, y + 26 + li * 3.5);
    });

    y += blockH + 3;
  });

  y += 4;

  // ── Benefits ─────────────────────────────────────────────────────────────────
  if (data.benefits && data.benefits.benefit_items.length > 0) {
    checkPage(20);
    rule();
    label('BENEFITS LAYER', GREEN);
    y += 1;

    const { summary, top_benefits, net_by_tenure } = data.benefits;

    // Summary counts
    const bStats = [
      { k: 'Net positive', v: String(summary.net_positive_validators), c: GREEN },
      { k: 'Net negative', v: String(summary.net_negative_validators), c: RED },
      { k: 'Neutral', v: String(summary.net_neutral_validators), c: DIM },
      { k: 'Benefit items', v: String(summary.total_benefit_items), c: BLUE },
    ];
    const bColW = CONTENT_W / bStats.length;
    bStats.forEach(({ k, v, c }, i) => {
      const sx = MARGIN + i * bColW;
      pdf.setFontSize(13);
      pdf.setFont('helvetica', 'bold');
      setTextColor(pdf, c);
      pdf.text(v, sx, y + 5);
      pdf.setFontSize(6.5);
      pdf.setFont('helvetica', 'normal');
      setTextColor(pdf, DIM);
      pdf.text(k.toUpperCase(), sx, y + 9);
    });
    y += 16;

    // Net by tenure
    if (Object.keys(net_by_tenure).length > 0) {
      label('NET IMPACT BY TENURE');
      Object.entries(net_by_tenure).forEach(([tenure, g]) => {
        checkPage(8);
        const netColor = g.avg_net > 0.3 ? GREEN : g.avg_net < -0.3 ? RED : MUTED;
        pdf.setFontSize(8);
        pdf.setFont('helvetica', 'normal');
        setTextColor(pdf, MUTED);
        pdf.text(tenure.toUpperCase(), MARGIN, y + 3);
        pdf.setFont('helvetica', 'bold');
        setTextColor(pdf, netColor);
        pdf.text(`${g.avg_net > 0 ? '+' : ''}${g.avg_net.toFixed(2)}`, MARGIN + 40, y + 3);
        pdf.setFont('helvetica', 'normal');
        setTextColor(pdf, DIM);
        pdf.text(`(${g.count} validators)`, MARGIN + 58, y + 3);
        y += 5;
      });
      y += 2;
    }

    // Top benefits
    label('TOP BENEFITS');
    top_benefits.slice(0, 3).forEach((b) => {
      checkPage(14);
      setFill(pdf, PANEL);
      const bh = 14;
      pdf.rect(MARGIN, y, CONTENT_W, bh, 'F');
      setFill(pdf, GREEN);
      pdf.rect(MARGIN, y, 1.5, bh, 'F');
      pdf.setFontSize(8);
      pdf.setFont('helvetica', 'bold');
      setTextColor(pdf, TEXT);
      const bLines = pdf.splitTextToSize(b.benefit, CONTENT_W - 30);
      pdf.text(bLines[0], MARGIN + 5, y + 5);
      pdf.setFontSize(7);
      pdf.setFont('helvetica', 'normal');
      setTextColor(pdf, MUTED);
      const mechLines = pdf.splitTextToSize(b.mechanism, CONTENT_W - 20);
      pdf.text(mechLines[0], MARGIN + 5, y + 10);
      tag(`MAG ${b.magnitude}`, W - MARGIN - 16, y + 5, GREEN);
      y += bh + 2;
    });
  }

  // ── Demographic Tensions ──────────────────────────────────────────────────────
  if (data.demographic_tensions && data.demographic_tensions.length > 0) {
    checkPage(20);
    rule();
    label('DEMOGRAPHIC TENSIONS', AMBER);
    y += 1;
    data.demographic_tensions.slice(0, 4).forEach((t) => {
      checkPage(16);
      setFill(pdf, PANEL);
      pdf.rect(MARGIN, y, CONTENT_W, 16, 'F');
      pdf.setFontSize(7.5);
      pdf.setFont('helvetica', 'bold');
      setTextColor(pdf, TEXT);
      pdf.text(t.risk_title, MARGIN + 3, y + 5);
      pdf.setFontSize(7);
      pdf.setFont('helvetica', 'normal');
      setTextColor(pdf, MUTED);
      pdf.text(`${t.group_a}: ${Math.round(t.rate_a * 100)}%  vs  ${t.group_b}: ${Math.round(t.rate_b * 100)}%  (gap: ${Math.round(t.gap * 100)}%)`, MARGIN + 3, y + 10);
      const interpLines = pdf.splitTextToSize(t.interpretation, CONTENT_W - 6);
      setTextColor(pdf, DIM);
      pdf.text(interpLines[0], MARGIN + 3, y + 14);
      y += 18;
    });
  }

  // ── Blind Spots ──────────────────────────────────────────────────────────────
  checkPage(30);
  rule();
  label('BLIND SPOTS & LIMITATIONS', RED);
  y += 1;

  if (typeof data.risk_report.blind_spots === 'object') {
    const bs = data.risk_report.blind_spots;
    [
      { k: 'Underrepresented groups', v: bs.underrepresented_groups },
      { k: 'Unmodeled effects', v: bs.unmodeled_effects },
      { k: 'Data gaps', v: bs.data_gaps },
    ].forEach(({ k, v }) => {
      if (!v) return;
      checkPage(12);
      pdf.setFontSize(7);
      pdf.setFont('helvetica', 'bold');
      setTextColor(pdf, MUTED);
      pdf.text(k.toUpperCase(), MARGIN, y);
      y += 3.5;
      body(v, DIM);
      y += 1;
    });
  } else {
    body(String(data.risk_report.blind_spots), DIM);
  }

  // ── Footer on last page ───────────────────────────────────────────────────────
  const totalPages = (pdf as unknown as { internal: { pages: unknown[] } }).internal.pages.length - 1;
  for (let p = 1; p <= totalPages; p++) {
    pdf.setPage(p);
    setFill(pdf, DARK);
    pdf.rect(0, H - 8, W, 8, 'F');
    setDraw(pdf, BORDER);
    pdf.setLineWidth(0.2);
    pdf.line(0, H - 8, W, H - 8);
    pdf.setFontSize(6);
    setTextColor(pdf, DIM);
    pdf.text('CIVICA — POLICY SIMULATION ENGINE', MARGIN, H - 3);
    pdf.text(`civica.site`, W / 2, H - 3, { align: 'center' });
    pdf.text(`Page ${p} of ${totalPages}`, W - MARGIN, H - 3, { align: 'right' });
  }

  const filename = data.seal_id ? `civica-report-${data.seal_id}.pdf` : 'civica-report.pdf';
  pdf.save(filename);
}
