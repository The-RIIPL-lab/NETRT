import os
import logging
import re
import datetime
import numpy as np
import pydicom
from pydicom import dcmread, uid
from pydicom.tag import Tag
from pydicom.pixels import pack_bits
from rt_utils import RTStructBuilder

logger = logging.getLogger(__name__)

class ContourProcessor:
    """Processes RTSTRUCT files to create a new series with contour overlays."""

    def __init__(self, config):
        """
        Initializes the ContourProcessor.

        Args:
            config (dict): The application configuration dictionary.
        """
        self.processing_config = config.get("processing", {})

    def run(self, dcm_path, struct_path, output_path):
        """
        Executes the full contour processing pipeline.

        Args:
            dcm_path (str): Path to the directory with original DICOM images.
            struct_path (str): Path to the RTSTRUCT file.
            output_path (str): Path to the directory to save the new series.
        
        Returns:
            bool: True if processing was successful, False otherwise.
        """
        try:
            os.makedirs(output_path, exist_ok=True)
            rt_struct = RTStructBuilder.create_from(
                dicom_series_path=dcm_path,
                rt_struct_path=struct_path
            )
            mask = self._create_merged_mask(rt_struct)
            self._create_overlay_series(dcm_path, mask, output_path)
            return True
        except Exception as e:
            logger.error(f"Failed during contour processing: {e}", exc_info=True)
            return False

    def _create_merged_mask(self, rt_struct):
        """Merges specified ROI contours into a single binary 3D mask."""
        all_rois = rt_struct.get_roi_names()
        ignore_terms = self.processing_config.get("ignore_contour_names_containing", ["skull"])
        rois_to_process = [r for r in all_rois if not any(term.lower() in r.lower() for term in ignore_terms)]
        
        logger.info(f"Original ROIs found: {all_rois}")
        logger.info(f"Ignoring contours containing: {ignore_terms}")
        logger.info(f"ROIs to be merged into mask: {rois_to_process}")

        if not rois_to_process:
            raise ValueError("No contours left to process after filtering.")

        # Initialize a blank mask with the shape of the 3D image volume
        base_mask = rt_struct.get_roi_mask_by_name(rois_to_process[0])
        merged_mask = np.zeros_like(base_mask, dtype=bool)

        for roi in rois_to_process:
            try:
                mask_3d = rt_struct.get_roi_mask_by_name(roi)
                merged_mask = np.logical_or(merged_mask, mask_3d)
            except Exception as e:
                logger.warning(f"Could not get mask for ROI '{roi}'. Skipping. Error: {e}")
        
        return np.flip(merged_mask, axis=2) # Flip mask to match slice order

    def _sort_dicom_files(self, dcm_path):
        """Sorts DICOM files in a directory by InstanceNumber."""
        files = [f for f in os.listdir(dcm_path) if f.lower().endswith('.dcm')]
        
        def get_sort_key(filename):
            try:
                return int(re.findall(r'\d+', filename)[-1])
            except (IndexError, ValueError):
                try:
                    full_path = os.path.join(dcm_path, filename)
                    dcm = dcmread(full_path, stop_before_pixels=True)
                    return dcm.InstanceNumber
                except Exception as e:
                    logger.warning(f"Could not determine sort key for {filename}: {e}. It will be sorted last.")
                    return float('inf')

        files.sort(key=get_sort_key)
        return files

    def _create_overlay_series(self, dcm_path, mask_3d, output_path):
        """Creates a new DICOM series with the provided mask as an overlay."""
        sorted_files = self._sort_dicom_files(dcm_path)
        new_series_uid = uid.generate_uid()
        
        for i, filename in enumerate(sorted_files):
            ds = dcmread(os.path.join(dcm_path, filename))
            if not hasattr(ds, 'SliceLocation'):
                logger.debug(f"Skipping file {filename} as it has no SliceLocation.")
                continue

            new_ds = self._add_overlay_to_slice(ds, mask_3d[:, :, i], new_series_uid)
            output_filename = os.path.join(output_path, f"OVERLAY-{filename}")
            new_ds.save_as(output_filename, enforce_file_format=True)
        logger.info(f"Successfully created {len(sorted_files)} files in new overlay series.")

    def _add_overlay_to_slice(self, ds, mask_slice, series_uid):
        """Adds a single overlay plane to a pydicom dataset."""
        # These tags are modified for the new series
        ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.2' # CT Image Storage
        ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.2'
        ds.SOPInstanceUID = uid.generate_uid()
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.SeriesInstanceUID = series_uid

        # Set new series attributes from config
        ds.SeriesNumber = self.processing_config.get("overlay_series_number", 98)
        ds.SeriesDescription = self.processing_config.get("overlay_series_description", "Contour Overlay")
        ds.StudyID = self.processing_config.get("overlay_study_id", "RTPlanShare")

        # Update date and time to current
        now = datetime.datetime.now()
        ds.ContentDate = now.strftime('%Y%m%d')
        ds.ContentTime = now.strftime('%H%M%S.%f')
        ds.SeriesDate = now.strftime('%Y%m%d')
        ds.SeriesTime = now.strftime('%H%M%S.%f')

        # Add overlay data
        overlay_group = 0x6000
        ds.add_new(Tag(overlay_group, 0x0010), 'US', ds.Rows)
        ds.add_new(Tag(overlay_group, 0x0011), 'US', ds.Columns)
        ds.add_new(Tag(overlay_group, 0x0015), 'IS', '1') # Number of Frames in Overlay
        ds.add_new(Tag(overlay_group, 0x0040), 'CS', 'R') # ROI Area
        ds.add_new(Tag(overlay_group, 0x0050), 'SS', [ds.Rows // 2, ds.Columns // 2]) # Overlay Origin
        ds.add_new(Tag(overlay_group, 0x0100), 'US', 1) # Bits Allocated
        ds.add_new(Tag(overlay_group, 0x0102), 'US', 0) # Bit Position
        ds.add_new(Tag(overlay_group, 0x3000), 'OW', pack_bits(mask_slice))

        return ds
