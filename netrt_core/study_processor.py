import os
import logging
import time
import pydicom

from .dicom_sender import DicomSender
from .burn_in_processor import BurnInProcessor
from .contour_processor import ContourProcessor
from DicomAnonymizer import DicomAnonymizer

logger = logging.getLogger(__name__)
transaction_logger = logging.getLogger("transaction")

class StudyProcessor:
    """Orchestrates the processing pipeline for a received DICOM study."""

    def __init__(self, config, file_system_manager):
        self.config = config
        self.fsm = file_system_manager
        self.anonymizer = DicomAnonymizer(self.config.get("anonymization", {}))
        self.contour_processor = ContourProcessor(self.config)
        self.burn_in_processor = BurnInProcessor(self.config.get("processing", {}).get("burn_in_text"))

    def process_study(self, study_instance_uid):
        """Main entry point for processing a study."""
        study_path = self.fsm.get_study_path(study_instance_uid)
        processing_start_time = time.time()
        transaction_logger.info(f"PROCESSING_START StudyUID: {study_instance_uid}, Path: {study_path}")
        logger.info(f"Starting processing for study: {study_instance_uid}")

        try:
            dcm_path, struct_path, addition_path = self._setup_paths(study_path)

            if not self._validate_inputs(dcm_path, study_instance_uid):
                return False

            struct_file = self._find_struct_file(struct_path)

            if self.config.get("anonymization", {}).get("enabled", True):
                self._anonymize_study(dcm_path, struct_file)

            if struct_file:
                success, debug_dicom_dir = self.contour_processor.run(
                    dcm_path, struct_file, addition_path, 
                    self.config.get('debug_mode', False), study_instance_uid
                )
                if not success:
                    raise Exception("Contour processing failed")

                if self.config.get("processing", {}).get("add_burn_in_disclaimer", True):
                    self.burn_in_processor.run(addition_path)
                
                self._send_directory(addition_path, "OVERLAY", study_instance_uid)
                
                # Send debug DICOM series if created
                if debug_dicom_dir and os.path.exists(debug_dicom_dir):
                    self._send_directory(debug_dicom_dir, "DEBUG", study_instance_uid)
            else:
                logger.warning(f"No RTSTRUCT file found for study {study_instance_uid}. Nothing to process or send.")

            self.fsm.cleanup_study_directory(study_instance_uid)
            processing_duration = time.time() - processing_start_time
            logger.info(f"Processing for study {study_instance_uid} completed successfully in {processing_duration:.2f} seconds.")
            transaction_logger.info(f"PROCESSING_SUCCESS StudyUID: {study_instance_uid}, DurationSec: {processing_duration:.2f}")
            return True

        except Exception as e:
            processing_duration = time.time() - processing_start_time
            logger.error(f"Error processing study {study_instance_uid}: {e}", exc_info=True)
            self.fsm.quarantine_study(study_instance_uid, str(e))
            transaction_logger.error(f"PROCESSING_FAILED StudyUID: {study_instance_uid}, DurationSec: {processing_duration:.2f}, Reason: {str(e)}")
            return False

    def _setup_paths(self, study_path):
        """Create and return the necessary directory paths for processing."""
        dcm_path = os.path.join(study_path, "DCM")
        struct_path = os.path.join(study_path, "Structure")
        addition_path = os.path.join(study_path, "Addition")
        os.makedirs(addition_path, exist_ok=True)
        return dcm_path, struct_path, addition_path

    def _validate_inputs(self, dcm_path, study_instance_uid):
        """Validates that the necessary input directories and files exist."""
        if not os.path.isdir(dcm_path) or not os.listdir(dcm_path):
            logger.error(f"DCM directory is missing or empty for study {study_instance_uid}")
            self.fsm.quarantine_study(study_instance_uid, "Missing or empty DCM directory")
            return False
        return True

    def _find_struct_file(self, struct_dir_path):
        """Finds the first DICOM file in the Structure directory."""
        if not os.path.isdir(struct_dir_path) or not os.listdir(struct_dir_path):
            return None
        
        struct_files = [os.path.join(struct_dir_path, f) for f in os.listdir(struct_dir_path) if f.lower().endswith(".dcm")]
        if not struct_files:
            return None
        
        if len(struct_files) > 1:
            logger.warning(f"Multiple RTSTRUCT files found. Using the first one: {struct_files[0]}")
        return struct_files[0]

    def _anonymize_study(self, dcm_path, struct_file_path):
        """Anonymizes all DICOM files in a study."""
        logger.info(f"Anonymizing files in {dcm_path}...")
        for root, _, files in os.walk(dcm_path):
            for filename in files:
                if filename.lower().endswith(".dcm"):
                    self.anonymizer.anonymize_file(os.path.join(root, filename))
        
        if struct_file_path:
            logger.info(f"Anonymizing RTSTRUCT file: {struct_file_path}")
            self.anonymizer.anonymize_file(struct_file_path)

    def _send_directory(self, directory_path, series_type, study_instance_uid):
        """Sends a directory of DICOM files to the configured destination."""
        dest_config = self.config.get("dicom_destination", {})
        sender = DicomSender(dest_config.get("ip"), dest_config.get("port"), dest_config.get("ae_title"))
        
        transaction_logger.info(f"SENDING_START SeriesType: {series_type}, StudyUID: {study_instance_uid}, DestAET: {sender.ae_title}")
        if sender.send_directory(directory_path):
            transaction_logger.info(f"SENDING_SUCCESS SeriesType: {series_type}, StudyUID: {study_instance_uid}, DestAET: {sender.ae_title}")
        else:
            raise Exception(f"Failed to send {series_type} series.")
