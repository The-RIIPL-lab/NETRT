from itertools import count
import os
import cv2
import pydicom
import re
#import numpy as np
import datetime
import time

class JPEGToDICOM_Class:

    def __init__(self, jpg_folder_path, extraction_path, dcm_path, debug=False, RAND_ID='', RAND_UID=''):
        self.jpg_folder_path = jpg_folder_path
        self.extraction_path = extraction_path
        self.dcm_path = dcm_path
        self.debug = debug
        self.RAND_ID = RAND_ID
        self.RAND_UID = RAND_UID

    def process(self):

        # Create a list of sorted JPEG files
        jpeg_files = os.listdir(self.extraction_path)
        jpeg_files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))
        
        # Create a sorted list of DICOM files
        dcm_sorted = os.listdir(self.dcm_path)
        dcm_sorted.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        counter = 0
        for jpeg_file in jpeg_files:

            # Get the basename of the image file.
            save_name = jpeg_file.replace('.jpeg', '')

            # Add padding 0s dynamically
            if len(save_name) < 5:
               save_name  = '0' * (5 - len(save_name)) + save_name 
            jpeg_file = os.path.join(self.extraction_path, jpeg_file)

            # Hopefully, identify the source DICOM image for the JPEG file
            reference_dicom = dcm_sorted[counter]
            counter+=1
            reference_dicom = os.path.join(self.dcm_path, reference_dicom)
            ds = pydicom.dcmread(reference_dicom)

            # Read the JPEG file
            jpeg_file = cv2.imread(jpeg_file)
            jpeg_file = cv2.convertScaleAbs(jpeg_file)
            jpeg_bytes=jpeg_file.tobytes()
            list_of_images=[]
            list_of_images.append(jpeg_bytes)

            # Write Meta
            meta = pydicom.Dataset()
            meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            meta.MediaStorageSOPClassUID = pydicom.uid.JPEGExtended12Bit
            meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()

            # Create new data with META
            new_ds = pydicom.Dataset()
            new_ds.file_meta = meta
            new_ds.fix_meta_info()

            new_ds.Modality = 'OT'
            new_ds.ContentDate = str(datetime.date.today()).replace('-','')
            new_ds.ContentTime = str(time.time()) #milliseconds since the epoch

            new_ds.SecondaryCaptureDeviceManufctur = 'RIIPL NETRT'

            new_ds.is_little_endian = True
            new_ds.is_implicit_VR = False
            new_ds.SOPClassUID = pydicom.uid.JPEGExtended12Bit
            new_ds.SOPInstanceUID = pydicom.uid.generate_uid()
            print("SOPClassUID: {} \n SOPInstanceUID: {}".format(
                new_ds.SOPClassUID,
                new_ds.SOPInstanceUID
            ))

            new_ds.SeriesInstanceUID = pydicom.uid.generate_uid()
            new_ds.StudyInstanceUID = pydicom.uid.generate_uid()
            new_ds.FrameOfReferenceUID = pydicom.uid.generate_uid()

            new_ds.BitsStored = 8
            new_ds.BitsAllocated = 8
            new_ds.SamplesPerPixel = 1
            new_ds.HighBit = 7
            new_ds.ImageType = r"ORIGINAL\PRIMARY\AXIAL"
            new_ds.RescaleIntercept = "0"
            new_ds.RescaleSlope = "1"
            new_ds.PixelRepresentation = 0
            new_ds.SamplesPerPixel = 3
            new_ds.SeriesNumber = ds.SeriesNumber + 75

            # Copy these fields from DS
            new_ds.InstanceNumber = ds.InstanceNumber
            #new_ds.ImagesInAcquisition = ds.ImagesInAcquisition
            new_ds.ImagePositionPatient = ds.ImagePositionPatient
            new_ds.ImageOrientationPatient = ds.ImageOrientationPatient
            new_ds.SeriesDescription = "Unapproved Treatment Plan JPEG"
            new_ds.StudyDescription = "Unapproved Treatment Plan JPEG"
            new_ds.Rows, new_ds.Columns, dummy = jpeg_file.shape
            new_ds.PhotometricInterpretation = 'YBR_FULL_422'
            new_ds.InstanceNumber = counter

            # encapsulated dicom
            new_ds.PixelData = pydicom.encaps.encapsulate(list_of_images)
            #new_ds.NumberOfFrames = len(jpeg_files)
            new_ds.NumberOfFrames = 1
            new_ds.PixelRepresentation = 0
            new_ds.PlanarConfiguration = 0

            # Case DEBUG but no CODE
            if self.debug:
                remove_these_tags = ['AccessionNumber']
                for tag in remove_these_tags:
                    if tag in ds:
                        delattr(ds, tag)

                new_ds.PatientID = str("RT_TEST-" + self.RAND_ID).upper()
                new_ds.PatientName = str("RT_TEST-" + self.RAND_ID).upper()
                new_ds.StudyInstanceUID = self.RAND_UID
            
            elif self.debug == False: # if you are not in debug mode
                # Check Image Comments for ID string (Depricated feature)
                if 'ImageComments' in ds: 
                    if len(ds.ImageComments) > 0:
                        sid = re.search(r'(?<=sid\:)[A-z0-9]+', ds.ImageComments )
                        sid=sid.group(0)

                        # Search for SID number
                        if len(sid) > 0: 
                            remove_these_tags = ['AccessionNumber']
                            for tag in remove_these_tags:
                                if tag in ds:
                                    delattr(ds, tag)

                            ds.PatientID = sid
                            ds.PatientName = sid
                else:
                    # Remove Accession Number to cause PACS error
                    remove_these_tags = ['AccessionNumber']
                    for tag in remove_these_tags:
                        if tag in ds:
                            delattr(ds, tag)

            print(" - Creating %s" % f"{save_name}.dcm")
            new_ds.save_as(f"{self.jpg_folder_path}/{save_name}.dcm", write_like_original=False)