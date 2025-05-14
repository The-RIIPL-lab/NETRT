# netrt_core/contour_processor.py

import os
import numpy as np
import pydicom
from rt_utils import RTStructBuilder
from pydicom.pixels import pack_bits
import datetime
import logging

# Assuming DicomAnonymizer is refactored and available if needed, or its logic integrated/called from study_processor
# from .dicom_anonymizer import DicomAnonymizer # Example if it becomes part of the core package

logger = logging.getLogger(__name__)

class ContourProcessor:
    def __init__(self, config):
        self.config = config
        self.processing_config = config.get("processing", {})
        self.anonymization_config = config.get("anonymization", {})
        # self.anonymizer = DicomAnonymizer(self.anonymization_config) # If anonymizer is used here

    def _generate_uid(self, prefix=None):
        """Generates a DICOM UID, optionally with a prefix."""
        # In future, a registered organizational root UID prefix should be used here.
        # For now, pydicom's default generation is used.
        if prefix:
            return pydicom.uid.generate_uid(prefix=prefix)
        return pydicom.uid.generate_uid()

    def process_study_for_contours(
        self, 
        dcm_path, 
        struct_path, 
        output_addition_path,
        original_study_uid, # Preserve original StudyInstanceUID
        original_for_uid    # Preserve original FrameOfReferenceUID
    ):
        """Processes DICOM images and RTStruct to add merged contours as overlays."""
        try:
            rtstruct_builder = RTStructBuilder.create_from(
                dicom_series_path=dcm_path,
                rt_struct_path=struct_path
            )
        except Exception as e:
            logger.error(f"Failed to load RTStruct or DICOM series: {e}", exc_info=True)
            return False

        all_roi_names = rtstruct_builder.get_roi_names()
        logger.info(f"Available ROIs: {all_roi_names}")

        ignore_keywords = [kw.lower() for kw in self.processing_config.get("ignore_contour_names_containing", ["skull"])]
        
        rois_to_process = []
        ignored_rois = []
        for roi_name in all_roi_names:
            if any(keyword in roi_name.lower() for keyword in ignore_keywords):
                ignored_rois.append(roi_name)
            else:
                rois_to_process.append(roi_name)
        
        if ignored_rois:
            logger.info(f"Ignored ROIs based on keywords {ignore_keywords}: {ignored_rois}")

        if not rois_to_process:
            logger.warning("No ROIs left to process after filtering. No overlay will be generated.")
            return True # Successfully processed by doing nothing with contours

        if len(rois_to_process) > 1:
            logger.warning(f"Multiple non-ignored ROIs found: {rois_to_process}. They will be merged into a single binary mask.")
        else:
            logger.info(f"Processing ROI: {rois_to_process[0]}")

        # Combine masks
        combined_mask_3d = None
        for i, roi_name in enumerate(rois_to_process):
            try:
                roi_mask_3d = rtstruct_builder.get_roi_mask_by_name(roi_name)
                if combined_mask_3d is None:
                    combined_mask_3d = roi_mask_3d
                else:
                    combined_mask_3d = np.logical_or(combined_mask_3d, roi_mask_3d)
            except Exception as e:
                logger.error(f"Error getting or combining mask for ROI 	{roi_name}	: {e}", exc_info=True)
                # Decide if we should skip this ROI or fail the study
                continue # Skip this problematic ROI
        
        if combined_mask_3d is None:
            logger.error("Failed to generate any mask data from the selected ROIs.")
            return False

        combined_mask_3d = np.where(combined_mask_3d > 0, 1, 0) # Ensure binary
        # Original code had a flip: combined_mask_3d = np.flip(combined_mask_3d, axis=2)
        # This flip needs to be verified if it's necessary for correct orientation.
        # Assuming it is for now, based on original code.
        # TODO: Verify necessity of this flip. It depends on how rt-utils orients masks vs pydicom pixel data.
        combined_mask_3d = np.flip(combined_mask_3d, axis=2)

        # --- Create new DICOM series with this merged overlay ---
        os.makedirs(output_addition_path, exist_ok=True)
        source_dicom_files = sorted(
            [os.path.join(dcm_path, f) for f in os.listdir(dcm_path) if f.endswith(".dcm")],
            key=lambda x: pydicom.dcmread(x, stop_before_pixels=True).InstanceNumber
        )

        new_series_instance_uid = self._generate_uid() # UID for the new overlay series
        default_series_desc = self.processing_config.get("default_series_description", "Processed DicomRT with Overlay")
        default_series_num = self.processing_config.get("default_series_number", 9901)

        for i, dcm_file_path in enumerate(source_dicom_files):
            try:
                ds = pydicom.dcmread(dcm_file_path)
                
                # Preserve original study and patient identifiers by default
                # Anonymization should be a separate step if enabled
                ds.StudyInstanceUID = original_study_uid
                ds.FrameOfReferenceUID = original_for_uid

                # New Series and SOP Instance UIDs
                ds.SeriesInstanceUID = new_series_instance_uid
                ds.SOPInstanceUID = self._generate_uid(prefix=ds.SOPClassUID.replace("Storage","").replace(".","_X_")) # Generate new SOPInstanceUID, prefix can be based on SOPClass
                ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
                ds.file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID # Use pydicom's UID
                ds.file_meta.ImplementationVersionName = "NETRT_CORE_0.3"

                # Update Series information
                ds.SeriesDescription = default_series_desc
                ds.SeriesNumber = default_series_num
                # ds.Modality should be preserved from original, SOPClassUID too.

                # Update Dates/Times for derived instance
                now = datetime.datetime.now()
                ds.SeriesDate = now.strftime("%Y%m%d")
                ds.SeriesTime = now.strftime("%H%M%S.%f")[:16]
                ds.ContentDate = now.strftime("%Y%m%d")
                ds.ContentTime = now.strftime("%H%M%S.%f")[:16]
                ds.InstanceCreationDate = now.strftime("%Y%m%d")
                ds.InstanceCreationTime = now.strftime("%H%M%S.%f")[:16]
                # AcquisitionDate/Time should typically be preserved from original

                # Add the single merged overlay
                slice_index = i # Assuming files are sorted correctly by slice
                if slice_index < combined_mask_3d.shape[2]:
                    mask_slice = combined_mask_3d[:, :, slice_index]
                    if np.any(mask_slice):
                        packed_bytes = pack_bits(mask_slice)
                        # Overlay group 0x6000 (can choose any even group from 0x6000-0x601E)
                        # Ensure existing overlays are removed if any, or use a different group
                        # For simplicity, assuming we add to 0x6000 and it's fresh.
                        overlay_group_hex = 0x6000 
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0010), "US", ds.Rows) # Overlay Rows
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0011), "US", ds.Columns) # Overlay Columns
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0015), "IS", "1") # Number of Frames in Overlay
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0022), "LO", "Merged ROI Overlay") # Overlay Description
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0040), "CS", "R")  # Overlay Type (Region of Interest)
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0050), "SS", [1, 1]) # Overlay Origin (top left pixel)
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0100), "US", 1)  # Overlay Bits Allocated (1 for binary)
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0102), "US", 0)  # Overlay Bit Position (0 for binary)
                        # ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x0200), 'US', 0) # Overlay Activation Layer - Optional
                        ds.add_new(pydicom.tag.Tag(overlay_group_hex, 0x3000), "OW", packed_bytes) # Overlay Data
                    else:
                        logger.debug(f"Slice {slice_index} has no overlay data after merging.")
                else:
                    logger.warning(f"Slice index {slice_index} out of bounds for combined mask shape {combined_mask_3d.shape}")

                # Anonymization (if enabled and configured to run at this stage)
                # This should ideally be handled by the study_processor after all DICOM modifications are done.
                # if self.anonymizer and self.anonymization_config.get("enabled", False):
                #     ds = self.anonymizer.anonymize_dataset(ds) # Anonymizer needs to be adapted

                output_filename = os.path.join(output_addition_path, f"overlay_{ds.SOPInstanceUID}.dcm")
                ds.save_as(output_filename, enforce_file_format=True)
                logger.info(f"Saved DICOM with merged overlay: {output_filename}")

            except Exception as e:
                logger.error(f"Error processing or saving DICOM slice {dcm_file_path}: {e}", exc_info=True)
                # Potentially skip this slice or fail the entire study processing
                return False # Indicate failure for the study
        
        return True # Indicate success for the study

# Example usage (for testing - will be integrated into the main application)
if __name__ == "__main__":
    # This requires a more complex setup with sample DICOMs and RTStruct
    # and a proper configuration dictionary.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    logger.info("ContourProcessor module ready. Run with integration tests or a full application setup.")

    # Minimal config for testing structure
    test_config = {
        "processing": {
            "ignore_contour_names_containing": ["skull", "patient outline"],
            "default_series_description": "Test Overlay Series",
            "default_series_number": 9910
        },
        "anonymization": {"enabled": False} # Assuming anonymization is handled elsewhere
    }
    # cp = ContourProcessor(test_config)
    # To test cp.process_study_for_contours(...), you would need:
    # - dcm_path: path to a directory with DICOM image slices
    # - struct_path: path to an RTSTRUCT file corresponding to the images
    # - output_addition_path: path to an output directory
    # - original_study_uid: UID string
    # - original_for_uid: UID string
    # Example: 
    # cp.process_study_for_contours("./sample_data/dcm_series", "./sample_data/rtstruct.dcm", "./output/addition", "1.2.3", "1.2.3.1")

