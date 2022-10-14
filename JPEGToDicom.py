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

        jpeg_files = os.listdir(self.extraction_path)
        jpeg_files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))
        
        dcm_sorted = os.listdir(self.dcm_path)
        dcm_sorted.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        counter = 0
        list_of_images=[]
        for jpeg_file in jpeg_files:

            save_name = jpeg_file.replace('.jpeg', '')
            
            # add padding 0s dynamically
            if len(save_name) < 5:
               save_name  = '0' * (5 - len(save_name)) + save_name 

            jpeg_file = os.path.join(self.extraction_path, jpeg_file)
            reference_dicom = dcm_sorted[counter]
            counter+=1
            reference_dicom = os.path.join(self.dcm_path, reference_dicom)            
            jpeg_file = cv2.imread(jpeg_file)
            jpeg_file = cv2.convertScaleAbs(jpeg_file)
            #jpeg_bytes=jpeg_file.tobytes()
            list_of_images.append(jpeg_bytes)

        # Create image from array of encapsulate bits
        ds = pydicom.dcmread(reference_dicom)

        file_meta = pydicom.Dataset()
        file_meta.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
        #file_meta.file_meta.MediaStorageSOPInstanceUID
        #file_meta.ImplementationClassUID

        new_ds = pydicom.FileDataset(f"{save_name}.dcm", file_meta=file_meta)
        new_ds.Modality = 'OT'
        new_ds.ContentDate = str(datetime.date.today()).replace('-','')
        new_ds.ContentTime = str(time.time()) #milliseconds since the epoch

        #new_ds.StudyInstanceUID
        #new_ds.SeriesInstanceUID
        #new_ds.SOPInstanceUID
        new_ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
        new_ds.SecondaryCaptureDeviceManufctur = 'RIIPL NETRT'

        #ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        new_ds.SamplesPerPixel = 3
        new_ds.SeriesNumber = ds.SeriesNumber + 75
        new_ds.SeriesDescription = "Unapproved Treatment Plan JPEG"
        new_ds.StudyDescription = "Unapproved Treatment Plan JPEG"
        new_ds.BitsStored = 24
        new_ds.BitsAllocated = 24
        new_ds.HighBit = 23

        new_ds.Rows, new_ds.Columns, dummy = jpeg_file.shape
        
        new_ds.PhotometricInterpretation = 'YBR_FULL_422'

        # encapsulated dicom
        new_ds.PixelData = pydicom.encaps.encapsulate(list_of_images)
        #ds.PixelData = jpeg_file.tobytes()
        new_ds.NumberOfFrames = len(list_of_images)
        new_ds.PixelRepresentation = 0
        new_ds.PlanarConfiguration = 0
        new_ds.is_little_endian = True
        new_ds.is_implicit_VR = False

        if self.debug:
            remove_these_tags = ['AccessionNumber']
            for tag in remove_these_tags:
                if tag in ds:
                    delattr(ds, tag)

            ds.PatientID = str("RT_TEST-" + self.RAND_ID).upper()
            ds.PatientName = str("RT_TEST-" + self.RAND_ID).upper()
            ds.StudyInstanceUID = self.RAND_UID

        print(" - Creating %s" % f"{save_name}.dcm")
        ds.save_as(f"{self.jpg_folder_path}/{save_name}.dcm", write_like_original=False)