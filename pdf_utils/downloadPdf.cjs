const axios = require('axios');


const downloadPdf = async(url)=>{
    try {
        // Send a GET request with responseType set to 'arraybuffer' to get the raw PDF data
        const response = await axios.get(url, { responseType: 'arraybuffer' });

        // Convert the response data (arraybuffer) to a Buffer
        const pdfBuffer = Buffer.from(response.data);

        return pdfBuffer;
    } catch (error) {
        console.error('Error downloading the PDF:', error);
        throw error;
    }
}

module.exports = {downloadPdf}; 