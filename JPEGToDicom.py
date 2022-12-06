import os
from io import BytesIO
from PIL import Image
import pydicom
import re
import numpy as np
import datetime
import tempfile

class JPEGToDICOM_Class:

    def __init__(self, jpg_folder_path, extraction_path, dcm_path, debug=False, STUDY_INSTANCE_ID='', SC_SOPInstanceUID='',FOD_REF_ID='', RAND_ID=''):
        self.jpg_folder_path = jpg_folder_path
        self.extraction_path = extraction_path
        self.dcm_path = dcm_path
        self.debug = debug
        self.RAND_ID = RAND_ID
        self.SOPInstanceUID=SC_SOPInstanceUID
        self.StudyInstanceUID=STUDY_INSTANCE_ID
        self.FrameOfReferenceUID=FOD_REF_ID

    def process(self):

        # Create a list of sorted JPEG files
        jpeg_files = os.listdir(self.extraction_path)
        jpeg_files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))
        
        # Create a sorted list of DICOM files
        dcm_sorted = os.listdir(self.dcm_path)
        dcm_sorted.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        print("Number of JPEG files %i" % len(jpeg_files))
        print("Number of DICOM files %i" % len(dcm_sorted))

        def ensure_even(stream):
            # Very important for some viewers
            if len(stream) % 2:
                return stream + b"\x00"
            return stream

        ''' # Dev notes
        I think we want to iterate through all of the images in order
        and create a single encoded pixel array for the whole JPEG images 
        series
        '''

        ''' # Dev notes updated 11-30-2022
        Creating a Multi-Frame Full Color Secondary Capture image and sending 
        to a PACS system is a nightmare, and is not widely supported apparently. 
        Best bet will be create multiple JPEG dicom files with similar header information
        "FIP Frame Increment Pointer"

        SOPClassUID will probably be: Secondary Capture Image Storage
        https://dicomlibrary.com/dicom/sop/

        TransferSyntaxUID will probably be: ExplicitVRLittleEndian (if encapsulated)
        https://pydicom.github.io/pydicom/stable/reference/uid.html

        Reference Doc:
        https://stackoverflow.com/questions/20116825/what-is-multiframe-image-in-dicom

        '''

        ''' # Dev Notes 12-01-2022
            Continuing to get errored sessions for the JPEG files.
            Dicoms will not upload to PACS. 
            XNAT tells me "Premature end of File"
            ITK snaps says vector too long. 
        '''

        # Iteratively rotate through the JPEG images

        # Define the image array
        jpeg_sample = Image.open(os.path.join(self.extraction_path,jpeg_files[0]))
        jpeg_sample.load()
        jpeg_sample = np.asarray(jpeg_sample, dtype="int8")
        print("Sample Array Size %s" % str(jpeg_sample.shape))

        MediaSOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
        SeriesInstanceUID = pydicom.uid.generate_uid()
        instance_number=0

        for jpeg_file in jpeg_files:

            i=str(instance_number)
            save_name="IMG{}".format(
                ('0' * (5 - len(i)) + i)
            )

            jpeg_file = os.path.join(self.extraction_path, jpeg_file)

            # Hopefully, identify the source DICOM image for the JPEG file
            reference_dicom = dcm_sorted[instance_number]
            reference_dicom = os.path.join(self.dcm_path, reference_dicom)

            ds = pydicom.dcmread(reference_dicom)
            
            meta = ds.file_meta
            meta.TransferSyntaxUID = pydicom.uid.JPEGExtended
        
            # Read the JPEG file
            img = Image.open(jpeg_file)
            img.load()
            
            if img.format == "PNG" or img.format =="BMP" or img.format == "RGBA":
                print("Converting image to true RGB")
                img = img.covert('RGB')

            suffix = '.dcm'
            filename_little_endian = tempfile.NamedTemporaryFile(suffix=suffix).name

            # Create new data with META
            new_ds = pydicom.dataset.FileDataset(
                filename_little_endian, {}, file_meta=meta,  preamble=b"\0" * 128)

            # Create Pixel Data by using converted to bytes
            new_ds.Rows = img.height
            new_ds.Columns = img.width
            new_ds.NumberOfFrames = 1
            #new_ds.AcquisitionNumber=1

            if self.debug:
                print("Instance number: {}. Rows: {} Columns: {}, Number of Frames: {}".format(
                    instance_number, new_ds.Rows, new_ds.Columns, new_ds.NumberOfFrames))

            output = BytesIO()
            img.save(output, format="JPEG")
            new_ds.PixelData = pydicom.encaps.encapsulate([ensure_even(output.getvalue())])
            output.close()
            new_ds['PixelData'].is_undefined_length = True 

            new_ds.file_meta.MediaSOPClassUID = MediaSOPClassUID
            new_ds.SOPClassUID = MediaSOPClassUID

            new_ds.file_meta.MediaSOPInstanceUID = pydicom.uid.generate_uid(prefix='1.2.840.10008.5.1.4.1.1.7.')
            new_ds.SOPInstanceUID = ds.file_meta.MediaSOPInstanceUID 

            new_ds.StudyInstanceUID = self.StudyInstanceUID

            new_ds.SeriesInstanceUID = SeriesInstanceUID
            
            new_ds.FrameOfReferenceUID = self.FrameOfReferenceUID

            new_ds.Modality = 'SC'
            new_ds.ContentDate = str(datetime.date.today()).replace('-','')
            new_ds.AcquisitionDate = str(datetime.date.today()).replace('-','')
            new_ds.SeriesDate = str(datetime.date.today()).replace('-','')
            new_ds.StudyDate = str(datetime.date.today()).replace('-','')

            dt = datetime.time(0, 1, 1, 10)
            new_ds.StudyTime = dt.strftime('%H%M%S.%f')

            dt = datetime.time(0, 1, 2, 10)
            new_ds.SeriesTime = dt.strftime('%H%M%S.%f')

            dt = datetime.time(0, 1, 4, 10)
            new_ds.ContentTime = dt.strftime('%H%M%S.%f')

            dt = datetime.time(0, 1, 6, 10)
            new_ds.AcquisitionTime = dt.strftime('%H%M%S.%f')

            new_ds.SecondaryCaptureDeviceManufacturer = 'RIIPL NETRT'
            new_ds.is_little_endian = True
            new_ds.is_implicit_VR = False
        
            new_ds.SeriesDescription = "Unapproved Treatment Plan JPEG"
            new_ds.StudyDescription = "Unapproved Treatment Plan JPEG"
            
            new_ds.BitsStored = 8
            new_ds.BitsAllocated = 8
            new_ds.SamplesPerPixel = 3
            new_ds.HighBit = 7
            new_ds.ImageType = ["DERIVED","PRIMARY", "AXIAL"]
            new_ds.PixelRepresentation = 0
            new_ds.PlanarConfiguration = 1
            new_ds.SeriesNumber = 1
            new_ds.PhotometricInterpretation = 'YBR_FULL_422'
            new_ds.ColorSpace = 'SRGB'
            new_ds.InstanceNumber = instance_number

            new_ds.StudyID = "RTPlanShare"

            new_ds.ImageOrientationPatient = ds.ImageOrientationPatient
            new_ds.SliceThickness = ds.SliceThickness
            new_ds.ImagePositionPatient = ds.ImagePositionPatient
            new_ds.PatientPosition = ds.PatientPosition
            new_ds.SliceLocation = ds.SliceLocation
            new_ds.PixelSpacing = ds.PixelSpacing
            new_ds.ReferringPhysicianName = ds.ReferringPhysicianName 

            new_ds.PatientBirthDate = str(datetime.date.today()).replace('-','') # delete DOB
            new_ds.PatientSex= 'O'# delete Gender

            # Case DEBUG but no CODE
            if self.debug:
                remove_these_tags = ['AccessionNumber']
                for tag in remove_these_tags:
                    if tag in new_ds:
                        delattr(new_ds, tag)

                new_ds.PatientID = str("RT_" + self.RAND_ID).upper()
                new_ds.PatientName = str("RT_" + self.RAND_ID).upper()
            
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
                                if tag in new_ds:
                                    delattr(new_ds, tag)

                            new_ds.PatientID = sid
                            new_ds.PatientName = sid

            '''
            Let's just <b>ALWAYS</b> remove Accssion Number from the dicom files 
            to force the PACS to treat it as an exception. We can change this later
            if there is every a reason for sending research data to a Clinical PACs.
            (ie, if we get a RESEARCH VNA that clinicials can use)
            '''
            # Remove Accession Number to cause PACS error
            remove_these_tags = ['AccessionNumber']
            for tag in remove_these_tags:
                if tag in new_ds:
                    delattr(new_ds, tag)

            new_ds.AccessionNumber=None

            #pydicom.dataset.validate_file_meta(new_ds.file_meta, enforce_standard=True)

            print(" - Creating %s" % f"{save_name}.dcm")
            instance_number +=1
            new_ds.save_as(f"{self.jpg_folder_path}/{save_name}.dcm", write_like_original=False)
            del ds
            del new_ds

