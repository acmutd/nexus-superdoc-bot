const fs = require('node:fs');
const path = require('node:path');
const { Client, Collection, Events, GatewayIntentBits, MessageFlags  } = require('discord.js');
const { SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');

const dotenv = require('dotenv'); 
dotenv.config();


const Redis = require("redis");
const redisClient = Redis.createClient(); // Connects to local Redis server
redisClient.connect();
const token = process.env.DISCORD_TOKEN

const client = new Client({ intents: [
	GatewayIntentBits.Guilds, 
	GatewayIntentBits.GuildWebhooks, 
	GatewayIntentBits.GuildMessages, 
	GatewayIntentBits.MessageContent
] });

client.commands = new Collection();


const foldersPath = path.join(__dirname, 'commands');
const commandFolders = fs.readdirSync(foldersPath);

for (const folder of commandFolders) {
	const commandsPath = path.join(foldersPath, folder);
	const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.cjs'));
	for (const file of commandFiles) {
		const filePath = path.join(commandsPath, file);
		const command = require(filePath);
		// Set a new item in the Collection with the key as the command name and the value as the exported module
		if ('data' in command && 'execute' in command) {
			client.commands.set(command.data.name, command);
		} else {
			console.log(`[WARNING] The command at ${filePath} is missing a required "data" or "execute" property.`);
		}
	}
}

// When the client is ready, run this code (only once).
// The distinction between `client: Client<boolean>` and `readyClient: Client<true>` is important for TypeScript developers.
// It makes some properties non-nullable.
client.once(Events.ClientReady, readyClient => {
	console.log(`Ready! Logged in as ${readyClient.user.tag}`);
});

// Log in to Discord with your client's token
client.login(token);


//Discord doesn't have a webhook event,so I gotta do this MacGyver type shi 

//Listen to webhooks
client.on(Events.MessageCreate, async (message) =>{
	//console.log('Message:', message.content);
	if(!message.webhookId) return;

	
	const thread = message.channel; 
	const attachments = message.attachments;
	//assume webhook string is: create-unit,unitName  
	const commandstr = message.content.split(',');
	const commandName = commandstr[0];
	const unitName = commandstr[1];
	console.log('Webhook Command:',message.content);
	//get command object
	
	const command = client.commands.get(commandName);
	if(!command){
		console.log('Un-recognized commadn');
		return; 
	}
	let reply = undefined; 
	try{
		switch(commandName){
			case 'create-unit':
				const channel = thread.parent;
				await message.delete();
				reply = await command.create_unit(unitName,thread,channel); 
			break; 
			case 'merge': 
				const pdfobj  = attachments.first();
				reply = await command.merge(unitName,pdfobj,thread);
				await message.delete();
				//console.log('Attachments: '+pdfurl); 

			break;
		}
		await thread.send({
			content: reply.content
		}) 
		 
	} catch(error) {
		console.error(error);

	}
	
	//Gotta make mock interaction object depending on command and send 

});

//deals with yes/no poll clicks
client.on(Events.InteractionCreate, async (interaction) => {
	if (!interaction.isButton() || !interaction.customId.startsWith("poll_")) return;
	//await redisClient.connect();

	const messageId = interaction.message.id;
	const userId = interaction.user.id;
	const optionIndex = interaction.customId.split("_")[1];
	const embedtitle = interaction.message.embeds[0].title; 
  
	// Check if user already voted, if so presists whether they are the creator or not
	const hasVoted = await redisClient.hExists(`poll:${messageId}:votes`, userId);
	let creatorBool = false
	if (hasVoted) {
		const userVoteData = await redisClient.hGet(
			`poll:${messageId}:votes`,
			userId
		  );
		const { isCreator  } = JSON.parse(userVoteData); 
		creatorBool = isCreator;				
	}
	 
	
	// Register vote
	//await redisClient.hSet(`poll:${messageId}:votes`, userId, optionIndex);
	await redisClient.hSet(
		`poll:${messageId}:votes`, 
		userId, 
		JSON.stringify({ optionIndex: optionIndex, isCreator: creatorBool })
	  );
  
	// Update embed 
	/*
	const votes = await redisClient.hGetAll(`poll:${messageId}:votes`);
	const yesVotes = Object.values(votes).filter(v => v === "0").length;
	const noVotes = Object.values(votes).filter(v => v === "1").length;
	*/ 
	const votes = await redisClient.hGetAll(`poll:${messageId}:votes`);
	let yesVotes = 0, noVotes = 0;
	for (const userId in votes) {
		const { optionIndex } = JSON.parse(votes[userId]);
		if (Number(optionIndex) === 0) yesVotes++;
		else if (Number(optionIndex)) noVotes++;
	}

	const updatedEmbed = new EmbedBuilder()
	  .setTitle(embedtitle)
	  .setDescription(`✅ Yes: ${yesVotes}\n❌ No: ${noVotes}`);
  
	await interaction.message.edit({ embeds: [updatedEmbed] });
	await interaction.reply({ content: "Vote Complete!", ephemeral: true });

  });

  //deals with end poll clicks
client.on(Events.InteractionCreate, async (interaction) => {
	if (!interaction.isButton() || !interaction.customId.startsWith("end_poll")) return;
	

	const messageId = interaction.message.id;
	const userId = interaction.user.id;
	const optionIndex = interaction.customId.split("_")[1];
	const channel = interaction.channel;

	const userVoteData = await redisClient.hGet(
		`poll:${messageId}:votes`,
		userId
	  );
	const { isCreator  } = JSON.parse(userVoteData);
	console.log("userVoteData:",userVoteData);
	if (!isCreator) {
		return interaction.reply({
			content: "❌ Only the poll creator can end this!",
			ephemeral: true,
		});
  	}

	console.log(interaction.message.embeds);
	const unitName = interaction.message.embeds[0].title.split(":")[1];
	console.log("Channel members:",channel.members.thread);
	const numMembers = channel.members.thread.memberCount;
  
	// Update embed (example)
	const votes = await redisClient.hGetAll(`poll:${messageId}:votes`);
	let yesVotes = 0, noVotes = 0;
	for (const userId in votes) {
		const { optionIndex } = JSON.parse(votes[userId]);
		if (optionIndex === 0) yesVotes++;
		else if (optionIndex === 1) noVotes++;
	}
	
	//const yesVotes = Object.values(votes).filter(v => v === "0").length;
	//const noVotes = Object.values(votes).filter(v => v === "1").length;

	const command = client.commands.get('create-unit');
	const propYV = yesVotes/numMembers; 
	console.log("numMembers",numMembers); 
	console.log("yesVotes",yesVotes); 
	console.log("yesVotes/numMembers",propYV);
	//N
	//const rest = command.create_unit(unitName,channel,channel.parent);
	const rest = ((yesVotes/numMembers)>=0.2 || yesVotes>=10) ? command.create_unit(unitName,channel,channel.parent) : undefined; 

	console.log("Poll Result:",rest);
	let updatedEmbed = new EmbedBuilder()
	  .setTitle("Poll Ended")
	  .setDescription(`✅ Yes: ${yesVotes}\n❌ No: ${noVotes}\n ${unitName} created!`);
	if(!rest){
		updatedEmbed = new EmbedBuilder()
		.setTitle("Poll Ended")
		.setDescription(`✅ Yes: ${yesVotes}\n❌ No: ${noVotes}\n Insufficent votes to create ${unitName}`);
	}
  
	await redisClient.del(`poll:${messageId}:votes`);
	await interaction.message.delete();
	await interaction.reply({ embeds: [updatedEmbed] });  });

client.on(Events.InteractionCreate, async interaction => {
	if (!interaction.isChatInputCommand()) return;

	const command = interaction.client.commands.get(interaction.commandName);

	if (!command) {
		console.error(`No command matching ${interaction.commandName} was found.`);
		return;
	}

	try {
		await command.execute(interaction);
	} catch (error) {
		console.error(error);
		if (interaction.replied || interaction.deferred) {
			await interaction.followUp({ content: 'There was an error while executing this command!', flags: MessageFlags.Ephemeral });
		} else {
			await interaction.reply({ content: 'There was an error while executing this command!', flags: MessageFlags.Ephemeral });
		}
	}
});
