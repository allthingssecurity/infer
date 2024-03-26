# Use an official Python runtime as a parent image
FROM python:3.8-slim

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    ffmpeg \
    x264 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's code
COPY . .

# Make port 5000 available to the world outside this container


# Define environment variables for Redis connection and AWS credentials






# Command to run the Flask application

#CMD gunicorn --worker-tmp-dir /dev/shm --config gunicorn_config.py --log-level=info --access-logfile - --error-logfile - fullapp:app

ENV FLASK_APP=fullapp.py

# Expose the port Flask is running on
EXPOSE 5000

# Command to run the Flask application
#CMD ["flask", "run", "--host=0.0.0.0"]

# Make the shell script executable
RUN chmod +x start.sh

# Run start.sh when the container launches
CMD ["/bin/bash", "./start.sh"]





