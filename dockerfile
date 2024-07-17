# Base image using Python 3.8 runtime
# FROM public.ecr.aws/lambda/python:3.8
FROM python:3.9

#Set the working directory
WORKDIR /usr/local/bin

# Copy requirements.txt
COPY requirements.txt .

# Install dependecies using pip
RUN pip install -r requirements.txt

# Copy your python script and any other dependecies
COPY . /usr/local/bin/

# Set the handler (entry point) for Lambda function
CMD ["python", "app.py"]
