# netrt_core/study_processor.py

import os
import logging
import pydicom
import random # For RAND_ID if de-identifying, though this should be managed better
import time # For timing events

# Import existing application modules - these might need adaptation later
# For now, assume they are in the parent directory or Python path is set up
from DicomAnonymizer import DicomAnonymizer # Corrected import based on file name
import Contour_Addition  # Assuming Contour_Addition.py is accessible
import Add_Burn_In       # Assuming Add_Burn_In.py is accessible
import Send_Files        # Assuming Send_Files.py is accessible
import Segmentations     # Assuming Segmentations.py is accessible

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
            deidentify_config_flag = self.config.get("anonymization", {}).get("enabled", False)
            # If anonymizer is None, deidentify is effectively False for the old modules
            deidentify_for_old_modules = self.anonymizer is not None and deidentify_config_flag

            # UIDs for new series - these should be robustly generated.
            # The original script generated these per-study. This might need review for true DICOM compliance if these are meant to be globally unique across app runs.
            # For now, keeping the pattern of generating them per processing run.
            new_study_instance_id_for_series = pydicom.uid.generate_uid() # Used as Study UID for *new* series by old modules
            new_fod_ref_id = pydicom.uid.generate_uid()
            # CT_SOPInstanceUID_prefix = "1.2.840.10008.5.1.4.1.1.2." # Example for CT, old modules generate full UIDs
            
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
                            try:
                                ds = pydicom.dcmread(filepath)
                                self.anonymizer.anonymize_dataset(ds) # Anonymizes in-place
                                ds.save_as(filepath) # Save changes
                                logger.debug(f"Anonymized and saved: {filepath}")
                            except Exception as e:
                                logger.error(f"Failed to anonymize file {filepath}: {e}", exc_info=True)
                                # Decide if this is a critical failure for the whole study
                if struct_file_path:
                    try:
                        ds_struct = pydicom.dcmread(struct_file_path)
                        self.anonymizer.anonymize_dataset(ds_struct)
                        ds_struct.save_as(struct_file_path)
                        logger.info(f"Anonymized and saved RTSTRUCT: {struct_file_path}")
                    except Exception as e:
                        logger.error(f"Failed to anonymize RTSTRUCT file {struct_file_path}: {e}", exc_info=True)

            # --- Contour Addition (incorporating new logic) ---
            if struct_file_path:
                logger.info(f"Processing contours from {struct_file_path} for images in {dcm_path}")
                # Contour_Addition needs refactoring to use config for SeriesNumber, Description, and the new contour logic.
                # It also needs to handle the output directory properly.
                # The `ignore_contour_names_containing` and merging logic should be part of Contour_Addition or a pre-step.
                # For now, we assume Contour_Addition.py might need to be adapted to use self.config directly or passed specific params.
                contour_series_desc = self.config.get("processing", {}).get("default_series_description", "Processed DicomRT with Overlay")
                contour_series_num = self.config.get("processing", {}).get("default_series_number_overlay", 9901)

                try:
                    # This is a simplification. Contour_Addition needs to be significantly refactored.
                    # It should take the list of ROIs to process from _handle_contour_logic if that pre-filters.
                    # Or, Contour_Addition itself should implement the filtering based on config.
                    contour_adder = Contour_Addition.ContourAddition(
                        dcm_path=dcm_path, 
                        struct_path=struct_file_path, 
                        deidentify=deidentify_for_old_modules, # Legacy flag
                        STUDY_INSTANCE_ID=new_study_instance_id_for_series, 
                        CT_SOPInstanceUID=pydicom.uid.generate_uid(), # Placeholder, needs better UID mgmt
                        FOD_REF_ID=new_fod_ref_id, 
                        RAND_ID=rand_id_for_old_modules,
                        # TODO: Pass series_description, series_number from config
                        # TODO: Pass ignore_contour_names from config
                        # TODO: Ensure output is to `addition_path`
                    )
                    contour_adder.process() # This is a call to the old module
                    logger.info("Contour addition process completed.")
                except Exception as e:
                    logger.error(f"Contour addition failed for study {study_instance_uid}: {e}", exc_info=True)
                    self.fsm.quarantine_study(study_instance_uid, f"Contour addition error: {str(e)}")
                    transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, Reason: Contour addition error: {str(e)}")
                    return False

                # --- Add Burn In --- (operates on the output of ContourAddition)
                if self.config.get("processing", {}).get("add_burn_in_disclaimer", True):
                    burn_in_text = self.config.get("processing", {}).get("burn_in_text", "FOR RESEARCH USE ONLY")
                    burn_in_adder = Add_Burn_In.Add_Burn_In(addition_path, burn_in_text) # Pass text from config
                    try:
                        burn_in_adder.apply_watermarks()
                        logger.info("Burn-in disclaimer added.")
                    except Exception as e:
                        logger.error(f"Apply watermark failed for study {study_instance_uid}: {e}", exc_info=True)
                        # This might not be a fatal error for the whole study, depending on requirements.
                else:
                    logger.info("Burn-in disclaimer is disabled by configuration.")
            else:
                logger.info("No RTSTRUCT file found or specified, skipping contour addition and burn-in.")

            # --- DICOM SEG Creation (if enabled and not de-identifying for old modules) ---
            # The `deidentify_for_old_modules` flag is a bit confusing here. SEG creation might have its own anonymization needs.
            # For now, using the old logic.
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
                            STUDY_INSTANCE_ID=new_study_instance_id_for_series
                            # TODO: Pass SeriesNumber, SeriesDescription from config
                        )
                        segmentation_creator.process()
                        logger.info("DICOM SEG creation completed.")
                    except Exception as e:
                        logger.error(f"DICOM SEG creation failed for study {study_instance_uid}: {e}", exc_info=True)
                        # This might not be a fatal error for the whole study.
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

# Example usage (for testing - will be integrated into the main application)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    # Dummy config and FSM for testing StudyProcessor
    # This requires the dependent modules (Contour_Addition etc.) to be in PYTHONPATH
    # and a valid DICOM dataset in the specified structure.
    # This test is complex to set up standalone and is better tested via integration tests.
    
    from netrt_core.config_loader import DEFAULT_CONFIG # Use default config for structure
    test_config = DEFAULT_CONFIG
    test_config["directories"]["working"] = "/tmp/CNCT_working_sp_test"
    test_config["directories"]["logs"] = "/tmp/CNCT_logs_sp_test"
    test_config["anonymization"]["enabled"] = False # Test without anonymization first
    test_config["feature_flags"]["enable_segmentation_export"] = True

    # Setup logging for the test
    from netrt_core.logging_setup import setup_logging, TRANSACTION_LOGGER_NAME
    setup_logging(test_config)

    class MockFSM:
        def __init__(self, config):
            self.working_dir = os.path.expanduser(config.get("directories", {}).get("working", "~/CNCT_working"))
            self.quarantine_dir = os.path.join(self.working_dir, config.get("directories", {}).get("quarantine_subdir", "quarantine"))
            os.makedirs(self.working_dir, exist_ok=True)
            os.makedirs(self.quarantine_dir, exist_ok=True)
            logger.info(f"MockFSM initialized. Working: {self.working_dir}")

        def get_study_path(self, study_instance_uid):
            return os.path.join(self.working_dir, f"UID_{study_instance_uid}")

        def quarantine_study(self, study_instance_uid, reason):
            quarantine_path = os.path.join(self.quarantine_dir, f"UID_{study_instance_uid}")
            # shutil.move(self.get_study_path(study_instance_uid), quarantine_path) # If moving
            logger.warning(f"MOCK: Quarantining study {study_instance_uid} to {quarantine_path} due to: {reason}")
        
        def cleanup_study_directory(self, study_instance_uid):
            # shutil.rmtree(self.get_study_path(study_instance_uid)) # If cleaning up
            logger.info(f"MOCK: Cleaning up study directory for {study_instance_uid}")

    mock_fsm = MockFSM(test_config)
    processor = StudyProcessor(test_config, mock_fsm)

    logger.info("StudyProcessor initialized for test. To run a specific test case, create data and call process_study.")
    logger.info(f"Test logs will be in {test_config["directories"]["logs"]}")
    logger.info(f"Test working files in {test_config["directories"]["working"]}")

    # Example: Create a dummy study structure for a hypothetical test
    # test_study_uid = "1.2.3.4.5.test"
    # dummy_study_dir = mock_fsm.get_study_path(test_study_uid)
    # dummy_dcm_dir = os.path.join(dummy_study_dir, "DCM")
    # dummy_struct_dir = os.path.join(dummy_study_dir, "Structure")
    # os.makedirs(dummy_dcm_dir, exist_ok=True)
    # os.makedirs(dummy_struct_dir, exist_ok=True)
    # # Create dummy files (these won\u2019t be valid DICOMs, just for path testing)
    # # For a real test, use actual DICOM files.
    # # with open(os.path.join(dummy_dcm_dir, "ct1.dcm"), "w") as f: f.write("dummy ct")
    # # with open(os.path.join(dummy_struct_dir, "rtstruct.dcm"), "w") as f: f.write("dummy rtstruct")
    # 
    # logger.info(f"Attempting to process dummy study: {test_study_uid}. This will likely fail due to dummy data and unrefactored legacy modules.")
    # # processor.process_study(test_study_uid)

