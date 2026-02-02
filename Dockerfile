# Use the official AWS Lambda Python 3.13 base image
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.13
ENV PIP_ROOT_USER_ACTION=ignore

# The working directory in AWS base images is /var/task by default
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt
RUN pip install --no-cache-dir serverless-wsgi

COPY . .

CMD ["lambda_function.handler"]