# Use an official Python runtime as a parent image
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create a non-root user and group
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Install system dependencies required by rt-utils or other libraries
# libglib2.0-0, libsm6, libxrender1, libxext6, libgl1 are common for image processing/GUI libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create default directories for logs and working data and set ownership
# These paths should match the defaults in config_loader.py if config is not mounted
# Or, they serve as mount points if volumes are used.
RUN mkdir -p /home/appuser/CNCT_logs /home/appuser/CNCT_working /app/config && \
    chown -R appuser:appgroup /home/appuser/CNCT_logs && \
    chown -R appuser:appgroup /home/appuser/CNCT_working && \
    chown -R appuser:appgroup /app && \
    chown -R appuser:appgroup /app/config

# Switch to the non-root user
USER appuser

# Define mount points for persistent data and configuration
VOLUME ["/home/appuser/CNCT_logs", "/home/appuser/CNCT_working", "/app/config"]

# Expose the port the app runs on (should match config.yaml)
# This is a placeholder; the actual port is in config.yaml. 
# Users should ensure their config.yaml inside /app/config matches this or use -p to map.
EXPOSE 11112 

# Define the command to run the application
# It expects config.yaml to be in /app/config/config.yaml
CMD ["python", "main.py", "--config", "/app/config/config.yaml"]

