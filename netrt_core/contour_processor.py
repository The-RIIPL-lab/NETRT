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
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import ListedColormap
matplotlib.use('Agg')

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

    def run(self, dcm_path, struct_path, output_path, debug_mode=False, study_uid=None):
        """
        Executes the full contour processing pipeline.
        """
        try:
            os.makedirs(output_path, exist_ok=True)
            rt_struct = RTStructBuilder.create_from(
                dicom_series_path=dcm_path,
                rt_struct_path=struct_path
            )
            mask = self._create_merged_mask(rt_struct)
            self._create_overlay_series(dcm_path, mask, output_path)
            
            debug_dicom_dir = None
            if debug_mode:
                # Create JPG debug images
                self.save_debug_visualization(dcm_path, mask, os.path.dirname(output_path), study_uid or "UNKNOWN")
                # Create DICOM debug series
                debug_dicom_dir = self.create_debug_dicom_series(dcm_path, mask, os.path.dirname(output_path), study_uid or "UNKNOWN")
            
            return True, debug_dicom_dir  # Return debug dir path for sending
        except Exception as e:
            logger.error(f"Failed during contour processing: {e}", exc_info=True)
            return False, None

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
    
    def _create_secondary_capture_dicom(self, original_ds, rgb_array, series_uid, slice_index):
        """Create a Secondary Capture DICOM from RGB image data."""
        import copy
        import datetime
        
        # Create a copy of the original dataset
        new_ds = copy.deepcopy(original_ds)
        
        # Set Secondary Capture SOP Class
        new_ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.7'  # Secondary Capture Image Storage
        new_ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
        
        # Generate new UIDs
        new_ds.SOPInstanceUID = uid.generate_uid()
        new_ds.file_meta.MediaStorageSOPInstanceUID = new_ds.SOPInstanceUID
        new_ds.SeriesInstanceUID = series_uid
        
        # Set series-level attributes
        new_ds.SeriesNumber = self.processing_config.get("debug_series_number", 101)
        new_ds.SeriesDescription = self.processing_config.get("debug_series_description", "DEBUG: Contour Overlay")
        new_ds.Modality = "SC"  # Secondary Capture
        
        # Update dates/times
        now = datetime.datetime.now()
        new_ds.ContentDate = now.strftime('%Y%m%d')
        new_ds.ContentTime = now.strftime('%H%M%S.%f')
        new_ds.SeriesDate = now.strftime('%Y%m%d')
        new_ds.SeriesTime = now.strftime('%H%M%S.%f')
        
        # Set image pixel data
        new_ds.Rows, new_ds.Columns, _ = rgb_array.shape
        new_ds.BitsAllocated = 8
        new_ds.BitsStored = 8
        new_ds.HighBit = 7
        new_ds.SamplesPerPixel = 3  # RGB
        new_ds.PhotometricInterpretation = 'RGB'
        new_ds.PixelRepresentation = 0
        new_ds.PlanarConfiguration = 0  # pixel interleaved (RGBRGBRGB...)
        
        # Convert RGB array to bytes (interleaved)
        new_ds.PixelData = rgb_array.tobytes()
        
        # Update instance number
        new_ds.InstanceNumber = slice_index + 1
        
        # Remove overlay data if present (since we're creating a new visualization)
        overlay_tags = [tag for tag in new_ds.keys() if tag.group == 0x6000]
        for tag in overlay_tags:
            delattr(new_ds, tag)
        
        return new_ds
    
    def save_debug_visualization(self, dcm_path, mask_3d, output_dir, study_uid):
        """Save debug JPG images showing the binary mask overlay on DICOM slices."""
        debug_dir = os.path.join(output_dir, "debug_visualization")
        os.makedirs(debug_dir, exist_ok=True)
        
        sorted_files = self._sort_dicom_files(dcm_path)
        logger.info(f"Creating debug visualization for {len(sorted_files)} slices in {debug_dir}")
        
        for i, filename in enumerate(sorted_files):
            try:
                # Read the original DICOM file
                ds = pydicom.dcmread(os.path.join(dcm_path, filename))
                if not hasattr(ds, 'SliceLocation') or i >= mask_3d.shape[2]:
                    continue
                
                # Get the image data and normalize to 8-bit
                img_data = ds.pixel_array
                img_normalized = ((img_data - img_data.min()) / (img_data.max() - img_data.min()) * 255).astype(np.uint8)
                
                # Get the corresponding mask slice
                mask_slice = mask_3d[:, :, i]
                
                # Create the visualization
                fig, ax = plt.subplots(figsize=(10, 10))
                ax.imshow(img_normalized, cmap='gray', alpha=1.0)
                
                # Overlay the mask as red contours
                if np.any(mask_slice):
                    contours = plt.contour(mask_slice, levels=[0.5], colors='red', linewidths=2)
                    plt.clabel(contours, inline=True, fontsize=8)
                
                ax.set_title(f'Study: {study_uid}\nSlice {i+1}: {filename}\nMask Overlay (Red)')
                ax.axis('off')
                
                # Save as JPG
                jpg_filename = f"slice_{i+1:03d}_{filename.replace('.dcm', '.jpg')}"
                jpg_path = os.path.join(debug_dir, jpg_filename)
                plt.savefig(jpg_path, format='jpg', bbox_inches='tight', dpi=150)
                plt.close()
                
            except Exception as e:
                logger.warning(f"Could not create debug visualization for slice {i}: {e}")
                continue
        
        logger.info(f"Debug visualization complete. Images saved to: {debug_dir}")

    def create_debug_dicom_series(self, dcm_path, mask_3d, output_dir, study_uid):
        """Create a DICOM Secondary Capture series from debug visualizations."""
        debug_dicom_dir = os.path.join(output_dir, "DebugDicom")
        os.makedirs(debug_dicom_dir, exist_ok=True)
        
        sorted_files = self._sort_dicom_files(dcm_path)
        logger.info(f"Creating debug DICOM series for {len(sorted_files)} slices in {debug_dicom_dir}")
        
        # Use non-interactive backend
        new_series_uid = uid.generate_uid()
        
        for i, filename in enumerate(sorted_files):
            try:
                ds = pydicom.dcmread(os.path.join(dcm_path, filename))
                if not hasattr(ds, 'SliceLocation') or i >= mask_3d.shape[2]:
                    continue
                
                # Create the visualization with matplotlib (high quality)
                img_data = ds.pixel_array
                img_normalized = ((img_data - img_data.min()) / (img_data.max() - img_data.min()) * 255).astype(np.uint8)
                mask_slice = mask_3d[:, :, i]
                
                # Create figure with exact pixel dimensions for 1:1 mapping
                dpi = 100
                fig_width = img_data.shape[1] / dpi
                fig_height = img_data.shape[0] / dpi
                
                fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
                ax.imshow(img_normalized, cmap='gray', alpha=1.0)
                
                if np.any(mask_slice):
                    # High quality matplotlib contours
                    contours = ax.contour(mask_slice, levels=[0.5], colors='red', linewidths=1, alpha=0.6)
                
                ax.axis('off')
                fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
                
                # Robust method to get RGB array - works across matplotlib versions
                from io import BytesIO
                buf = BytesIO()
                fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0)
                buf.seek(0)
                
                # Read back as RGB array using PIL (more reliable than canvas methods)
                from PIL import Image
                pil_img = Image.open(buf)
                rgb_array = np.array(pil_img.convert('RGB'))
                
                plt.close(fig)  # Important: close the figure to free memory
                buf.close()
                
                # Create new DICOM dataset
                new_ds = self._create_secondary_capture_dicom(ds, rgb_array, new_series_uid, i)
                
                # Save the DICOM file
                output_filename = os.path.join(debug_dicom_dir, f"DEBUG-{filename}")
                new_ds.save_as(output_filename, enforce_file_format=True)
                
            except Exception as e:
                logger.warning(f"Could not create debug DICOM for slice {i}: {e}")
                continue
        
        logger.info(f"Debug DICOM series created in: {debug_dicom_dir}")
        return debug_dicom_dir