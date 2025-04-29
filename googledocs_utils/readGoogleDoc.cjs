const {getGoogleDoc} = require('./getGoogleDoc.cjs'); 


const readGoogleDoc = async (documentId) => {
    try {
        //retriving google-doc by id 
        const doc = await getGoogleDoc(documentId);
        // Extract text content from the document's body
        const docContent = doc.body.content;
        let text = '';

        // Iterate through the content and extract the text from each paragraph
        docContent.forEach(element => {
            if (element.paragraph) {
                   element.paragraph.elements.forEach(subElement => {
                    if (subElement.textRun) {
                        text += subElement.textRun.content;
                    }
                });
            }
        });

        console.log('Document Text:', text);
        return text;
    } catch (error) {
        console.error("Error Reading Google Doc: ", error);
        throw error;
    }
    
}

module.exports = {readGoogleDoc};