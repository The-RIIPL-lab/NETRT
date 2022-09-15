# RIIPL Inline contour rendering

### Description
The RIIPL Inline contour rendering server receives Radiotherapy DICOM images (DicomRT) with contours (RTSTRUCT) and an accompanying anatomtical MR or CT image. This tool extracts the contours from the RTSTUCT file and creates two new image series:

1. A copy of the anat image with binary masks of the contours encoded in the Overlay Plane layers of the DICOM file. (windowable)
2. A stack of JPEG images with the contour masks rendered on the anatomical images with labels and colors for the various ROIs. (non-windowable)

The output series are then automatically forwarded to the destination location/port and removed from local storage.

### Installation 
```shell
git clone git remote add origin http://rhgitserv01pv.medctr.ad.wfubmc.edu/rbarcus/NETRT.git

cd NETRT

# For conda users
conda env create -f ./conda.yml

# For pip users, in your virtual env
# this requires Python 3.7+
pip install -r requirements.txt
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
```