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
#from skimage.measure import find_contours
import re

plt.switch_backend('agg')

class ContourAddition:

    def __init__(self, dcm_path, struct_path, debug=False, RAND_ID='', RAND_UID=''):
        self.dcm_path = dcm_path
        self.struct_path = struct_path
        self.debug  = debug
        self.RAND_ID = RAND_ID
        self.RAND_UID = RAND_UID

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
            #try:
            # load by name
            mask_3d = RTstruct.get_roi_mask_by_name(struct)

            # Assign mask value for each different mask
            mask_dict[struct] = np.where(mask_3d > 0, 1, 0)

            #except Exception as err:
            #    pass
                #print(err)

        # get a list of all structural files
        files = os.listdir(self.dcm_path)

        # Create Overlay layer function
        output_directory = os.path.abspath(self.dcm_path).replace('DCM', 'Addition')

        if os.path.isdir(output_directory) == False:
            os.mkdir(output_directory)

        def add_overlay_layers(ds, mask_dict, match):
            slice_number = int(match) - 1
            
            slice_str = str(slice_number)
            
            # add padding 0s dynamically
            if len(slice_str) < 5:
               slice_str  = '0' * (5 - len(slice_str)) + slice_str

            if self.debug:
                print("DEBUG: building layer for slice: ", slice_number)

            hex_start = 0x6000

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
                ds.SeriesDescription = "Unapproved Treatment Plan CT w Mask"
                ds.StudyDescription = "Unapproved Treatment Plan CT w Mask"
                ds.SeriesNumber = ds.SeriesNumber + 100

                ds.add_new(pydicom.tag.Tag(hex_start, 0x0040), 'CS', 'R')
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0050), 'SS', [1, 1])
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0100), 'US', 8)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0102), 'US', 0)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x022), 'LO', mask)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x1500), 'LO', mask)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x3000), 'OW', packed_bytes)
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0010), 'US', mask_slice.shape[0])
                ds.add_new(pydicom.tag.Tag(hex_start, 0x0011), 'US', mask_slice.shape[1])

                if self.debug: # Debug Mode anonymizes everything crudely
                    remove_these_tags = ['AccessionNumber']
                    for tag in remove_these_tags:
                        if tag in ds:
                            delattr(ds, tag)

                    ds.PatientID = str("RT_TEST-" + self.RAND_ID).upper()
                    ds.PatientName = str("RT_TEST-" + self.RAND_ID).upper()
                    ds.StudyInstanceUID = self.RAND_UID

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

        for f in files:

            fds = pydicom.dcmread(os.path.join(self.dcm_path, f))
            
            number = f.split('.')[-2]
            if int(number) > 300:
                number = fds.ImagePositionPatient[2]
                print(" >> File Number %i" % number)
            
            if hasattr(fds, 'SliceLocation'):
                # Add the overlay layer
                # fds = add_overlay_layers(fds, mask_dict, number)
                slices.append(fds)
            else:
                skipcount = skipcount + 1

            fds = add_overlay_layers(fds, mask_dict, number)

        print("skipped, no SliceLocation: {}".format(skipcount))
