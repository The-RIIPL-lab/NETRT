FROM python:3.12.8-slim-bullseye
WORKDIR /NETRT
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip -U
RUN pip install -r requirements.txt
COPY . .
CMD ["python","NETRT_Receive.py"]