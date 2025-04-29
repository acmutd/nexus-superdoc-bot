const {google} = require('googleapis')
const googledocs = require('@googleapis/docs')
const dotenv = require('dotenv'); 
const { GoogleAuth } = require('google-auth-library');

dotenv.config();



const configGoogleDoc = async () => {

    try {
        console.log("Google auth: ",google.auth);
        const auth = new GoogleAuth({
            keyFile: process.env.GOOGLE_KEY_FILE,  // Path to your Google service account key file
            scopes: [
              'https://www.googleapis.com/auth/documents',
              'https://www.googleapis.com/auth/drive',
            ],
          });
        const authClient = await auth.getClient();
        
        
        const docs = await googledocs.docs({
            version: 'v1',
            auth: authClient
        });
        const drive = google.drive({ 
            version: 'v3', 
            auth: authClient
        });
        console.log("googledocs authenticated")
        return {docs:docs,drive:drive};

    } catch (error) {
        console.error('Error Authentication GoogleDoc Access', error);
        throw error;
    }
}


module.exports = {configGoogleDoc}; 

if(require.main === module)
    configGoogleDoc();