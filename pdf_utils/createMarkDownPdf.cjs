 
const markdownit = require('markdown-it');
const puppeteer = require('puppeteer');

const createMarkDownPDF = async(textContent) => {
    const md = markdownit(); 
    const htmlContent = md.render(textContent); 
    // Launch puppeteer and generate PDF
    const browser = await puppeteer.launch();
    const page = await browser.newPage();

    // Set the HTML content in puppeteer
    await page.setContent(htmlContent, { waitUntil: 'domcontentloaded' });

    // Generate PDF
    const pdfBuffer = await page.pdf({
        format: 'A4',
        margin: { top: '20px', right: '20px', bottom: '20px', left: '20px' }
    });

    await browser.close();

    return pdfBuffer.toJSON().data; // return proper 8-int array  
};

module.exports = {createMarkDownPDF};
