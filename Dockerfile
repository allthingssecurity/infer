# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's code
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variables for Redis connection and AWS credentials
ENV REDIS_HOST=""
ENV REDIS_PORT=""
ENV REDIS_USERNAME=""
ENV REDIS_PASSWORD=""
ENV ACCESS_ID=""
ENV SECRET_KEY=""

ENV FLASK_APP=ep.py



# Command to run the Flask application
CMD ["flask", "run", "--host=0.0.0.0"]


