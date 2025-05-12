# Discord-Tomfoolery-

A Discord bot designed to manage course-related tasks, including creating Google Docs for units, merging PDFs with those documents, and facilitating polls for course-related decisions.  This bot utilizes Discord webhooks, Google Docs API, and AWS DynamoDB for persistent data storage.


## Key Features

* **Course Allocation:** Creates dedicated text channels and threads for each course section, managing permissions for instructors and students.
* **Unit Creation:** Generates new Google Docs for course units upon command, automatically linking them to a central "Superdoc" message in a designated thread.
* **PDF Merging:** Allows users to merge PDFs with existing Google Docs representing course units.  This uses a large language model for content integration.
* **Discord Polls:**  Creates custom polls with yes/no options, utilizing Redis for vote tracking and updating poll results in real-time.  Polls can trigger the creation of new units based on vote results.
* **Superdoc Management:** Manages a central "Superdoc" message that acts as an index of all unit Google Docs for a given course.


## Technologies Used

* **Node.js:**  Backend framework.
* **Discord.js:**  Discord API library.
* **Google APIs:** Google Docs API, Google Generative AI API.
* **AWS SDK for JavaScript:**  Interaction with AWS DynamoDB.
* **Redis:** In-memory data store for managing poll votes.
* **Puppeteer:** For PDF generation (using Markdown).
* **pdfjs-dist:** For PDF text extraction.
* **axios:** For HTTP requests.
* **dotenv:** For managing environment variables.


## Prerequisites

1. **Node.js and npm (or yarn):** Make sure you have Node.js and npm (Node Package Manager) installed on your system.  You can download them from [https://nodejs.org/](https://nodejs.org/).
2. **Discord Bot Token:** Create a new Discord bot application and obtain its token.  [https://discord.com/developers/applications](https://discord.com/developers/applications)
3. **Google Cloud Platform (GCP) Project & Credentials:** Create a GCP project, enable the Google Docs API, and download a service account key file (JSON).
4. **AWS Account & Credentials:** Create an AWS account and configure your AWS credentials (access key ID and secret access key). Create a DynamoDB table named `discord-allocated-courses` with a primary key `courseid` of type String.
5. **Redis Server:** Install and run a Redis server.
6. **Gemini API Key:** Obtain a Gemini API key from Google Cloud AI Platform.


## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Braindeeeaad/discord-tomfoolery-.git
   cd discord-tomfoolery-
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Create a `.env` file:** Create a file named `.env` in the root directory of the project and add the following environment variables:

   ```
   DISCORD_TOKEN=<your_discord_bot_token>
   CLIENT_ID=<your_discord_client_id>
   GUILD_ID=<your_discord_guild_id>  
   GOOGLE_KEY_FILE=<path_to_your_google_service_account_key_file.json>
   AWS_ACCESS_KEY=<your_aws_access_key_id>
   AWS_SECRET_ACCESS_KEY=<your_aws_secret_access_key>
   GEMINI_API_KEY=<your_gemini_api_key>
   ```

4. **Deploy commands:**  This registers your bot's slash commands with Discord.
    ```bash
    npm run deploy
    ```

5. **Run the bot:**
   ```bash
   npm run dev  //Use nodemon for automatic restarts on code changes. For production use `node index.cjs`
   ```


## Usage Examples

**1. Add Course:**

```
/add-course course-code:<course_code> course-number:<course_number> course-section:<course_section>
```
For example: `/add-course course-code:CS course-number:101 course-section:Smith`

**2. Create Unit:** (Use this command within the appropriate course's `superdoc` thread)

```
/create-unit name:<unit_name>
```
For example: `/create-unit name:Midterm`

**3. Merge PDF:** (Use this command within the appropriate course's `superdoc` thread)

```
/merge name:<unit_name> pdf:<pdf_file>
```
(Attach the PDF file when using this command.)

**Note:** Error handling is implemented throughout the code; the bot will reply with ephemeral messages indicating errors (e.g., missing permissions, invalid input).


## Project Structure

```
discord-tomfoolery-/
├── aws_utils/          // AWS DynamoDB utilities
│   └── aws-config.cjs
├── commands/           // Discord slash commands
│   ├── coursealloc/
│   │   └── allocate-course.cjs
│   ├── superdoc/
│   │   ├── create-unit.cjs
│   │   └── merge.cjs
│   └── utilities/
│       └── ping.js
├── discord_utils/      // Discord-specific utility functions
│   ├── findSuperdocMessage.cjs
│   ├── makeDiscordPoll.cjs
│   ├── makeDiscordWebhook.cjs
│   ├── makeTextChannel.cjs
│   ├── makeTextThread.cjs
│   └── writeSuperdocMessage.cjs
├── gemini_utils/       // Gemini API interaction
│   └── combineSuperDoc.cjs
├── googledocs_utils/   // Google Docs API utilities
│   ├── clearAndWriteGoogleDoc.cjs
│   ├── configGoogleDoc.cjs
│   ├── createGoogleDoc.cjs
│   ├── getGoogleDoc.cjs
│   └── readGoogleDoc.cjs
├── deploy-commands.cjs // Script to deploy Discord commands
├── dockerfile          // Dockerfile for containerization
├── eslint.config.js    // ESLint configuration
├── index.cjs           // Main bot file
├── package.json        // Project dependencies
└── ...
```


