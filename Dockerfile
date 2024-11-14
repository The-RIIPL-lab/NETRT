# Use an official Python runtime as a parent image
FROM python:3.9.16-slim-bullseye

# Install necessary packages
RUN apt-get update && \
    apt-get install -y libgl1-mesa-glx libglib2.0-0 libgirepository1.0-dev

# Install your Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files into the container at /app
COPY . /app

# Fix potential Windows line endings and add execute permission
RUN sed -i 's/\r$//' /app/NETRT_Receive.py
RUN chmod +x /app/NETRT_Receive.py

# Define environment variable
ENV PYTHONDONTWRITEBYTECODE 1

# Run NETRT_Receive.py when the container launches
CMD ["python", "NETRT_Receive.py"]