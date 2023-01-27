FROM python:3.9.16-slim-bullseye
WORKDIR /NETRT
COPY requirements.txt requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install -r requirements.txt
EXPOSE 11112/tcp
COPY . .
CMD ["python","NETRT_Receive.py"]