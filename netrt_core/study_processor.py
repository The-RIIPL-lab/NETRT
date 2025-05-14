import os
import logging
import pydicom
import random
import time
from DicomAnonymizer import DicomAnonymizer
import Contour_Addition
import Add_Burn_In
import Send_Files
import Segmentations

# Standard logger for general module events
logger = logging.getLogger(__name__)
# Specific logger for transaction events, configured in logging_setup.py
transaction_logger = logging.getLogger("transaction")

class StudyProcessor:
    """Orchestrates the processing pipeline for a received DICOM study."""

    def __init__(self, config, file_system_manager):
        """Initialize the StudyProcessor.

        Args:
            config (dict): Application configuration.
            file_system_manager (FileSystemManager): Instance of FileSystemManager.
        """
        self.config = config
        self.fsm = file_system_manager
        # Initialize anonymizer with its specific configuration section
        anonymization_settings = self.config.get("anonymization", {})
        if anonymization_settings.get("enabled", False):
            self.anonymizer = DicomAnonymizer(anonymization_settings)
        else:
            self.anonymizer = None
            logger.info("Anonymization is disabled in StudyProcessor.")

    def _handle_contour_logic(self, rtstruct_builder, dcm_path):
        """Handles the new contour logic: ignore skull, merge others.
        This is a placeholder and needs to be integrated with Contour_Addition.py logic.
        The current Contour_Addition.py already has some logic for structure iteration.
        We need to modify it or pre-process the structure list.
        """
        structures = rtstruct_builder.get_roi_names()
        logger.info(f"Original ROI names: {structures}")
        
        final_rois_to_process = []
        skull_contours_found = []
        ignore_names = self.config.get("processing", {}).get("ignore_contour_names_containing", ["skull"])

        for struct_name in structures:
            should_ignore = False
            for ignore_term in ignore_names:
                if ignore_term.lower() in struct_name.lower():
                    should_ignore = True
                    break
            if should_ignore:
                skull_contours_found.append(struct_name)
                logger.info(f"Identified contour to ignore: {struct_name} (based on terms: {ignore_names}).")
            else:
                final_rois_to_process.append(struct_name)
        
        if len(skull_contours_found) > 0:
            logger.info(f"Contours ignored: {skull_contours_found}")

        if not final_rois_to_process:
            logger.warning(f"No non-ignored contours found in {rtstruct_builder.rt_struct_path}. Nothing to merge or process.")
            return None # Or an empty mask

        if len(final_rois_to_process) > 1:
            logger.warning(f"Multiple non-ignored contours found: {final_rois_to_process}. They will be merged into a single binary mask by Contour_Addition.")
        
        return final_rois_to_process

    def process_study(self, study_instance_uid):
        """Processes a single DICOM study located in the working directory."""
        study_path = self.fsm.get_study_path(study_instance_uid)
        processing_start_time = time.time()
        transaction_logger.info(f"PROCESSING_START StudyUID: {study_instance_uid}, Path: {study_path}")
        logger.info(f"Starting processing for study: {study_path} (UID: {study_instance_uid})")

        dcm_path = os.path.join(study_path, "DCM")
        struct_dir_path = os.path.join(study_path, "Structure")
        addition_path = os.path.join(study_path, "Addition") # Output for contour addition
        seg_path = os.path.join(study_path, "Segmentations") # Output for DICOM SEG
        os.makedirs(addition_path, exist_ok=True)
        os.makedirs(seg_path, exist_ok=True)

        if not os.path.isdir(dcm_path) or not os.listdir(dcm_path):
            logger.error(f"DCM directory is missing or empty for study {study_instance_uid}")
            self.fsm.quarantine_study(study_instance_uid, "Missing or empty DCM directory")
            transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, Reason: Missing or empty DCM directory")
            return False

        struct_file_path = None
        if os.path.isdir(struct_dir_path) and os.listdir(struct_dir_path):
            struct_files = [os.path.join(struct_dir_path, f) for f in os.listdir(struct_dir_path) if f.lower().endswith(".dcm")]
            if struct_files:
                struct_file_path = struct_files[0]
                if len(struct_files) > 1:
                    logger.warning(f"Multiple RTSTRUCT files found in {struct_dir_path}. Using the first one: {struct_file_path}")
            else:
                logger.warning(f"No .dcm files found in Structure directory for study {study_instance_uid}.")
        else:
            logger.warning(f"Structure directory is missing or empty for study {study_instance_uid}. Proceeding without contour processing.")

        try:
            # --- Configuration items --- 
            base_anon_flag = self.config.get("anonymization", {}).get("enabled", False)
            full_anon_flag = self.config.get("anonymization", {}).get("full_anonymization_enabled", False)

            if base_anon_flag and full_anon_flag:
                deidentify_config_flag = True
            else:
                deidentify_config_flag = False

            deidentify_for_old_modules = self.anonymizer is not None and deidentify_config_flag
            new_study_instance_id_for_series = pydicom.uid.generate_uid()
            new_fod_ref_id = pydicom.uid.generate_uid()
            
            rand_id_for_old_modules = ""
            if deidentify_for_old_modules:
                letters = "abcdefghijklmnopqrstuvwxyz"
                rand_id_for_old_modules = "".join(random.choice(letters) for _ in range(8)).upper()
                logger.info(f"De-identification enabled for legacy modules. RAND_ID: {rand_id_for_old_modules}")

            # --- Anonymize original files (if enabled) ---
            # This step should ideally happen *before* any processing that uses DICOM tags from original files
            # if the anonymization modifies those tags. The DicomAnonymizer class is now config-driven.
            if self.anonymizer:
                logger.info(f"Applying configured anonymization to files in {dcm_path} for study {study_instance_uid}")
                for root, _, files in os.walk(dcm_path):
                    for filename in files:
                        if filename.lower().endswith(".dcm"):
                            filepath = os.path.join(root, filename)
                            if self.config.get("anonymization", {}).get("full_anonymization_enabled", False) and self.config.get("anonymization", {}).get("enabled", True):
                                try:
                                    ds = pydicom.dcmread(filepath)
                                    self.anonymizer.anonymize(ds)
                                    ds.save_as(filepath) # Save changes
                                    logger.debug(f"Anonymized and saved: {filepath}")
                                except Exception as e:
                                    logger.error(f"Failed to anonymize file {filepath}: {e}", exc_info=True)
                if struct_file_path:
                    if self.config.get("anonymization", {}).get("full_anonymization_enabled", False) and self.config.get("anonymization", {}).get("enabled", True):
                        try:
                            ds_struct = pydicom.dcmread(struct_file_path)
                            self.anonymizer.anonymize(ds_struct)
                            ds_struct.save_as(struct_file_path)
                            logger.info(f"Anonymized and saved RTSTRUCT: {struct_file_path}")
                        except Exception as e:
                            logger.error(f"Failed to anonymize RTSTRUCT file {struct_file_path}: {e}", exc_info=True)

            # --- Contour Addition ---
            if struct_file_path:
                logger.info(f"Processing contours from {struct_file_path} for images in {dcm_path}")

                #contour_series_desc = self.config.get("processing", {}).get("default_series_description", "Processed DicomRT with Overlay")
                #contour_series_num = self.config.get("processing", {}).get("default_series_number_overlay", 9901)

                try:
                    contour_adder = Contour_Addition.ContourAddition(
                        dcm_path=dcm_path, 
                        struct_path=struct_file_path, 
                        deidentify=deidentify_for_old_modules, 
                        STUDY_INSTANCE_ID=new_study_instance_id_for_series, 
                        CT_SOPInstanceUID=pydicom.uid.generate_uid(), 
                        FOD_REF_ID=new_fod_ref_id, 
                        RAND_ID=rand_id_for_old_modules,
                    )
                    contour_adder.process()
                    logger.info("Contour addition process completed.")
                except Exception as e:
                    logger.error(f"Contour addition failed for study {study_instance_uid}: {e}", exc_info=True)
                    self.fsm.quarantine_study(study_instance_uid, f"Contour addition error: {str(e)}")
                    transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, Reason: Contour addition error: {str(e)}")
                    return False

                # --- Add Burn In --- (operates on the output of ContourAddition)
                if self.config.get("processing", {}).get("add_burn_in_disclaimer", True):
                    burn_in_text = self.config.get("processing", {}).get("burn_in_text", "RESEARCH IMAGE - Not for diagnostic purpose")
                    burn_in_adder = Add_Burn_In.Add_Burn_In(addition_path, burn_in_text)
                    try:
                        burn_in_adder.apply_watermarks()
                        logger.info(f"Burn-in disclaimer added with text: '{burn_in_text}'")
                    except Exception as e:
                        logger.error(f"Apply watermark failed for study {study_instance_uid}: {e}")
                        self.fsm.quarantine_study(study_instance_uid, str(e))
                        return False
                else:
                    logger.info("Burn-in disclaimer is disabled by configuration.")
            else:
                logger.info("No RTSTRUCT file found or specified, skipping contour addition and burn-in.")

            # --- DICOM SEG Creation (if enabled and not de-identifying for old modules) ---
            if self.config.get("feature_flags", {}).get("enable_segmentation_export", False) and struct_file_path:
                if not deidentify_for_old_modules: # Original condition
                    logger.info("Creating DICOM SEG objects.")
                    seg_series_num = self.config.get("processing", {}).get("default_series_number_seg", 9902)
                    # Segmentation class also needs config for UIDs, output path (seg_path), SeriesNumber, Description.
                    try:
                        segmentation_creator = Segmentations.Segmentations(
                            dcm_path=dcm_path, 
                            struct_path=struct_file_path, 
                            seg_path=seg_path, 
                            DEIDENTIFY=deidentify_for_old_modules, 
                            STUDY_INSTANCE_ID=new_study_instance_id_for_series,
                        )
                        segmentation_creator.process()
                        logger.info("DICOM SEG creation completed.")
                    except Exception as e:
                        logger.error(f"DICOM SEG creation failed for study {study_instance_uid}: {e}", exc_info=True)
                else:
                    logger.info("DICOM SEG creation skipped due to de-identification flag for legacy modules.")
            else:
                logger.info("DICOM SEG creation is disabled by feature flag or no RTSTRUCT file.")
            
            # --- Send Files --- 
            dest_ip = self.config.get("dicom_destination", {}).get("ip", "127.0.0.1")
            dest_port = self.config.get("dicom_destination", {}).get("port", 11112)
            dest_aet = self.config.get("dicom_destination", {}).get("ae_title", "DEST_AET")

            files_sent_overlay = False
            if os.path.exists(addition_path) and os.listdir(addition_path):
                transaction_logger.info(f"SENDING_START SeriesType: OVERLAY, StudyUID: {study_instance_uid}, DestAET: {dest_aet}, DestIP: {dest_ip}, DestPort: {dest_port}")
                logger.info(f"Sending processed files with overlays from {addition_path} to {dest_aet}@{dest_ip}:{dest_port}")
                try:
                    sender_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aet)
                    sender_overlay.send_dicom_folder()
                    files_sent_overlay = True
                    transaction_logger.info(f"SENDING_SUCCESS SeriesType: OVERLAY, StudyUID: {study_instance_uid}, DestAET: {dest_aet}")
                except Exception as e:
                    logger.error(f"Failed to send OVERLAY series for study {study_instance_uid} to {dest_aet}: {e}", exc_info=True)
                    transaction_logger.error(f"SENDING_FAILED SeriesType: OVERLAY, StudyUID: {study_instance_uid}, DestAET: {dest_aet}, Reason: {str(e)}")
            else:
                logger.info(f"No files in {addition_path} to send (overlay series).")

            files_sent_seg = False
            if self.config.get("feature_flags", {}).get("enable_segmentation_export", False) and os.path.exists(seg_path) and os.listdir(seg_path):
                # Original logic: if not deidentify_for_old_modules. This check should be aligned with SEG creation.
                if not deidentify_for_old_modules: 
                    transaction_logger.info(f"SENDING_START SeriesType: SEG, StudyUID: {study_instance_uid}, DestAET: {dest_aet}, DestIP: {dest_ip}, DestPort: {dest_port}")
                    logger.info(f"Sending DICOM SEG files from {seg_path} to {dest_aet}@{dest_ip}:{dest_port}")
                    try:
                        sender_seg = Send_Files.SendFiles(seg_path, dest_ip, dest_port, dest_aet)
                        sender_seg.send_dicom_folder()
                        files_sent_seg = True
                        transaction_logger.info(f"SENDING_SUCCESS SeriesType: SEG, StudyUID: {study_instance_uid}, DestAET: {dest_aet}")
                    except Exception as e:
                        logger.error(f"Failed to send SEG series for study {study_instance_uid} to {dest_aet}: {e}", exc_info=True)
                        transaction_logger.error(f"SENDING_FAILED SeriesType: SEG, StudyUID: {study_instance_uid}, DestAET: {dest_aet}, Reason: {str(e)}")
                else:
                    logger.info(f"SEG series sending skipped due to de-identification flag for legacy modules.")
            else:
                logger.info(f"No files in {seg_path} to send (SEG series), or SEG export is disabled.")

            processing_duration = time.time() - processing_start_time
            transaction_logger.info(f"PROCESSING_SUCCESS StudyUID: {study_instance_uid}, DurationSec: {processing_duration:.2f}, OverlaySent: {files_sent_overlay}, SegSent: {files_sent_seg}")
            logger.info(f"Processing for study {study_instance_uid} completed successfully in {processing_duration:.2f} seconds.")
            self.fsm.cleanup_study_directory(study_instance_uid)
            return True

        except Exception as e:
            processing_duration = time.time() - processing_start_time
            logger.error(f"Error processing study {study_instance_uid} after {processing_duration:.2f} seconds: {e}", exc_info=True)
            self.fsm.quarantine_study(study_instance_uid, str(e))
            transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, DurationSec: {processing_duration:.2f}, Reason: {str(e)}")
            return False