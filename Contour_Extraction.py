import os
import numpy as np
import pydicom
from rt_utils import RTStructBuilder
import matplotlib.pyplot as plt
import os.path
from scipy.ndimage.measurements import center_of_mass
from math import isnan
from pydicom.pixel_data_handlers.util import apply_modality_lut
#import cv2
import PIL.Image
import re

plt.switch_backend('agg')

class ContourExtraction:

    def __init__(self, dcm_path, struct_path):
        self.dcm_path = dcm_path
        self.struct_path = struct_path

    '''
    get the three-dimensional outline of a numpy pixel array with dimensions (512, 512, 139)
    '''
    def process(self):

        # Load dicom files
        RTstruct= RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        # get a list of structures
        structures = RTstruct.get_roi_names()
        
        # Remove known problematic ROIs
        if '*Skull' in structures:
            structures.remove('*Skull')

        # Evaluate ROIs
        print("Evaluating Segmentations")
        for struct in structures:
            try:
                dummy = RTstruct.get_roi_mask_by_name(struct)
            except Exception:
                print("WARNING: %s is an unreadable ROI." % struct)
                structures.remove(struct)
                continue
            t=np.where(dummy > 0, 1, 0)
            print(" >>> Structure: {} is sized at {}\n".format(
                struct,
                (dummy > 0 ).sum()
            ))

        # get a list of all structural files
        files = os.listdir(self.dcm_path)
        files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))
        
        print("file count: {}".format(len(files)))

        # skip files with no SliceLocation (eg scout views)
        slices = []
        skipcount = 0

        for f in files:
            fds = pydicom.dcmread(os.path.join(self.dcm_path,f))
            if hasattr(fds, 'SliceLocation'):
                slices.append(fds)
            else:
                skipcount = skipcount + 1

        print("skipped, no SliceLocation: {}".format(skipcount))

        # pixel aspects, assuming all slices are the same
        ps = slices[0].PixelSpacing
        ss = slices[0].SliceThickness

        # create 3D array
        img_shape = list(slices[0].pixel_array.shape)
        img_shape.append(len(slices))
        anat_array = np.zeros(img_shape)

        # fill 3D array with the images from the files
        for i, s in enumerate(slices):
            img2d = s.pixel_array
            img2d = apply_modality_lut(img2d, s)
            anat_array[:, :, i] = img2d

        # Build Struct masks
        # increment make value to make NOT binary to rep colors in JPEG image.
        mask_dict = {}
        i=100
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

        for struct in structures:
            try:
                # load by name
                mask_3d = RTstruct.get_roi_mask_by_name(struct)

            except KeyError:
                print("ERROR: unable to locate mask: %s" % struct)
                continue

            except Exception as err:
                print("OTHER ERROR: {}".format(err))
                break

            # Assign mask value
            mask_dict[struct]= np.where(mask_3d > 0, i, 0)
            i+=100

        for x in range(0, anat_array.shape[2]):
            
            slice_str = str(x)
            
            # add padding 0s dynamically
            if len(slice_str) < 5: 
               slice_str  = '0' * (5 - len(slice_str)) + slice_str 
                  
            plt.figure(figsize=(10, 10))

            plt.axis('off')

            # Get a 2D slice of the anat_array
            plt.imshow(anat_array[:, :, x], cmap=plt.cm.gray)

            # Get a corresponding 2D slice of each mask
            mask_image_dict = {}
            
            # For reference, now the "structs" from before are "masks"
            for mask in mask_dict.keys():
                mask_array = mask_dict[mask]
                mask_slice = mask_array[:, :, x]
                mask_slice = np.ma.masked_where(mask_slice==0, mask_slice)
                
                center_of_mask = center_of_mass(np.where(mask_slice > 0, 1, 0))
                if isnan(center_of_mask[0]):
                    continue
                else:
                    txt = plt.text(center_of_mask[1], center_of_mask[0], mask)
                    txt.set_color("white")

                mask_image_dict[mask] = plt.imshow(mask_slice, alpha=0.6, cmap=plt.cm.prism)

            output_directory = self.dcm_path.replace('DCM', 'Extraction')

            if os.path.isdir(output_directory) == False:
                os.mkdir(output_directory)
            
            print(" - Creating JPEG image %s" % f"{str(slice_str)}.jpeg")

            try:
                plt.savefig(f'{output_directory}/{str(slice_str)}.jpeg', bbox_inches='tight', pad_inches=0)
            except:
                print(' - Unable to create image %s' % f'{str(slice_str)}.jpeg')
                
            plt.close()