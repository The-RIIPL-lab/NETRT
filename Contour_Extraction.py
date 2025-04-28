from pathlib import Path
import numpy as np
import pydicom
from rt_utils import RTStructBuilder
import matplotlib.pyplot as plt
import re
from scipy.ndimage.measurements import center_of_mass
from logger_module import setup_logger

# Configure plotting backend
plt.switch_backend('agg')

# Get logger
logger = setup_logger()

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
    """
    Class for extracting contours from RT structure sets and creating visualization images.
    
    This class processes DICOM CT/MR images and associated RT structure sets to create
    visualization images with contour overlays.
    """
    
    def __init__(self, dcm_path, struct_path):
        """
        Initialize the ContourExtraction with paths to DICOM images and RT structure set.
        
        Args:
            dcm_path (str or Path): Path to the directory containing DICOM image files
            struct_path (str or Path): Path to the RT structure set file
        """
        self.dcm_path = dcm_path
        self.struct_path = struct_path
    
    def _save_slice_as_jpeg(self, slice_index, anat_array, mask_dict, output_directory):
        """
        Save a single slice with contour overlays as a JPEG image.
        
        Args:
            slice_index (int): Index of the slice to save
            anat_array (numpy.ndarray): 3D array of anatomical image data
            mask_dict (dict): Dictionary mapping structure names to mask arrays
            output_directory (Path): Directory to save the output JPEG image
            
        Returns:
            None
        """
        slice_str = f"{slice_index:05d}"
        plt.figure(figsize=(10, 10))
        plt.axis('off')
        plt.imshow(anat_array[:, :, slice_index], cmap=plt.cm.gray)
        for mask_name, mask in mask_dict.items():
            mask_slice = np.ma.masked_where(mask[:, :, slice_index] == 0, mask[:, :, slice_index])
            center = center_of_mass(np.where(mask_slice > 0, 1, 0))
            if not any(np.isnan(center)):
                txt = plt.text(center[1], center[0], mask_name)
                txt.set_color("white")
            plt.imshow(mask_slice, alpha=0.6, cmap=plt.cm.prism)
        output_path = output_directory / f"{slice_str}.jpeg"
        try:
            plt.savefig(output_path, bbox_inches='tight', pad_inches=0)
            logger.info(f"Created JPEG image {output_path}")
        except Exception as e:
            logger.error(f"Unable to create image {output_path}. Error: {e}")
        plt.close()

    def process(self):
        """
        Process the DICOM files and RT structure set to generate visualization images.
        
        This method:
        1. Loads the DICOM files and RT structure set
        2. Extracts contours for each ROI in the structure set
        3. Creates a 3D volume from the DICOM slices
        4. Generates JPEG images for each slice with contour overlays
        
        Returns:
            None
        """
        # Load dicom files and RTStruct
        rtstruct = RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        # Load ROI names and exclude known problematic structures
        structures = [s for s in rtstruct.get_roi_names() if s != '*Skull']

        # Evaluate ROIs and remove unreadable ones
        readable_structures = []
        for struct in structures:
            try:
                roi_mask = rtstruct.get_roi_mask_by_name(struct)
                non_zero_pixels = (roi_mask > 0).sum()
                logger.info(f"Structure: {struct} is sized at {non_zero_pixels}")
                readable_structures.append((struct, roi_mask))
            except Exception as e:
                logger.warning(f"{struct} is an unreadable ROI. Error: {e}")

        # Get sorted list of DICOM files using pathlib
        dcm_dir = Path(self.dcm_path)
        files = sorted(
            [p for p in dcm_dir.iterdir() if p.suffix.lower() == '.dcm'],
            key=lambda p: int(re.findall(r'\d+', p.name)[-1])
        )

        logger.info(f"Total files: {len(files)}")

        # Filter out slices without SliceLocation
        slices = []
        skip_count = 0

        for f in files:
            # f is a pathlib.Path to a DICOM file
            ds = pydicom.dcmread(f)
            if hasattr(ds, 'SliceLocation'):
                slices.append(ds)
            else:
                skip_count += 1

        logger.info(f"Skipped files without SliceLocation: {skip_count}")

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

        # Build output directory path by replacing 'DCM' with 'Extraction'
        output_directory = Path(self.dcm_path).with_name(Path(self.dcm_path).name.replace('DCM', 'Extraction'))
        output_directory.mkdir(exist_ok=True)

        # Create JPEG images
        for x in range(anat_array.shape[2]):
            self._save_slice_as_jpeg(x, anat_array, mask_dict, output_directory)