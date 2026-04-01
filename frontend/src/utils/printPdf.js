/**
 * Print a PDF from a blob URL using a hidden iframe.
 * This is the standard print method used across the application.
 *
 * @param {string} pdfUrl - The blob URL of the PDF to print
 */
export const printPdfFromUrl = (pdfUrl) => {
  if (!pdfUrl) return;
  const iframe = document.createElement('iframe');
  iframe.style.display = 'none';
  document.body.appendChild(iframe);
  iframe.src = pdfUrl;
  iframe.onload = () => {
    iframe.contentWindow.print();
    setTimeout(() => {
      document.body.removeChild(iframe);
    }, 1000);
  };
};
