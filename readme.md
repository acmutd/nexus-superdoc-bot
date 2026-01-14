This README explains how to build and run your superdoc container locally. Since this image is designed for AWS Lambda, we use the Runtime Interface Emulator (RIE) to simulate the Lambda environment on your machine.
superdoc

A containerized AWS Lambda function for processing documents using PyMuPDF4LLM, OpenAI, and Google Docs API.
1. Prerequisites

    Docker installed and running.

    Google Service Account Key: A service-account-key.json file in the project root.

    Environment Variables: A .env file containing your OPENAI_API_KEY and other secrets.

2. Local Setup (One-time)

To test the Lambda function locally, you need the AWS Lambda Runtime Interface Emulator (RIE) on your host machine.
Bash

mkdir -p ~/.aws-lambda-rie && \
curl -Lo ~/.aws-lambda-rie/aws-lambda-rie https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie && \
chmod +x ~/.aws-lambda-rie/aws-lambda-rie

3. Build the Image

Build the Docker container with the name superdoc:
Bash

docker build -t superdoc .

4. Run the Container

Run the container by mounting the emulator, your Google credentials, and your environment variables.
Bash

docker run -it --rm \
  -v ~/.aws-lambda-rie/aws-lambda-rie:/usr/bin/aws-lambda-rie \
  -v $(pwd)/service-account-key.json:/app/service-account-key.json \
  -v $(pwd)/.env:/app/.env \
  -p 8080:8080 \
  --entrypoint /usr/bin/aws-lambda-rie \
  superdoc \
  python -m awslambdaric lambda_function.handler

5. Test the Function

Once the container is running, you can trigger the function by sending a JSON payload via curl.
Bash

curl -XPOST "http://localhost:8080/2015-03-31/functions/function/invocations" \
     -d '{
       
     }'