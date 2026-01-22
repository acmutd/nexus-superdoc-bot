
A containerized AWS Lambda function for processing documents using PyMuPDF4LLM, OpenAI, and Google Docs API.
1. Prerequisites

    Docker installed and running.

    Google Service Account Key: A service-account-key.json file in the project root.

    Environment Variables: A .env file containing your OPENAI_API_KEY and other secrets.

2. Build the Image

Build the Docker container with the name superdoc:
Bash

docker build -t superdoc .

3. Run the Container

Run the container by mounting the emulator, your Google credentials, and your environment variables.
Bash

docker run -it --rm \
  -v $(pwd)/.env:${LAMBDA_TASK_ROOT}/.env \
  -v ~/.aws:/root/.aws:ro \
  -p 8080:8080 \
  superdoc

(because it uses a specific run time environment to test out the code in the lambda function, it requires an ugly postman request)
so, instead of testing on the container, we can just test simply using uvicorn



run: uvicorn lambda_function:app --port 8000  

\
for ex, u can use the endpoints like they normally would be used and send normal body requests http://127.0.0.1:8000/health 
