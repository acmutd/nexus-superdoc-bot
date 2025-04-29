
const axios = require('axios'); 
const dotenv = require('dotenv'); 
dotenv.config();
/**
 * 
 * @param {*} channelId 
 * @param {*} webhookname 
 * @returns https://discord.com/api/webhooks/{{webhook_id}}/{{webhook_token}}
 */

const makeDiscordWebhook = async(channelId,webhookname)=>{
    const url = `https://discord.com/api/channels/${channelId}/webhooks`;
    
        const payload = {
            name: webhookname
        };
    
        try {
            const response = await axios.post(url, payload, {
                headers: {
                    Authorization: `Bot ${process.env.DISCORD_TOKEN}`,
                    'Content-Type': 'application/json'
                }
            });
            console.log('Webhook created:', response.data);
            //https://discord.com/api/webhooks/{{webhook_id}}/{{webhook_token}}
            return response.data.url;
        } catch (error) {
            console.error('Error creating webhook:', error.response ? error.response.data : error.message);
        }

}

module.exports = {makeDiscordWebhook};