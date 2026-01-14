FROM python:3.13-bookworm
ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /app 

# Install system dependencies if needed (e.g., for pymupdf or docling)
RUN apt-get update && apt-get install -y libgl1-mesa-glx && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /app/requirements.txt


RUN pip install --no-cache-dir --prefer-binary -r requirements.txt 
RUN pip install --no-cache-dir --prefer-binary awslambdaric
RUN pip install --no-cache-dir --prefer-binary serverless-wsgi

COPY ./ /app
# Point to the lambda_function.py file and the 'handler' function
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["lambda_function.handler"]


