// Create a text channel with specific permissions

const{ChannelType, PermissionsBitField} = require('discord.js'); 

/**
 * 
 * @param {*} interaction 
 * @param {*} courseCode 
 * @param {*} courseNumber 
 * @returns {channel:channel,hasExisted}//hasExisted returns true if the channel had already been made before
 */
const makeTextChannel =  async(interaction, courseCode, courseNumber)=>{
    
    //If channel is already made then early return
    const assumingChannel = interaction.guild.channels.cache.find(c => c.name === courseCode.toLowerCase()+'-'+courseNumber.toLowerCase());
    if(assumingChannel)
        return {channel:assumingChannel,hasExisted:true}; 
    
    try{
        const channel = await interaction.guild.channels.create({
            name: courseCode+'-'+courseNumber,
            type: 0, // 0 = Text channel
            permissionOverwrites: [
                {
                    id: interaction.guild.id, // Default everyone role
                    deny: [PermissionsBitField.Flags.ViewChannel], // Hide the channel from everyone
                },
                {
                    id: interaction.user.id, // Grant access to the command user
                    allow: [PermissionsBitField.Flags.ViewChannel,PermissionsBitField.Flags.SendMessages],
                },
                {
                    id: interaction.guild.members.me.id, // Bot
                    allow: [
                        PermissionsBitField.Flags.ViewChannel,
                        PermissionsBitField.Flags.ManageChannels,
                        //PermissionsBitField.Flags.ManageRoles,
                    ],
                }
            ],
        }); 
        //await interaction.reply(`Created channel: ${channel.name}`);
        return {channel:channel,hasExisted:false};

    } catch(error){
        console.log("Error creating channel: ",error);
        await interaction.reply(`Sorry there was an error creating a channel`); 
    }
    

    return undefined; 

    
     

}
module.exports = {makeTextChannel}
