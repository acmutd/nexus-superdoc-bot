
const { SlashCommandBuilder, MessageFlags, PermissionsBitField } = require('discord.js');
const { downloadPdf } = require('../../pdf_utils/downloadPdf.cjs');
const { combineWithSuperDoc } = require('../../gemini_utils/combineSuperDoc.cjs');
const { findSuperdocMessage } = require('../../discord_utils/findSuperdocMessage.cjs');
const { clearAndWriteGoogleDoc } = require('../../googledocs_utils/clearAndWriteGoogleDoc.cjs');
module.exports = {
    data: new SlashCommandBuilder()
        .setName('merge')
        .setDescription("dd your course to get access to your class's chat!")
        .addStringOption(option =>
            option.setName('name')
                .setDescription("add the name of the unit you want to create")
        )
        .addAttachmentOption(option =>
            option.setName('pdf')
                .setDescription("attach pdf to merge to superdoc!")
        ),
    async merge(unitName, pdfobj, channel) {
        const superDocMessage = await findSuperdocMessage(channel);
        const units = superDocMessage.content.replace("SUPERDOC:", "").split(',');

        const unitMessage = units.find(msg => msg.includes(unitName));
        if (!unitMessage) {

            return {
                content: "Unit doesn't exist",
                flags: MessageFlags.Ephemeral,
            };


        }

        const docUrl = unitMessage.split('-->')[1];
        const documentId = docUrl.match(/[-\w]{25,}/);
        //console.log("Url: "+docUrl+"\nDocId: "+documentId);

        const generateContent = await combineWithSuperDoc(pdfobj.url, documentId);
        console.log('Generated Content: ' + generateContent);

        //convert generatedContent(markdown -> to text)
        await clearAndWriteGoogleDoc(documentId, generateContent);

        //merge the file w/ superdoc

        return {
            content: "File merged",
            flags: MessageFlags.Ephemeral,
        };

    },
    async execute(interaction) {
        await interaction.deferReply({
            flags: MessageFlags.Ephemeral,
        });
        //First get pdf, get current channel's 
        const unitName = await interaction.options.getString('name');
        const pdfobj = await interaction.options.getAttachment('pdf');
        const channel = interaction.channel;
        
        const reply = await this.merge(unitName, pdfobj, channel);
        
        await interaction.editReply(reply); 

    },
}

