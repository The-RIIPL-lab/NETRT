import os
import pydicom
import numpy as np
import cv2
import copy


class Add_Burn_In:
    def __init__(self, directory):
        self.directory = directory
        self.dicom_filepaths = self.get_dicom_filepaths()

    def get_dicom_filepaths(self):
        dicom_filepaths = []

        for root, dirs, files in os.walk(self.directory):
            if "Structure" in dirs:
                dirs.remove("Structure")  # exclude the "structure" subfolder

            for file in files:
                if file.endswith(".dcm"):
                    filepath = os.path.join(root, file)
                    try:
                        pydicom.dcmread(filepath)  # check if it's a valid DICOM file
                        dicom_filepaths.append(filepath)
                    except pydicom.errors.InvalidDicomError:
                        pass  # ignore non-DICOM files

        return dicom_filepaths

    def apply_watermark(self, input_filename):
        # Load the DICOM image
        dcm = pydicom.dcmread(input_filename, force=True)
    
        # Check if the DICOM file contains pixel data
        if dcm.get("PixelData") is None:
            print(f"WARNING: File {input_filename} does not contain valid pixel data. Skipping...")
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
        for dicom_file in self.dicom_filepaths:
            self.apply_watermark(dicom_file)