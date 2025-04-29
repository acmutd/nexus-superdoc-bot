const {configGoogleDoc} = require('./configGoogleDoc.cjs');

const getGoogleDoc = async (documentId) => {
    const google = await configGoogleDoc();
    const docs = google.docs;
    const res = await docs.documents.get({
        documentId: documentId,
    }); 
    return res.data; 
}

module.exports = {getGoogleDoc}; 
