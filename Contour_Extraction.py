import os
import numpy as np
import pydicom
from rt_utils import RTStructBuilder
import matplotlib.pyplot as plt
import re
from scipy.ndimage.measurements import center_of_mass

plt.switch_backend('agg')

def apply_modality_lut(pixel_array, ds):
    """
    Apply modality LUT to the pixel array.
    
    Parameters:
        pixel_array (numpy.ndarray): The original pixel data from the DICOM file.
        ds (pydicom.dataset.Dataset): The DICOM dataset containing the image metadata.
    
    Returns:
        numpy.ndarray: The transformed pixel data.
    """
    # Check if Rescale Slope and Rescale Intercept are present in the dataset
    rescale_slope = getattr(ds, 'RescaleSlope', 1.0)
    rescale_intercept = getattr(ds, 'RescaleIntercept', 0.0)

    # Apply the LUT transformation
    return pixel_array * rescale_slope + rescale_intercept

class ContourExtraction:
    def __init__(self, dcm_path, struct_path):
        self.dcm_path = dcm_path
        self.struct_path = struct_path

    def process(self):
        # Load dicom files and RTStruct
        rtstruct = RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        structures = rtstruct.get_roi_names()
        
        if '*Skull' in structures:
            structures.remove('*Skull')

        # Evaluate ROIs and remove unreadable ones
        readable_structures = []
        for struct in structures:
            try:
                roi_mask = rtstruct.get_roi_mask_by_name(struct)
                non_zero_pixels = (roi_mask > 0).sum()
                print(f"Structure: {struct} is sized at {non_zero_pixels}")
                readable_structures.append((struct, roi_mask))
            except Exception as e:
                print(f"WARNING: {struct} is an unreadable ROI. Error: {e}")

        # Get sorted list of DICOM files
        files = [f for f in os.listdir(self.dcm_path) if f.endswith('.dcm')]
        files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        print(f"Total files: {len(files)}")

        # Filter out slices without SliceLocation
        slices = []
        skip_count = 0

        for f in files:
            ds = pydicom.dcmread(os.path.join(self.dcm_path, f))
            if hasattr(ds, 'SliceLocation'):
                slices.append(ds)
            else:
                skip_count += 1

        print(f"Skipped files without SliceLocation: {skip_count}")

        # Get pixel spacing and slice thickness
        ps = slices[0].PixelSpacing
        ss = slices[0].SliceThickness

        # Create 3D array
        img_shape = list(slices[0].pixel_array.shape)
        img_shape.append(len(slices))
        anat_array = np.zeros(img_shape)

        # Fill 3D array with images from files
        for i, s in enumerate(slices):
            img2d = apply_modality_lut(s.pixel_array, s)
            anat_array[:, :, i] = img2d

        # Build structure masks
        mask_dict = {}
        value_increment = 100
        for struct, roi_mask in readable_structures:
            mask_dict[struct] = np.where(roi_mask > 0, value_increment, 0)
            value_increment += 100

        output_directory = self.dcm_path.replace('DCM', 'Extraction')
        if not os.path.isdir(output_directory):
            os.mkdir(output_directory)

        # Create JPEG images
        for x in range(anat_array.shape[2]):
            slice_str = f"{x:05d}"

            plt.figure(figsize=(10, 10))
            plt.axis('off')

            plt.imshow(anat_array[:, :, x], cmap=plt.cm.gray)

            mask_image_dict = {}
            for mask_name, mask in mask_dict.items():
                mask_slice = np.ma.masked_where(mask[:, :, x] == 0, mask[:, :, x])
                
                center_of_mask = center_of_mass(np.where(mask_slice > 0, 1, 0))
                if not any(np.isnan(center_of_mask)):
                    txt = plt.text(center_of_mask[1], center_of_mask[0], mask_name)
                    txt.set_color("white")

                plt.imshow(mask_slice, alpha=0.6, cmap=plt.cm.prism)

            output_path = os.path.join(output_directory, f"{slice_str}.jpeg")
            try:
                plt.savefig(output_path, bbox_inches='tight', pad_inches=0)
                print(f"Created JPEG image {output_path}")
            except Exception as e:
                print(f"Unable to create image {output_path}. Error: {e}")

            plt.close()