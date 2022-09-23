import os
import cv2
import pydicom
import re

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

        for jpeg_file in jpeg_files:

            save_name = jpeg_file.replace('.jpeg', '')
            
            # add padding 0s dynamically
            if len(save_name) < 5:
               save_name  = '0' * (5 - len(save_name)) + save_name 

            jpeg_file = os.path.join(self.extraction_path, jpeg_file)
               
            reference_dicom = dcm_sorted[counter]
            reference_dicom = os.path.join(self.dcm_path, reference_dicom)

            ds = pydicom.dcmread(reference_dicom)
            
            ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            #ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.1.1'
            ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.7.4'
            ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3"
            ds.file_meta.ImplementationClassUID = "1.2.3.4"
            
            counter = counter + 1
            
            ds.SeriesNumber = ds.SeriesNumber + 75
            ds.SeriesDescription = "Dicom RT Contours JPEG"
            
            jpeg_file = cv2.imread(jpeg_file)
            
            ds.Rows, ds.Columns, dummy = jpeg_file.shape

            if jpeg_file.shape[1] == 3:
                ds.SamplesPerPixel = 3
            else:
                ds.SamplesPerPixel = 1

            ds.PhotometricInterpretation = 'YBR_FULL_422'
            ds.BitsStored = 8
            ds.BitsAllocated = 8
            ds.HighBit = 7
            ds.PixelData = jpeg_file.tobytes()
            ds.PixelRepresentation = 0
            ds.PlanarConfiguration = 0
            ds.NumberOfFrames = 1
            ds.is_little_endian = True
            ds.is_implicit_VR = False

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