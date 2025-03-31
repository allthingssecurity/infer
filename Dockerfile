# Use an official Python runtime as a parent image
FROM python:3.8-slim

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    ffmpeg \
    libmagic1 \
    libmagic-dev \
    x264 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# COPY dependencies first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# COPY only your app code AFTER deps
COPY . .

# Set environment variables
ENV FLASK_APP=fullapp.py

# Make port 5000 available
EXPOSE 5000

# Make the shell script executable
RUN chmod +x start.sh

# Entry point
CMD ["/bin/bash", "./start.sh"]
