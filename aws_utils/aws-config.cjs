const AWS = require('aws-sdk'); 
const dotenv = require('dotenv'); 

dotenv.config(); 
AWS.config.update({
    region: 'us-east-1',
    accessKeyId: process.env.AWS_ACCESS_KEY,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
  })

const dynamodb = new AWS.DynamoDB.DocumentClient()  
const courseTable = 'discord-allocated-courses'  

const db_add_course = async(courseId, item = {courseid: courseId, units : []})=>{
    const params = {
        TableName: courseTable, 
        Item: item
    }
    
    try{
        await dynamodb.put(params).promise(); 
        return params.Item; 
    } catch(error){
        console.log("Error saving item:",error);
        throw error 
    }

}

const db_fetch_course = async(courseId)=>{
    const params = {
        TableName: courseTable, 
        Key:{courseid:courseId}
    };

    try {
        const result = await dynamodb.get(params).promise(); // Using DocumentClient's get method
    
        if (!result.Item) {
          throw new Error('course not found');
        }

        return result.Item 
    } catch(error){
        console.error('Error retrieving course: ',error)
    }

}  

module.exports = {db_add_course,db_fetch_course}; 