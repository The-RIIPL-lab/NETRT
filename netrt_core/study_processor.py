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
    """Orchestrates the processing pipeline for a received DICOM study.
    
    This class is responsible for coordinating the entire processing workflow for
    DICOM studies, including:
    1. Anonymization of DICOM data
    2. Processing of RTSTRUCT contours
    3. Addition of overlays to DICOM images
    4. Generation of DICOM SEG objects
    5. Adding burn-in text disclaimers
    6. Sending processed files to destination DICOM systems
    
    The processing workflow is configurable through various configuration settings
    that control which features are enabled and how they operate.
    
    Attributes:
        config: Application configuration dictionary
        fsm: FileSystemManager instance for file operations
        anonymizer: DicomAnonymizer instance for anonymizing DICOM data
    """

    def __init__(self, config, file_system_manager):
        """Initialize the StudyProcessor.

        Args:
            config (dict): Application configuration dictionary containing 
                          processing settings and feature flags.
            file_system_manager (FileSystemManager): Instance of FileSystemManager
                                                   for file operations.
        """
        self.config = config
        self.fsm = file_system_manager
        
        # Initialize anonymizer with its specific configuration section
        anonymization_settings = self.config.get("anonymization", {})
        
        # Always initialize the anonymizer to ensure AccessionNumber is always removed,
        # even if full anonymization is disabled in the config
        self.anonymizer = DicomAnonymizer(anonymization_settings)
        
        if not anonymization_settings.get("enabled", True):
            logger.info("Full anonymization is disabled, only AccessionNumber will be removed.")

    # ======== Contour Processing Methods ========
    
    def _handle_contour_logic(self, rtstruct_builder, dcm_path):
        """Filters and processes contours from an RTSTRUCT file based on naming rules.
        
        This method applies filtering rules to exclude specific contours (like skull)
        while including others for processing. It implements the business logic for
        determining which contours to process or ignore based on configuration.
        
        Args:
            rtstruct_builder: Object with access to RTSTRUCT contour data
            dcm_path: Path to the corresponding DICOM images
            
        Returns:
            list: List of ROI names to process, or None if no valid contours found
            
        Notes:
            - Contours containing terms in the ignore_contour_names_containing config
              setting will be excluded from processing
            - Multiple non-ignored contours will be merged into a single binary mask
            - If no valid contours remain after filtering, None is returned
        """
        # Get all contours from the RTSTRUCT file
        structures = rtstruct_builder.get_roi_names()
        logger.info(f"Original ROI names: {structures}")
        
        # Initialize lists to track contours
        final_rois_to_process = []
        skull_contours_found = []
        
        # Get ignore patterns from config, default to "skull" if not specified
        ignore_names = self.config.get("processing", {}).get("ignore_contour_names_containing", ["skull"])

        # Filter contours based on naming patterns
        for struct_name in structures:
            should_ignore = False
            for ignore_term in ignore_names:
                if ignore_term.lower() in struct_name.lower():
                    should_ignore = True
                    break
                    
            # Sort contours into appropriate lists
            if should_ignore:
                skull_contours_found.append(struct_name)
                logger.info(f"Identified contour to ignore: {struct_name} (based on terms: {ignore_names}).")
            else:
                final_rois_to_process.append(struct_name)
        
        # Log the ignored contours if any were found
        if len(skull_contours_found) > 0:
            logger.info(f"Contours ignored: {skull_contours_found}")

        # Handle case where no valid contours remain
        if not final_rois_to_process:
            logger.warning(f"No non-ignored contours found in {rtstruct_builder.rt_struct_path}. Nothing to merge or process.")
            return None # Or an empty mask

        # Warn if multiple contours will be merged
        if len(final_rois_to_process) > 1:
            logger.warning(f"Multiple non-ignored contours found: {final_rois_to_process}. They will be merged into a single binary mask by Contour_Addition.")
        
        return final_rois_to_process

    # ======== Main Processing Pipeline ========
    
    def process_study(self, study_instance_uid):
        """Processes a single DICOM study through the complete pipeline.
        
        This method is the main entry point for processing a study and coordinates
        the entire workflow from start to finish, including:
        1. Setting up directory structure
        2. Validating input files
        3. Anonymizing DICOM data
        4. Processing contours and generating overlays
        5. Creating DICOM SEG files if enabled
        6. Adding burn-in disclaimers
        7. Sending results to destination DICOM systems
        8. Cleanup or quarantine based on success/failure
        
        Args:
            study_instance_uid: StudyInstanceUID of the study to process
            
        Returns:
            bool: True if processing completed successfully, False otherwise
        """
        # ---- Initialization and setup ----
        study_path = self.fsm.get_study_path(study_instance_uid)
        processing_start_time = time.time()
        
        # Log processing start to both standard and transaction logs
        transaction_logger.info(f"PROCESSING_START StudyUID: {study_instance_uid}, Path: {study_path}")
        logger.info(f"Starting processing for study: {study_path} (UID: {study_instance_uid})")

        # Set up directory paths for input and output data
        dcm_path = os.path.join(study_path, "DCM")                 # Original DICOM images
        struct_dir_path = os.path.join(study_path, "Structure")    # RTSTRUCT files
        addition_path = os.path.join(study_path, "Addition")       # Output for contour addition
        seg_path = os.path.join(study_path, "Segmentations")       # Output for DICOM SEG
        
        # Create output directories
        os.makedirs(addition_path, exist_ok=True)
        os.makedirs(seg_path, exist_ok=True)

        # ---- Validate input files ----
        # Verify that the DCM directory exists and contains files
        if not os.path.isdir(dcm_path) or not os.listdir(dcm_path):
            logger.error(f"DCM directory is missing or empty for study {study_instance_uid}")
            self.fsm.quarantine_study(study_instance_uid, "Missing or empty DCM directory")
            transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, Reason: Missing or empty DCM directory")
            return False

        # Check for and locate RTSTRUCT file if present
        struct_file_path = None
        if os.path.isdir(struct_dir_path) and os.listdir(struct_dir_path):
            # Find all DICOM files in the Structure directory
            struct_files = [os.path.join(struct_dir_path, f) for f in os.listdir(struct_dir_path) 
                           if f.lower().endswith(".dcm")]
            
            if struct_files:
                # Use the first RTSTRUCT file found
                struct_file_path = struct_files[0]
                
                # Warn if multiple RTSTRUCT files were found
                if len(struct_files) > 1:
                    logger.warning(f"Multiple RTSTRUCT files found in {struct_dir_path}. Using the first one: {struct_file_path}")
            else:
                logger.warning(f"No .dcm files found in Structure directory for study {study_instance_uid}.")
        else:
            logger.warning(f"Structure directory is missing or empty for study {study_instance_uid}. Proceeding without contour processing.")

        try:
            # ---- Configuration and initialization ----
            # Load anonymization flags from configuration
            base_anon_flag = self.config.get("anonymization", {}).get("enabled", True)
            full_anon_flag = self.config.get("anonymization", {}).get("full_anonymization_enabled", False)

            # Only enable full de-identification for legacy modules if both flags are enabled
            deidentify_for_old_modules = base_anon_flag and full_anon_flag
            
            # Generate new UIDs for processed series
            new_study_instance_id_for_series = pydicom.uid.generate_uid()
            new_fod_ref_id = pydicom.uid.generate_uid()
            
            # Generate a random ID for legacy modules if de-identification is enabled
            rand_id_for_old_modules = ""
            if deidentify_for_old_modules:
                letters = "abcdefghijklmnopqrstuvwxyz"
                rand_id_for_old_modules = "".join(random.choice(letters) for _ in range(8)).upper()
                logger.info(f"De-identification enabled for legacy modules. RAND_ID: {rand_id_for_old_modules}")

            # ---- Anonymize original files ----
            # This must happen before any processing that depends on DICOM tags
            logger.info(f"Applying anonymization to files in {dcm_path} for study {study_instance_uid}")
            
            # Get anonymization settings for logging
            anon_enabled = self.config.get("anonymization", {}).get("enabled", True)
            full_anon_enabled = self.config.get("anonymization", {}).get("full_anonymization_enabled", False)
            
            if anon_enabled:
                logger.info(f"Anonymization is enabled. Full anonymization: {full_anon_enabled}")
            else:
                logger.info("Anonymization is disabled. Only AccessionNumber will be removed.")
                
            # Process all DICOM files in the DCM directory
            for root, _, files in os.walk(dcm_path):
                for filename in files:
                    if filename.lower().endswith(".dcm"):
                        filepath = os.path.join(root, filename)
                        try:
                            # Read, anonymize, and save each file in place
                            ds = pydicom.dcmread(filepath)
                            self.anonymizer.anonymize(ds)
                            ds.save_as(filepath)
                            logger.debug(f"Anonymized and saved: {filepath}")
                        except Exception as e:
                            logger.error(f"Failed to anonymize file {filepath}: {e}", exc_info=True)
            
            # Process the RTSTRUCT file if it exists
            if struct_file_path:
                try:
                    # Read, anonymize, and save the RTSTRUCT file
                    ds_struct = pydicom.dcmread(struct_file_path)
                    self.anonymizer.anonymize(ds_struct)
                    ds_struct.save_as(struct_file_path)
                    logger.info(f"Anonymized and saved RTSTRUCT: {struct_file_path}")
                except Exception as e:
                    logger.error(f"Failed to anonymize RTSTRUCT file {struct_file_path}: {e}", exc_info=True)

            # ---- Contour Addition ----
            if struct_file_path:
                logger.info(f"Processing contours from {struct_file_path} for images in {dcm_path}")
                
                # Process RTSTRUCT contours and create overlay images
                try:
                    # Initialize contour processor with appropriate parameters
                    contour_adder = Contour_Addition.ContourAddition(
                        dcm_path=dcm_path,                                # Path to DICOM images
                        struct_path=struct_file_path,                     # Path to RTSTRUCT file
                        deidentify=deidentify_for_old_modules,            # Whether to de-identify output
                        STUDY_INSTANCE_ID=new_study_instance_id_for_series, # New StudyInstanceUID for output
                        CT_SOPInstanceUID=pydicom.uid.generate_uid(),     # New SOP instance UID for CT reference
                        FOD_REF_ID=new_fod_ref_id,                        # New frame of reference UID
                        RAND_ID=rand_id_for_old_modules,                  # Random ID for de-identification
                    )
                    
                    # Execute contour processing
                    contour_adder.process()
                    logger.info("Contour addition process completed successfully.")
                except Exception as e:
                    # Handle contour processing failures by quarantining the study
                    logger.error(f"Contour addition failed for study {study_instance_uid}: {e}", exc_info=True)
                    self.fsm.quarantine_study(study_instance_uid, f"Contour addition error: {str(e)}")
                    transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, Reason: Contour addition error: {str(e)}")
                    return False

                # ---- Add Burn-In Disclaimer ----
                # Add burn-in text to the overlay images if enabled in config
                if self.config.get("processing", {}).get("add_burn_in_disclaimer", True):
                    # Get disclaimer text from config or use default
                    burn_in_text = self.config.get("processing", {}).get(
                        "burn_in_text", "RESEARCH IMAGE - Not for diagnostic purpose")
                    
                    # Initialize and apply burn-in text
                    burn_in_adder = Add_Burn_In.Add_Burn_In(addition_path, burn_in_text)
                    try:
                        burn_in_adder.apply_watermarks()
                        logger.info(f"Burn-in disclaimer added with text: '{burn_in_text}'")
                    except Exception as e:
                        # Handle burn-in failures by quarantining the study
                        logger.error(f"Apply watermark failed for study {study_instance_uid}: {e}")
                        self.fsm.quarantine_study(study_instance_uid, str(e))
                        return False
                else:
                    logger.info("Burn-in disclaimer is disabled by configuration.")
            else:
                logger.info("No RTSTRUCT file found or specified, skipping contour addition and burn-in.")

            # ---- DICOM SEG Creation ----
            # Create DICOM Segmentation objects if enabled in config
            if self.config.get("feature_flags", {}).get("enable_segmentation_export", False) and struct_file_path:
                # Skip SEG creation when de-identifying for legacy modules
                if not deidentify_for_old_modules:
                    logger.info("Creating DICOM SEG objects from RTSTRUCT contours.")
                    
                    # Get series number for segmentation series
                    seg_series_num = self.config.get("processing", {}).get("default_series_number_seg", 9902)
                    
                    try:
                        # Initialize segmentation creator
                        segmentation_creator = Segmentations.Segmentations(
                            dcm_path=dcm_path,                               # Path to DICOM images
                            struct_path=struct_file_path,                    # Path to RTSTRUCT file
                            seg_path=seg_path,                               # Output path for SEG files
                            DEIDENTIFY=deidentify_for_old_modules,           # Whether to de-identify
                            STUDY_INSTANCE_ID=new_study_instance_id_for_series, # StudyUID for new series
                        )
                        
                        # Process RTSTRUCT and create SEG objects
                        segmentation_creator.process()
                        logger.info("DICOM SEG creation completed successfully.")
                    except Exception as e:
                        logger.error(f"DICOM SEG creation failed for study {study_instance_uid}: {e}", exc_info=True)
                else:
                    logger.info("DICOM SEG creation skipped due to de-identification flag for legacy modules.")
            else:
                logger.info("DICOM SEG creation is disabled by feature flag or no RTSTRUCT file is available.")
            
            # ---- Send Processed Files to Destination ----
            # Get destination details from configuration
            dest_ip = self.config.get("dicom_destination", {}).get("ip", "127.0.0.1")
            dest_port = self.config.get("dicom_destination", {}).get("port", 11112)
            dest_aet = self.config.get("dicom_destination", {}).get("ae_title", "DEST_AET")

            # Send overlay series (output of contour addition)
            files_sent_overlay = False
            if os.path.exists(addition_path) and os.listdir(addition_path):
                # Log the start of sending process
                transaction_logger.info(f"SENDING_START SeriesType: OVERLAY, StudyUID: {study_instance_uid}, " +
                                        f"DestAET: {dest_aet}, DestIP: {dest_ip}, DestPort: {dest_port}")
                logger.info(f"Sending processed files with overlays from {addition_path} to {dest_aet}@{dest_ip}:{dest_port}")
                
                try:
                    # Initialize and execute file sender
                    sender_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aet)
                    sender_overlay.send_dicom_folder()
                    
                    # Mark successful send and log it
                    files_sent_overlay = True
                    transaction_logger.info(f"SENDING_SUCCESS SeriesType: OVERLAY, StudyUID: {study_instance_uid}, DestAET: {dest_aet}")
                except Exception as e:
                    # Log failures
                    logger.error(f"Failed to send OVERLAY series for study {study_instance_uid} to {dest_aet}: {e}", exc_info=True)
                    transaction_logger.error(f"SENDING_FAILED SeriesType: OVERLAY, StudyUID: {study_instance_uid}, " +
                                             f"DestAET: {dest_aet}, Reason: {str(e)}")
            else:
                logger.info(f"No files in {addition_path} to send (overlay series).")

            # Send DICOM SEG series if enabled and created
            files_sent_seg = False
            if (self.config.get("feature_flags", {}).get("enable_segmentation_export", False) and 
                os.path.exists(seg_path) and os.listdir(seg_path)):
                
                # Only send SEG files if not de-identifying for legacy modules
                # (this check should match the condition for SEG creation)
                if not deidentify_for_old_modules: 
                    # Log the start of sending process
                    transaction_logger.info(f"SENDING_START SeriesType: SEG, StudyUID: {study_instance_uid}, " +
                                            f"DestAET: {dest_aet}, DestIP: {dest_ip}, DestPort: {dest_port}")
                    logger.info(f"Sending DICOM SEG files from {seg_path} to {dest_aet}@{dest_ip}:{dest_port}")
                    
                    try:
                        # Initialize and execute file sender for SEG files
                        sender_seg = Send_Files.SendFiles(seg_path, dest_ip, dest_port, dest_aet)
                        sender_seg.send_dicom_folder()
                        
                        # Mark successful send and log it
                        files_sent_seg = True
                        transaction_logger.info(f"SENDING_SUCCESS SeriesType: SEG, StudyUID: {study_instance_uid}, DestAET: {dest_aet}")
                    except Exception as e:
                        # Log failures
                        logger.error(f"Failed to send SEG series for study {study_instance_uid} to {dest_aet}: {e}", exc_info=True)
                        transaction_logger.error(f"SENDING_FAILED SeriesType: SEG, StudyUID: {study_instance_uid}, " +
                                                 f"DestAET: {dest_aet}, Reason: {str(e)}")
                else:
                    logger.info(f"SEG series sending skipped due to de-identification flag for legacy modules.")
            else:
                logger.info(f"No files in {seg_path} to send (SEG series), or SEG export is disabled.")

            # ---- Finalize Processing ----
            # Calculate and log processing duration
            processing_duration = time.time() - processing_start_time
            
            # Log successful completion with details about sent files
            transaction_logger.info(f"PROCESSING_SUCCESS StudyUID: {study_instance_uid}, " +
                                    f"DurationSec: {processing_duration:.2f}, " +
                                    f"OverlaySent: {files_sent_overlay}, SegSent: {files_sent_seg}")
            logger.info(f"Processing for study {study_instance_uid} completed successfully in {processing_duration:.2f} seconds.")
            
            # Clean up the original study directory after successful processing
            self.fsm.cleanup_study_directory(study_instance_uid)
            return True

        except Exception as e:
            # ---- Error Handling ----
            # Calculate processing duration (for reporting)
            processing_duration = time.time() - processing_start_time
            
            # Log detailed error information
            logger.error(f"Error processing study {study_instance_uid} after {processing_duration:.2f} seconds: {e}", 
                         exc_info=True)
            
            # Move the study to quarantine for later analysis
            self.fsm.quarantine_study(study_instance_uid, str(e))
            
            # Log failure in transaction log
            transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, " +
                                     f"DurationSec: {processing_duration:.2f}, Reason: {str(e)}")
            return False