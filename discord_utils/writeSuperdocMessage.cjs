const {findSuperdocMessage} = require('./findSuperdocMessage.cjs');

//change write superdoc message from using interactions to reply to using the channel, 
//gay function
const writeSuperDocMessage = async(channel,unit_info)=>{
    const superdocMessage = await findSuperdocMessage(channel);

    //if the superdoc message exists, then simply add unit-content to the message
    if(superdocMessage){
        //If the superdoc message only contains "SUPERDOC:"
        if(superdocMessage.content.length<=11){
            await superdocMessage.edit(superdocMessage.content+'\n'+unit_info.lable+'-->'+unit_info.url)
            return;
        }

        await superdocMessage.edit(superdocMessage.content+',\n'+unit_info.lable+'-->'+unit_info.url)
        return; 
    }
    
    //If unit_info is provided and there is no previous superdoc message, then send/pin
    if(unit_info){
        const res = await channel.send(
            {content: "SUPERDOC: \n "+unit_info.lable+'-->'+unit_info.url} 
        )
        await res.pin();
        return; 
    } 
    

    //if unit_info is not provided and there is no superdoc message, then create: 
    const res = await channel.send(
        {content: "SUPERDOC:"} 
    )
    //await res.pin();
    return; 
    
}

module.exports = {writeSuperDocMessage};