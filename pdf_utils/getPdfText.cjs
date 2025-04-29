
//const pdfjsLib = require("pdfjs-dist/legacy/build/pdf.mjs");


const loadPDFJS = async () => {
  //
  return await import('pdfjs-dist/legacy/build/pdf.mjs');  // ✅ Dynamically load the ESM module
};

const getPdfText = async (fileUrl) => {
  const pdfjslib = await loadPDFJS(); 
  const pdf = await pdfjslib.getDocument(fileUrl).promise; 
  const maxPages = pdf.numPages;
  let text = '';

  // Loop through all pages to extract text
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent(); // Use getTextContent method
    const pageText = content.items.map((item) => item.str).join(' ');
    text += pageText + '\n';
  }
 
  
  return text;


}

module.exports = { getPdfText };