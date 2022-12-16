#!/bin/bash

conda activate NETRT

# You will need to customize your various source and destination flags here
NETRT_PATH="/mnt/Poe/richard/NETRT"
echo python ${NETRT_PATH}/NETRT_Receive.py -D True
