#from itertools import count
import os
from io import BytesIO
#import cv2
from PIL import Image
import pydicom
import re
import numpy as np
import datetime
import time
import tempfile

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

        ''' # Dev notes
        I think we want to iterate through all of the images in order
        and create a single encoded pixel array for the whole JPEG images 
        series
        '''

        # Iteratively rotate through the JPEG images adding them to pixel data
        counter = 0
        
        # Define the image array
        number_of_frames = len(jpeg_files) # length of the jpeg file list
        jpeg_sample = Image.open(os.path.join(self.extraction_path,jpeg_files[0]))
        jpeg_sample.load()
        jpeg_sample = np.asarray(jpeg_sample, dtype="int8")
        print("Sample Array Size %s" % str(jpeg_sample.shape))

        encoded_frame_items = []
        for jpeg_file in jpeg_files:

            # Get the basename of the image file.
            save_name = jpeg_file.replace('.jpeg', '')

            # Add padding 0s dynamically
            if len(save_name) < 5:
               save_name  = '0' * (5 - len(save_name)) + save_name 
            jpeg_file = os.path.join(self.extraction_path, jpeg_file)

            # Hopefully, identify the source DICOM image for the JPEG file
            reference_dicom = dcm_sorted[counter]
            reference_dicom = os.path.join(self.dcm_path, reference_dicom)
            ds = pydicom.dcmread(reference_dicom)

            # Read the JPEG file
            img = Image.open(jpeg_file)
            img.load()
            instance_byte_str_buffer = BytesIO()
            img.save(instance_byte_str_buffer, "JPEG", quality=80, icc_profile=img.info.get('icc_profile'), progressive=False)
            t = instance_byte_str_buffer.getvalue()
            encoded_frame_items.append(t)
            
            # Move to next file
            counter+=1

        suffix = '.dcm'
        filename_little_endian = tempfile.NamedTemporaryFile(suffix=suffix).name

        # Write Meta
        meta = pydicom.dataset.FileMetaDataset()
        meta.TransferSyntaxUID = pydicom.uid.JPEGExtended12Bit
        meta.MediaStorageSOPClassUID = pydicom.uid.MultiFrameTrueColorSecondaryCaptureImageStorage
        meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()

        # Create new data with META
        new_ds = pydicom.dataset.FileDataset(
            filename_little_endian, {},
            file_meta=meta)

        # Create Pixel Data by using converted to pytes
        ds.LossyImageCompression = '00'
        new_ds.NumberOfFrames = number_of_frames
        new_ds.Rows, new_ds.Columns, dummy = jpeg_sample.shape
        print(new_ds.NumberOfFrames)

        # Encapsulate image stack into a single dicom
        PixelData_encoded = encoded_frame_items
        data_elem_tag = pydicom.tag.TupleTag((0x7FE0, 0x0010))
        enc_frames = pydicom.encaps.encapsulate(PixelData_encoded, has_bot=True)
        pd_ele = pydicom.dataelem.DataElement(data_elem_tag, 'OB', enc_frames, is_undefined_length=True)
        new_ds.add(pd_ele)

        new_ds.FrameIncrementPointer = 1
        new_ds.PixelRepresentation = 0
        new_ds.PlanarConfiguration = 0

        new_ds.Modality = 'OT'
        new_ds.ContentDate = str(datetime.date.today()).replace('-','')
        new_ds.ContentTime = str(time.time()) #milliseconds since the epoch

        new_ds.SecondaryCaptureDeviceManufacturer = 'RIIPL NETRT'

        new_ds.is_little_endian = True
        new_ds.is_implicit_VR = False
        new_ds.SOPClassUID = meta.MediaStorageSOPClassUID
        new_ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID

        new_ds.SeriesInstanceUID = pydicom.uid.generate_uid()
        new_ds.StudyInstanceUID = pydicom.uid.generate_uid()
        new_ds.FrameOfReferenceUID = pydicom.uid.generate_uid()

        new_ds.SeriesDescription = "Unapproved Treatment Plan JPEG"
        new_ds.StudyDescription = "Unapproved Treatment Plan JPEG"
        new_ds.StudyID = "RAB01"

        new_ds.BitsStored = 8
        new_ds.BitsAllocated = 8
        new_ds.SamplesPerPixel = 3
        new_ds.HighBit = 7
        new_ds.ImageType = r"ORIGINAL\PRIMARY\AXIAL"
        new_ds.RescaleIntercept = "0"
        new_ds.RescaleSlope = "1"
        new_ds.PixelRepresentation = 0
        new_ds.SamplesPerPixel = 3
        new_ds.SeriesNumber = ds.SeriesNumber + 75
        new_ds.PhotometricInterpretation = 'YBR_FULL_422'
        new_ds.ColorSpace = 'sRGB'

        # Debug
        #print("Size is {}".format(new_ds.pixel_array.shape))

        # Copy these fields from DS
        #new_ds.InstanceNumber = ds.InstanceNumber
        #new_ds.ImagesInAcquisition = ds.ImagesInAcquisition
        #new_ds.ImagePositionPatient = ds.ImagePositionPatient
        #new_ds.ImageOrientationPatient = ds.ImageOrientationPatient
        #new_ds.InstanceNumber = counter

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

        #print(" - Creating %s" % f"{save_name}.dcm")
        #new_ds.save_as(f"{self.jpg_folder_path}/{save_name}.dcm", write_like_original=False)
        new_ds.save_as(f"{self.jpg_folder_path}/single_output_dicom.dcm", write_like_original=False)
