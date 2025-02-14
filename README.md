# RIIPL Inline contour rendering

### Description
The RIIPL Inline contour rendering server receives Radiotherapy DICOM images (DicomRT) with contours (RTSTRUCT) and an accompanying anatomtical MR or CT image. This tool extracts the contours from the RTSTUCT file and creates two new image series:

1. A copy of the anat image with binary masks of the contours encoded in the Overlay Plane layers of the DICOM file. (windowable)
2. A stack of JPEG images with the contour masks rendered on the anatomical images with labels and colors for the various ROIs. (non-windowable)

The output series are then automatically forwarded to the destination location/port and removed from local storage.

### New to Version 0.2
- `valid_networks.json` file to provide safe IP ranges for destination servers. While not 100% protection, this is a secondary check to make sure you are sending your data to the correct IP Address. 
- Improved anonymization when deidentifying data
- Dicom SEG exports that can be viewed on original structural images (not available in deidentified mode)
- Fwding of RT images to destination for viewers that support DICOMRT display (Required origional T1 series to existo on PACS. Not available in deidentified mode)

### Installation 
```shell
git clone https://github.com/The-RIIPL-lab/NETRT.git

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
-daet <destination at title> \
-D <deidentify: True or False. True is default> \
-nvf <valid_network_ranges.json path> 
```
