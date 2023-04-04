import pydicom
import numpy as np
import cv2
import os

import pydicom.pixel_data_handlers.numpy_handler  # use numpy_handler for pixel data


def get_dicom_filepaths(folder):
    dicom_filepaths = []
    
    for root, dirs, files in os.walk(folder):
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
    

def apply_watermark(input_filename):

    # Load the DICOM image
    dcm = pydicom.dcmread(input_filename)
    
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
    
    # Create an empty DICOM dataset with the same metadata as the original DICOM
    new_dcm = pydicom.dataset.Dataset()
    new_dcm.file_meta = dcm.file_meta
    new_dcm.PatientID = dcm.PatientID
    new_dcm.ContentDate = dcm.ContentDate
    new_dcm.ContentTime = dcm.ContentTime
    new_dcm.StudyInstanceUID = dcm.StudyInstanceUID
    new_dcm.SeriesInstanceUID = dcm.SeriesInstanceUID
    new_dcm.SOPClassUID = dcm.SOPClassUID
    new_dcm.SOPInstanceUID = dcm.SOPInstanceUID
    new_dcm.Modality = dcm.Modality
    new_dcm.Rows = dcm.Rows
    new_dcm.Columns = dcm.Columns
    new_dcm.PixelSpacing = dcm.PixelSpacing
    new_dcm.BitsAllocated = dcm.BitsAllocated
    new_dcm.BitsStored = dcm.BitsStored
    new_dcm.HighBit = dcm.HighBit
    new_dcm.PixelRepresentation = dcm.PixelRepresentation
    new_dcm.file_meta.TransferSyntaxUID = dcm.file_meta.TransferSyntaxUID
    
    # For unsigned integers
    new_pixel_data = img_copy.astype(np.uint16)
    
    # Convert the pixel data to bytes
    new_pixel_data = new_pixel_data.tobytes()
    
    # Assign the new pixel data to the new DICOM dataset
    new_dcm.PixelData = new_pixel_data
    
    # Write the new DICOM dataset to a file
    pydicom.dcmwrite(input_filename, new_dcm)
    
 
folder = '/home/jeremy/NETRT/Accession_NOCODE/'
   
dicom_filepaths = get_dicom_filepaths(folder)

for dicom_file in dicom_filepaths:
    apply_watermark(dicom_file)
    
