const {writeSuperDocMessage} = require('./writeSuperdocMessage.cjs');
/**
 * 
 * @param {
 * } interaction 
 * @param {*} channel 
 * @param {string} courseSection 
 * @returns {thread:thread, hasExisted} //hasExisted returns true if the thread had already been made before
 */
const makeTextThread = async (channel, courseSection) => {

    //If there ins't a channel
    if (!channel) {
        console.log("makeTextThread: undefined channel");
        return;
    }
    try {
        //const activeThreads = await channel.threads.fetchActive();
        //console.log("Active Threads in Channel: ", activeThreads.threads);
        const assumingThread = channel.threads.cache.find(x => x.name === courseSection);// 

        if (assumingThread)
            return {thread:assumingThread,hasExisted:true};

        //else make thread  
        const thread = await channel.threads.create({
            name: courseSection,
            autoArchiveDuration: 60, // Auto-archive after 60 minutes of inactivity
            type: 11, // 11 = Public thread
            reason: 'Discussion for the course',
        });

        
        //await interaction.reply(`Thread created: ${thread.name}`);
        return {thread:thread,hasExisted:false};
    } catch (error) {
        console.log("makeTextThread Error:",error);

    }
    return undefined;
    //If the thread already exists, return it      
}



module.exports = { makeTextThread }; 