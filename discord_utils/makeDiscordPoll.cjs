const axios = require('axios');
const {  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');


const dotenv = require('dotenv'); 
dotenv.config();


const makeDiscordPoll = async(channelId, question, answers, duration = 24, allowMultiselect = false) => {
    const url = `https://discord.com/api/v10/channels/${channelId}/messages`;

    const payload = {
        content: "Here's a poll!",
        poll: {
            question: { text: question },
            answers: answers.map(answer => ({ poll_media: { text: answer } })),
            duration,
            allow_multiselect: allowMultiselect
        }
    };

    try {
        const response = await axios.post(url, payload, {
            headers: {
                Authorization: `Bot ${process.env.DISCORD_TOKEN}`,
                'Content-Type': 'application/json'
            }
        });
        console.log('Poll created:', response.data);
    } catch (error) {
        console.error('Error creating poll:', error.response ? error.response.data : error.message);
    }
}

const makeCustomPoll = async(question,options)=>{
    // Limit to 5 options (Discord allows 5 buttons per row)
    if (options.length > 5) {
      return interaction.reply({ content: 'Max 5 options allowed!', ephemeral: true });
    }

    // Create buttons for each option
    const buttons = options.map((option, index) =>
      new ButtonBuilder()
        .setCustomId(`poll_${index}`) // e.g., "poll_0", "poll_1"
        .setLabel(option)
        .setStyle(ButtonStyle.Primary)
    );

    const row = new ActionRowBuilder().addComponents(buttons);

    //figure out how to set permissions to only the user being able to end this
    const endButton = new ButtonBuilder()
        .setCustomId('end_poll')
        .setLabel('End Poll')
        .setStyle(ButtonStyle.Danger);

    const row2 = new ActionRowBuilder().addComponents(endButton);
    // Create the poll embed
    const unitName = question.split(":")[1];
    const embed = new EmbedBuilder()
      .setTitle(question)
      .setDescription(`✅ Yes: ${1}\n❌ No: ${0}\n ${unitName} created!`)
      .setColor(0x00AE86);

    //await interaction.reply({ embeds: [embed], components: [row] }); 
    return { embeds: [embed], components: [row,row2] };
}
if(require.main === module){
    makeDiscordPoll('1347668303845265418',"golf or wang",["golf","wang"],1,false);
}
module.exports = {makeDiscordPoll,makeCustomPoll};
