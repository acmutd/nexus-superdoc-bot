const {configGoogleDoc} = require('./configGoogleDoc.cjs');


const createGoogleDoc = async (name) => {
    const google = await configGoogleDoc();
    const docs = google.docs; 
    const drive = google.drive;
    try {
        const response = await docs.documents.create({
            requestBody: {
                title: name,
            },
        });
        console.log('Created Document ID:', response.data.documentId);

        await drive.permissions.create({
            fileId: response.data.documentId,
            requestBody: {
              role: 'writer',
              type: 'anyone',
            },
          });

        return response.data; 
    } catch (err) {
        console.error('Error creating document:', err);
    }
}

module.exports = {createGoogleDoc}; 