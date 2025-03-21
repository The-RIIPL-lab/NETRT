# RIIPL Inline contour rendering (CONNECT)

### Description
The RIIPL Inline contour rendering server receives Radiotherapy DICOM images (DicomRT) with contours (RTSTRUCT) and an accompanying anatomtical MR or CT image. 
This tool was designed as a means to share DICOMRT data to PACS system with no RT visualization support. Later updates have allowed alternative processing methods including the creation of DICOM SEG files. 

The default function of this tool is to:

1. Anonymizing incoming data and assign a random ID string
2. Create a new copy of the image for Research Only that uses the Overplane later to render a DICOM RT contour on the CT image. (windowable)

The output series are then automatically forwarded to the destination location/port and removed from local storage.

### New to Version 0.2
- `valid_networks.json` file to provide safe IP ranges for destination servers. While not 100% protection, this is a secondary check to make sure you are sending your data to the correct IP Address. 
- Improved anonymization when deidentifying data
- Dicom SEG exports that can be viewed on original structural images (not available in deidentified mode)
- Fwding of RT images to destination for viewers that support DICOMRT display (Required origional T1 series to existo on PACS. Not available in deidentified mode)

### Installation 
```shell
git clone git remote add origin https://github.com/The-RIIPL-lab/NETRT
cd NETRT

# For conda users
conda env create -f ./conda.yml

# For pip users, in your virtual env
# this requires Python 3.7+
pip install -r requirements.txt
```

### Example `valid_network_ranges.json` file
```json
{
    "valid_networks": [
        "10.10.0.0/16",
        "192.168.1.0/32"
    ]
}
```

### Starting the server
```shell
python ./NETRT_Receive.py \
-p <localhost port> \
-i <localhost ip address> \
-aet <localhost ae title> \
-dp <destination port> \
-dip <destination IP> \
-daet <destination at title>
-D <deidentify: "True" or "False", default is True>
```