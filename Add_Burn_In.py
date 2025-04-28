from pathlib import Path
import pydicom
import numpy as np
import cv2
import logging

logger = logging.getLogger('NETRT')
import copy


class Add_Burn_In:
    """
    Class for adding watermarks to DICOM images.
    
    This class processes DICOM images by adding a "RESEARCH IMAGE" watermark
    to indicate that they are not for diagnostic purposes.
    """
    
    def __init__(self, directory):
        """
        Initialize the Add_Burn_In processor.
        
        Args:
            directory (str or Path): Path to the directory containing DICOM files
        """
        self.directory = directory
        self.dicom_filepaths = self.get_dicom_filepaths()

    def get_dicom_filepaths(self):
        """
        Recursively find all DICOM files (*.dcm) under the directory,
        excluding any files in a 'Structure' subdirectory.
        
        Returns:
            list: List of Path objects pointing to DICOM files
        """
        dicom_filepaths = []
        base_dir = Path(self.directory)
        for p in base_dir.rglob('*.dcm'):
            # Skip files in 'Structure' folder
            if 'Structure' in p.parts:
                continue
            try:
                # Verify valid DICOM
                pydicom.dcmread(str(p))
                dicom_filepaths.append(p)
            except pydicom.errors.InvalidDicomError:
                continue
        return dicom_filepaths

    def apply_watermark(self, input_filename):
        """
        Add a watermark to a single DICOM image.
        
        This method adds a "RESEARCH IMAGE" watermark to the DICOM image,
        which indicates that the image is not for diagnostic purposes.
        
        Args:
            input_filename (str or Path): Path to the DICOM file
            
        Returns:
            None
        """
        # Load the DICOM image
        dcm = pydicom.dcmread(input_filename, force=True)
    
        # Check if the DICOM file contains pixel data
        if dcm.get("PixelData") is None:
            logger.warning(f"File {input_filename} does not contain valid pixel data. Skipping...")
            return
    
        # Convert the DICOM image to a numpy array
        img = dcm.pixel_array
    
        # Determine the range of pixel values in the image
        min_val = np.min(img)
        max_val = np.max(img)
    
        # Rescale the pixel values
        img_rescaled = (img - min_val) / (max_val - min_val) * 255
    
        # Cast the rescaled pixel values to the uint8 data type
        img_copy = img_rescaled.astype(np.uint8)
    
        # Define the watermark text
        watermark_text = "RESEARCH IMAGE - Not for diagnostic purpose"
    
        # Define the font, font scale, color, and thickness of the text
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        color = (255, 255, 255)
        thickness = 1
    
        # Determine the size of the text
        text_size = cv2.getTextSize(watermark_text, font, font_scale, thickness)[0]
    
        # Define the position of the watermark in the bottom-right corner of the image
        x = img_copy.shape[1] - text_size[0] - 10
        y = img_copy.shape[0] - text_size[1] - 10
    
        # Define the rectangle that will surround the watermark text
        rect_coords = ((x, y + 2), (x + text_size[0], y - text_size[1] - 2))
    
        # Draw the watermark rectangle onto the image
        cv2.rectangle(img_copy, rect_coords[0], rect_coords[1], color, cv2.FILLED)
    
        # Draw the watermark text onto the image
        cv2.putText(img_copy, watermark_text, (x, y), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
    
        # Create a deep copy of the original DICOM dataset
        new_dcm = copy.deepcopy(dcm)
    
        # Convert the uint8 pixel data back to the original range
        img_copy = (img_copy / 255.0) * (max_val - min_val) + min_val
    
        # For unsigned integers
        new_pixel_data = img_copy.astype(np.uint16)
    
        # Convert the pixel data to bytes
        new_pixel_data = new_pixel_data.tobytes()
    
        # Assign the new pixel data to the new DICOM dataset
        new_dcm.PixelData = new_pixel_data
    
        # Write the new DICOM dataset to a file
        pydicom.dcmwrite(input_filename, new_dcm, enforce_file_format=True)
        
    def apply_watermarks(self):
        """
        Apply watermarks to all DICOM files in the directory.
        
        This method applies the "RESEARCH IMAGE" watermark to all DICOM files
        found in the directory specified during initialization.
        
        Returns:
            None
        """
        for dicom_file in self.dicom_filepaths:
            self.apply_watermark(dicom_file)