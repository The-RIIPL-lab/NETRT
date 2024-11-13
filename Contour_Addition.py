import os
import numpy as np
import pydicom
from rt_utils import RTStructBuilder
from pydicom.pixel_data_handlers.numpy_handler import pack_bits
import datetime
import re
import logging

# Import the logging configuration
from logging_config import setup_logging

# Ensure the logger is set up
setup_logging()

# Create a logger instance for this script
logger = logging.getLogger('Contour_Addition')

class ContourAddition:

    def __init__(self, dcm_path, struct_path, deidentify=True, study_instance_id='', ct_sopinstanceuid='', fod_ref_id='', rand_id=''):
        self.dcm_path = dcm_path
        self.struct_path = struct_path
        self.deidentify = deidentify
        self.rand_id = rand_id
        self.sop_instance_uid = ct_sopinstanceuid
        self.study_instance_uid = study_instance_id
        self.frame_of_reference_uid = fod_ref_id

    def add_overlay_layers(self, ds, output_directory, mask_dict, slice_number):
        slice_str = f"{slice_number:05d}"
        hex_start = 0x6000

        MediaSOPClassUID = '1.2.840.10008.5.1.4.1.1.2'  # Defined for the whole scan series

        ds.file_meta.MediaSOPClassUID = MediaSOPClassUID
        ds.SOPClassUID = MediaSOPClassUID

        ds.StudyDescription = "Unapproved Treatment Plan CT w Mask"
        ds.SeriesDescription = "Unapproved Treatment Plan CT w Mask"

        ds.SeriesNumber = 1
        ds.Modality = 'CT'
        current_date = str(datetime.date.today()).replace('-', '')

        ds.ContentDate = current_date
        ds.AcquisitionDate = current_date
        ds.SeriesDate = current_date
        ds.StudyDate = current_date

        for mask in mask_dict.keys():
            mask_array = mask_dict[mask]
            mask_slice = mask_array[:, :, slice_number - 1]
            mask_slice = np.ma.masked_where(mask_slice == 0, mask_slice)
            packed_bytes = pack_bits(mask_slice)

            ds.add_new(pydicom.tag.Tag(hex_start, 0x0040), 'CS', 'R')
            ds.add_new(pydicom.tag.Tag(hex_start, 0x0050), 'SS', [1, 1])
            ds.add_new(pydicom.tag.Tag(hex_start, 0x0100), 'US', 8)
            ds.add_new(pydicom.tag.Tag(hex_start, 0x0102), 'US', 0)
            ds.add_new(pydicom.tag.Tag(hex_start, 0x022), 'LO', mask)
            ds.add_new(pydicom.tag.Tag(hex_start, 0x1500), 'LO', mask)
            ds.add_new(pydicom.tag.Tag(hex_start, 0x3000), 'OW', packed_bytes)
            ds.add_new(pydicom.tag.Tag(hex_start, 0x0010), 'US', mask_slice.shape[0])
            ds.add_new(pydicom.tag.Tag(hex_start, 0x0011), 'US', mask_slice.shape[1])

            ds.StudyID = "RTPlanShare"

            dt = datetime.time(0, 1, 1, 10)
            ds.StudyTime = dt.strftime('%H%M%S.%f')

            dt = datetime.time(0, 1, 3, 30)
            ds.SeriesTime = dt.strftime('%H%M%S.%f')

            dt = datetime.time(0, 1, 7, 30)
            ds.ContentTime = dt.strftime('%H%M%S.%f')

            dt = datetime.time(0, 1, 9, 30)
            ds.AcquisitionTime = dt.strftime('%H%M%S.%f')

            if (0x0040, 0x0275) in ds:
                del ds[0x0040, 0x0275]
            if (0x0010, 0x1000) in ds:
                del ds[0x0010, 0x1000]  # delete retired IDs

            if (0x0008, 0x0012) in ds:
                del ds[0x0008, 0x0012]  # delete instance creation dates
                del ds[0x0008, 0x0013]  # delete Instance cretaion times

            if self.deidentify:
                remove_these_tags = ['AccessionNumber', 'MRN']
                for tag in remove_these_tags:
                    if hasattr(ds, tag):
                        delattr(ds, tag)

                ds.PatientID = f"RT_{self.rand_id}".upper()
                ds.PatientName = f"RT_{self.rand_id}".upper()
                ds.PatientAge = '0'
                ds.PatientBirthDate = current_date  # delete DOB
                ds.PatientSex = 'O'  # delete Gender

            hex_start += 2
            out_fn = os.path.join(output_directory, f"CT-with-overlay-{slice_str}.dcm")

            ds.save_as(out_fn)

    def process(self):
        # Load DICOM files and RT structure
        rt_struct = RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        # Get a list of structures
        structures = rt_struct.get_roi_names()

        # Remove known problematic ROIs
        if '*Skull' in structures:
            structures.remove('*Skull')
        
        if 'iso' in structures:
            structures.remove('iso')

        # Evaluate ROIs and print their sizes
        logger.info("Evaluating Segmentations")
        for struct in structures:
            try:
                mask_3d = rt_struct.get_roi_mask_by_name(struct)
            except Exception as e:
                logger.warning(f"WARNING: {struct} is an unreadable ROI. Error: {e}")
                structures.remove(struct)
                continue

            size = np.sum(mask_3d > 0)
            logger.info(f"Structure: {struct} is sized at {size}")

        logger.info(f"These structures exist in RT:\n{structures}")

        # Build struct masks
        mask_dict = {}
        for struct in structures:
            try:
                mask_3d = rt_struct.get_roi_mask_by_name(struct)
            except KeyError:
                logger.error(f"ERROR: unable to locate mask: {struct}")
                continue
            except Exception as err:
                logger.error(f"OTHER ERROR: {err}")
                continue

            # Assign binary mask value for each structure and flip along the z-axis
            mask_dict[struct] = np.where(mask_3d > 0, 1, 0).astype(np.uint8)
            mask_dict[struct] = np.flip(mask_dict[struct], axis=2)

        # Get a list of all DICOM files in the directory
        files = sorted(os.listdir(self.dcm_path), key=lambda x: int(re.findall(r'\d+', x)[-1]))

        # Create output directory if it doesn't exist
        output_directory = os.path.join(self.dcm_path, 'Addition')
        os.makedirs(output_directory, exist_ok=True)

        skip_count = 0
        for counter, f in enumerate(files, start=1):
            try:
                fds = pydicom.dcmread(os.path.join(self.dcm_path, f))
            except Exception as e:
                logger.error(f"Error reading file {f}: {e}")
                continue

            if hasattr(fds, 'SliceLocation'):
                self.add_overlay_layers(fds, output_directory, mask_dict, counter)
            else:
                skip_count += 1
                logger.warning(f"Skipped file {f}, no SliceLocation")

        logger.info(f"Skipped files with no SliceLocation: {skip_count}")