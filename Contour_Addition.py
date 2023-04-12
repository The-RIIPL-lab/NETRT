# Load necessary libraries
import os
import numpy as np
import pydicom
from rt_utils import RTStructBuilder
import matplotlib.pyplot as plt
from pydicom.pixel_data_handlers.numpy_handler import pack_bits
from pydicom.pixel_data_handlers.util import apply_modality_lut
from scipy.ndimage.measurements import center_of_mass
from math import isnan
import datetime
import re

plt.switch_backend('agg')

class ContourAddition:

    def __init__(self, dcm_path, struct_path, debug=False, STUDY_INSTANCE_ID='', CT_SOPInstanceUID='', FOD_REF_ID='', RAND_ID=''):
        self.dcm_path = dcm_path
        self.struct_path = struct_path
        self.debug  = debug
        self.RAND_ID = RAND_ID
        self.SOPInstanceUID=CT_SOPInstanceUID
        self.StudyInstanceUID=STUDY_INSTANCE_ID
        self.FrameOfReferenceUID=FOD_REF_ID

    def process(self):

        # Load dicom files
        RTstruct= RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        # Provide a list of structures
        structures = RTstruct.get_roi_names()

        # Remove known problematic ROIs
        if '*Skull' in structures:
            structures.remove()

        # Evaluate ROIs
        print("  - Evaluating Segmentations")
        for struct in structures:
            try:
                dummy = RTstruct.get_roi_mask_by_name(struct)
            except Exception:
                print("WARNING: %s is an unreadable ROI." % struct)
                structures.remove(struct)
                continue
            t=np.where(dummy > 0, 1, 0)
            print(" >>> Structure: {} is sized at {}".format(
                struct,
                (dummy > 0 ).sum()
            ))

        print("  - These structures exist in RT:\n", structures)

        # Build Struct masks
        mask_dict = {}

        # overlay layer only supports binary mask. No different colors for each structure
        for struct in structures:
            try:
                # load by name
                mask_3d = RTstruct.get_roi_mask_by_name(struct)

            except KeyError:
                print("ERROR: unable to locate mask: %s" % struct)
                continue

            except Exception as err:
                print("OTHER ERROR: {}".format(err))
                continue

            # Assign mask value for each different mask
            mask_dict[struct] = np.where(mask_3d > 0, 1, 0)

            # flip the mask
            mask_dict[struct] = np.flip(mask_dict[struct], axis=2)
            
        # get a list of all structural files
        files = os.listdir(self.dcm_path)

        # Create Overlay layer function
        output_directory = os.path.abspath(self.dcm_path).replace('DCM', 'Addition')

        if os.path.isdir(output_directory) == False:
            os.mkdir(output_directory)

        def add_overlay_layers(ds, SeriesInstanceUID, mask_dict, match):
            slice_number = int(match) - 1
            slice_str = str(slice_number)
            
            # add padding 0s dynamically
            if len(slice_str) < 5:
               slice_str  = '0' * (5 - len(slice_str)) + slice_str

            if self.debug:
                print("DEBUG: building layer for slice: ", slice_number)

            hex_start = 0x6000

            MediaSOPClassUID = '1.2.840.10008.5.1.4.1.1.2' # defined for the whole scan series

            for mask in mask_dict.keys():
                if self.debug:
                    print(" --- Mask: ", mask)
                mask_array = mask_dict[mask]
                mask_slice = mask_array[:, :, slice_number]
                mask_slice = np.ma.masked_where(mask_slice == 0, mask_slice)

                # pack bytes
                if self.debug:
                    print(" --- Adding new Overlay ROI: ", hex(hex_start))
                    
                packed_bytes = pack_bits(mask_slice)

                # These classes are consistent
                ds.file_meta.MediaSOPClassUID = MediaSOPClassUID
                ds.SOPClassUID = MediaSOPClassUID

                # There change image to image
                ds.file_meta.MediaSOPInstanceUID = pydicom.uid.generate_uid(prefix='1.2.840.10008.5.1.4.1.1.2.')
                ds.SOPInstanceUID = ds.file_meta.MediaSOPInstanceUID 
                
                ds.StudyDescription = "Unapproved Treatment Plan CT w Mask"
                ds.SeriesDescription = "Unapproved Treatment Plan CT w Mask"

                # Consistent within all study/session/scans
                ds.StudyInstanceUID = self.StudyInstanceUID

                # Different for each scan in the series, but same image to image
                ds.SeriesInstanceUID = SeriesInstanceUID

                ds.SeriesNumber = 1
                
                # Consistent within all study/session/scans
                ds.FrameOfReferenceUID = self.FrameOfReferenceUID

                ds.Modality = 'CT'
                ds.ContentDate = str(datetime.date.today()).replace('-','')
                ds.AcquisitionDate = str(datetime.date.today()).replace('-','')
                ds.SeriesDate = str(datetime.date.today()).replace('-','')
                ds.StudyDate = str(datetime.date.today()).replace('-','')

                ds.add_new(pydicom.tag.Tag(hex_start, 0x0040), 'CS', 'R')
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0050), 'SS', [1, 1])
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0100), 'US', 8)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0102), 'US', 0)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x022), 'LO', mask)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x1500), 'LO', mask)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x3000), 'OW', packed_bytes)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0010), 'US', mask_slice.shape[0])
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0011), 'US', mask_slice.shape[1])

                ds.StudyID = "RTPlanShare"

                dt = datetime.time(0, 1, 1, 10)
                ds.StudyTime = dt.strftime('%H%M%S.%f')

                dt = datetime.time(0, 1, 3, 30)
                ds.SeriesTime = dt.strftime('%H%M%S.%f')

                dt = datetime.time(0, 1, 7, 30)
                ds.ContentTime = dt.strftime('%H%M%S.%f')

                dt = datetime.time(0, 1, 9, 30)
                ds.AcquisitionTime = dt.strftime('%H%M%S.%f')

                if (0x0040, 0x0275) in ds:
                    del ds[0x0040, 0x0275]
                if (0x0010, 0x1000) in ds:
                    del ds[0x0010, 0x1000] # delete retired IDs

                if (0x0008, 0x0012) in ds:
                    del ds[0x0008, 0x0012] # delete instance creation dates
                    del ds[0x0008, 0x0013] # delete Instance cretaion times
                
                ds.PatientAge = '0'

                ds.PatientBirthDate = str(datetime.date.today()).replace('-','') # delete DOB
                ds.PatientSex= 'O'# delete Gender

                if self.debug: # Debug Mode anonymizes everything crudely
                    remove_these_tags = ['AccessionNumber']
                    for tag in remove_these_tags:
                        if tag in ds:
                            delattr(ds, tag)

                    ds.PatientID = str("RT_" + self.RAND_ID).upper()
                    ds.PatientName = str("RT_" + self.RAND_ID).upper()

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

                hex_start = hex_start + 2
                out_fn = os.path.join(output_directory, f"CT-with-overlay-{slice_str}.dcm")

                print(" - Create File with Overlay: %s" % f"CT-with-overlay-{slice_str}.dcm")
                ds.save_as(out_fn)
            return ds

        ## FROM PYDICOM EXAMPLE
        # Read the anatomical dicom file
        # skip files with no SliceLocation (eg scout views)
        slices = []
        skipcount = 0
        
        files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))
        print("file count: {}".format(len(files)))

        SeriesInstanceUID = pydicom.uid.generate_uid() # defined for the whole scan series
        
        headers = []
        
        for f in files:
            ds = pydicom.read_file(os.path.join(self.dcm_path, f))
            headers.append((ds[0x0020, 0x0013].value, f))
    
            # sort by header information (image number) and return a list of filenames sorted accordingly 
            files = [f for _, f in sorted(headers)]
            
        counter = 0

        for f in files:
        
            counter = counter + 1

            fds = pydicom.dcmread(os.path.join(self.dcm_path, f))
            number = f.split('.')[-2]
            
            if int(number) > 300:
              number = fds.ImagePositionPatient[2]
              print(" >> File Number %i" % number)
            
            if hasattr(fds, 'SliceLocation'):
                # Add the overlay layer
                # fds = add_overlay_layers(fds, mask_dict, number)
                slices.append(fds)
                fds = add_overlay_layers(fds, SeriesInstanceUID, mask_dict, counter)
            else:
                skipcount = skipcount + 1

        print("skipped, no SliceLocation: {}".format(skipcount))
        
        
