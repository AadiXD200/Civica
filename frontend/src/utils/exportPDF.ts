import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';

export async function exportReportPDF(sealId?: string): Promise<void> {
  const element = document.querySelector('.stage3-inner') as HTMLElement;
  if (!element) return;

  const canvas = await html2canvas(element, {
    scale: 2,
    useCORS: true,
    backgroundColor: '#0a0a0a',
    windowWidth: element.scrollWidth,
    windowHeight: element.scrollHeight,
  });

  const imgData = canvas.toDataURL('image/png');
  const pdf = new jsPDF({
    orientation: 'portrait',
    unit: 'px',
    format: 'a4',
  });

  const pdfWidth = pdf.internal.pageSize.getWidth();
  const pdfHeight = pdf.internal.pageSize.getHeight();
  const ratio = pdfWidth / canvas.width;
  const scaledHeight = canvas.height * ratio;

  let pagesRendered = 0;
  let remainingHeight = scaledHeight;

  while (remainingHeight > 0) {
    if (pagesRendered > 0) pdf.addPage();
    const yOffset = -pagesRendered * pdfHeight;
    pdf.addImage(imgData, 'PNG', 0, yOffset, pdfWidth, scaledHeight);
    remainingHeight -= pdfHeight;
    pagesRendered++;
  }

  const filename = sealId ? `civica-report-${sealId}.pdf` : 'civica-report.pdf';
  pdf.save(filename);
}
