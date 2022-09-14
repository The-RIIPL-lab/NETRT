import os
import cv2
import pydicom
import re

class JPEGToDICOM_Class:

    def __init__(self, jpg_folder_path, extraction_path, dcm_path):
        self.jpg_folder_path = jpg_folder_path
        self.extraction_path = extraction_path
        self.dcm_path = dcm_path

    def process(self):

        jpeg_files = os.listdir(self.extraction_path)
        jpeg_files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))
        
        dcm_sorted = os.listdir(self.dcm_path)
        dcm_sorted.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        counter = 0

        for jpeg_file in jpeg_files:

            save_name = jpeg_file.replace('.jpeg', '')
            
            # add padding 0s dynamically
            if len(save_name) < 5:
               save_name  = '0' * (5 - len(save_name)) + save_name 

            jpeg_file = os.path.join(self.extraction_path, jpeg_file)
               
            reference_dicom = dcm_sorted[counter]
            reference_dicom = os.path.join(self.dcm_path, reference_dicom)

            ds = pydicom.dcmread(reference_dicom)
            
            counter = counter + 1
            
            ds.SeriesNumber = ds.SeriesNumber + 75
            
            jpeg_file = cv2.imread(jpeg_file)
            
            ds.Rows, ds.Columns, dummy = jpeg_file.shape

            ds.PhotometricInterpretation = 'YBR_FULL_422'
            ds.SamplesPerPixel = 3
            ds.BitsStored = 8
            ds.BitsAllocated = 8
            ds.HighBit = 7
            ds.PixelData = jpeg_file.tobytes()

            ds.save_as(f"{self.jpg_folder_path}/{save_name}.dcm", write_like_original=False)