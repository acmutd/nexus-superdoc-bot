const { SlashCommandBuilder, MessageFlags , PermissionsBitField} = require('discord.js');
const {makeTextChannel} = require('../../discord_utils/makeTextChannel.cjs'); 
const {makeTextThread} = require('../../discord_utils/makeTextThread.cjs');
const {db_add_course} = require('../../aws_utils/aws-config.cjs');
const {writeSuperDocMessage} = require('../../discord_utils/writeSuperdocMessage.cjs');
const {makeDiscordWebhook} = require('../../discord_utils/makeDiscordWebhook.cjs');

module.exports = {
    data: new SlashCommandBuilder()
		.setName('add-course')
		.setDescription("dd your course to get access to your class's chat!")
        .addStringOption(option =>
            option.setName('course-code')
                .setDescription("Enter branch of your class i.e MATH CS")
        )   
        .addStringOption(option =>
            option.setName('course-number')
                .setDescription("Enter the number of your course i.e 3345 2304")
        ) 
        .addStringOption(option =>
            option.setName('course-section')
                .setDescription("Enter the name of your professor")
        ),    
	async execute(interaction) {

        const courseCode = await interaction.options.getString('course-code');
        const courseNumber = await interaction.options.getString('course-number');
        const courseSection = await interaction.options.getString('course-section');
        
        const userId = interaction.user.id; 
        //const member = await interaction.guild.members.fetch(userId); 
        if (!interaction.guild.members.me.permissions.has([
            PermissionsBitField.Flags.ManageChannels,
            PermissionsBitField.Flags.ManageRoles,
        ])) {
            return await interaction.reply({
                content: "I don't have permission to create channels or manage roles!",
                flags: MessageFlags.Ephemeral,
            });
        }
        
        //make and or set permission to course channel
        const channel_res = await makeTextChannel(interaction,courseCode,courseNumber); 
        const channel = channel_res.channel;
        await channel.permissionOverwrites.edit(userId, {
            ViewChannel: true, 
            SendMessages: true,
          });
        
        //makes a webhook for channel  
        const webhookurl = await makeDiscordWebhook(channel.id,'hook-'+courseNumber+'-'+courseSection);

        //make and or set permission to section thread 
        const thread_res = await makeTextThread(channel,courseSection); 
        const thread = thread_res.thread;
        await thread.members.add(userId);

        //await thread.send(channel.name+'-'+courseSection);
        const sdthread_res = await makeTextThread(channel,'superdoc-'+courseSection);
        const sdthread = sdthread_res.thread;

        //writes super-doc message to superdoc thread
        await writeSuperDocMessage(sdthread);
        await sdthread.members.add(userId);

    
        
        //upload course info to dynamodb if this is a new course
        const courseId = courseCode+'-'+courseNumber+'-'+courseSection;
        if(!channel_res.hasExisted&&!thread_res.hasExisted){
            await db_add_course(courseId,{
                courseid:courseId.toLowerCase(), 
                units:[], 
                channelid:channel.id, 
                threadid:thread.id, 
                sdthreadid:sdthread.id, 
                webhook: webhookurl
            });
        }
        

        await interaction.reply({
            content: "Succesfully logged into course: "+courseCode+"-"+courseNumber+"-"+courseSection, 
            flags: MessageFlags.Ephemeral,
        });

	},
}

