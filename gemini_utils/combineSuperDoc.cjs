
const { GoogleGenerativeAI }  = require('@google/generative-ai');
//const {createMarkDownPDF} = require('../pdf_utils/createMarkDownPdf.js');
const {getPdfText}  = require('../pdf_utils/getPdfText.cjs');
const {readGoogleDoc} = require('../googledocs_utils/readGoogleDoc.cjs'); 
const {clearAndWriteGoogleDoc} = require('../googledocs_utils/clearAndWriteGoogleDoc.cjs'); 

const dotenv = require('dotenv');

dotenv.config();

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

/*
// Converts buffer data to a GoogleGenerativeAI.Part object.
const bufferToGenerativePart = (buffer, mimeType) => ({
    inlineData: {
        data: buffer.toString("base64"),
        mimeType,
    },
});

*/


const combineWithSuperDoc = async (file, documentId) => {
    try {
        const superdocText = await readGoogleDoc(documentId);  
        const fileText = await getPdfText(file);



        
        // Choose a Gemini model
        const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
        const prompt = "Incorporate both of these documents together, avoid redundancy, and format the notes.";

        const generatedContent = await model.generateContent([prompt, superdocText, fileText]);

       
       return generatedContent.response.text();
    } catch (error) {
        throw error;
    }
};

module.exports =  { combineWithSuperDoc };
