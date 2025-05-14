# netrt_core/study_processor.py

import os
import logging
import pydicom
import random # For RAND_ID if de-identifying, though this should be managed better

# Import existing application modules - these might need adaptation later
# For now, assume they are in the parent directory or Python path is set up
import DicomAnonymizer # Assuming DicomAnonymizer.py is accessible
import Contour_Addition  # Assuming Contour_Addition.py is accessible
import Add_Burn_In       # Assuming Add_Burn_In.py is accessible
import Send_Files        # Assuming Send_Files.py is accessible
import Segmentations     # Assuming Segmentations.py is accessible

logger = logging.getLogger(__name__)

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
        self.anonymizer = DicomAnonymizer.DicomAnonymizer() if self.config.get("anonymization", {}).get("enabled", False) else None

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

        for struct_name in structures:
            if "skull" in struct_name.lower(): # Case-insensitive check for "skull"
                skull_contours_found.append(struct_name)
                logger.info(f"Identified skull contour: {struct_name}. It will be ignored for direct processing.")
            else:
                final_rois_to_process.append(struct_name)
        
        if len(skull_contours_found) > 0:
            logger.info(f"Skull contours ignored: {skull_contours_found}")

        if not final_rois_to_process:
            logger.warning(f"No non-skull contours found in {rtstruct_builder.rt_struct_path}. Nothing to merge or process.")
            return None # Or an empty mask

        if len(final_rois_to_process) > 1:
            logger.warning(f"Multiple non-skull contours found: {final_rois_to_process}. They will be merged into a single binary mask.")
        
        # The actual merging logic will happen within the modified Contour_Addition module
        # For now, this function primarily serves to identify and log.
        # Contour_Addition will need to be adapted to accept a list of ROIs to merge,
        # or to implement this filtering internally.
        return final_rois_to_process # Return list of ROIs to be processed/merged

    def process_study(self, study_instance_uid):
        """Processes a single DICOM study located in the working directory."""
        study_path = self.fsm.get_study_path(study_instance_uid)
        logger.info(f"Starting processing for study: {study_path}")

        dcm_path = os.path.join(study_path, "DCM")
        struct_dir_path = os.path.join(study_path, "Structure")
        addition_path = os.path.join(study_path, "Addition") # Output for contour addition
        seg_path = os.path.join(study_path, "Segmentations") # Output for DICOM SEG
        os.makedirs(addition_path, exist_ok=True)
        os.makedirs(seg_path, exist_ok=True)

        if not os.path.isdir(dcm_path) or not os.listdir(dcm_path):
            logger.error(f"DCM directory is missing or empty for study {study_instance_uid}")
            self.fsm.quarantine_study(study_instance_uid, "Missing or empty DCM directory")
            return False

        if not os.path.isdir(struct_dir_path) or not os.listdir(struct_dir_path):
            logger.warning(f"Structure directory is missing or empty for study {study_instance_uid}. Proceeding without contour processing if applicable.")
            # Depending on workflow, this might be an error or just a path that skips contouring.
            # For now, let it proceed, Contour_Addition should handle it.
            struct_file_path = None
        else:
            struct_files = [os.path.join(struct_dir_path, f) for f in os.listdir(struct_dir_path) if f.endswith(".dcm")]
            if not struct_files:
                logger.warning(f"No .dcm files found in Structure directory for study {study_instance_uid}.")
                struct_file_path = None
            else:
                struct_file_path = struct_files[0] # Assuming one RTSTRUCT file
                if len(struct_files) > 1:
                    logger.warning(f"Multiple RTSTRUCT files found in {struct_dir_path}. Using the first one: {struct_file_path}")

        try:
            # --- Configuration items --- 
            deidentify = self.config.get("anonymization", {}).get("enabled", False)
            # These UIDs should be robustly generated and managed
            # For now, using pydicom.uid.generate_uid() as in original script
            STUDY_INSTANCE_ID = pydicom.uid.generate_uid() # This seems to be for the *new* study/series
            FOD_REF_ID = pydicom.uid.generate_uid()
            CT_SOPInstanceUID_prefix = "1.2.840.10008.5.1.4.1.1.2." # Example for CT
            
            RAND_ID = ""
            if deidentify:
                letters = "abcdefghijklmnopqrstuvwxyz"
                RAND_ID = "".join(random.choice(letters) for _ in range(8)).upper()
                logger.info(f"De-identification enabled. RAND_ID: {RAND_ID}")

            # --- Contour Addition (incorporating new logic) ---
            if struct_file_path:
                logger.info(f"Processing contours from {struct_file_path} for images in {dcm_path}")
                # The ContourAddition class will need to be refactored to accept config for RAND_ID,
                # and to handle the new skull/merge logic based on a list of ROIs or internal filtering.
                # For now, we pass the deidentify flag and RAND_ID.
                # The actual ROI filtering and merging logic needs to be implemented IN or BEFORE ContourAddition.process
                
                # This is where the _handle_contour_logic would ideally be used to prepare ROIs
                # rt_struct_builder = Contour_Addition.RTStructBuilder.create_from(dicom_series_path=dcm_path, rt_struct_path=struct_file_path)
                # rois_to_process = self._handle_contour_logic(rt_struct_builder, dcm_path)
                # if rois_to_process is None and struct_file_path: # No valid ROIs to process
                #    logger.warning("No processable ROIs after filtering. Skipping contour addition.")
                # else:

                # The ContourAddition class will need significant refactoring to align with new requirements.
                # For now, let's assume it can be instantiated and run. It will need access to `addition_path`.
                # It also internally creates `Addition` directory, this should be harmonized.
                contour_adder = Contour_Addition.ContourAddition(
                    dcm_path=dcm_path, 
                    struct_path=struct_file_path, 
                    deidentify=deidentify, 
                    STUDY_INSTANCE_ID=STUDY_INSTANCE_ID, 
                    CT_SOPInstanceUID=pydicom.uid.generate_uid(prefix=CT_SOPInstanceUID_prefix), # This UID generation needs review
                    FOD_REF_ID=FOD_REF_ID, 
                    RAND_ID=RAND_ID,
                    # output_dir=addition_path # A new parameter might be needed
                )
                # The process method in ContourAddition needs to be updated to use the output_dir
                # and to implement the new contour handling (skull ignore, merge others)
                contour_adder.process() # This will write to its own `Addition` subdir for now.
                logger.info("Contour addition process completed.")

                # --- Add Burn In --- (operates on the output of ContourAddition)
                # The original Contour_Addition saves into <study_path>/Addition
                # We need to ensure Add_Burn_In looks there.
                burn_in_adder = Add_Burn_In.Add_Burn_In(addition_path)
                burn_in_adder.apply_watermarks()
                logger.info("Burn-in disclaimer added.")
            else:
                logger.info("No RTSTRUCT file found or specified, skipping contour addition and burn-in.")
                # If no contours, addition_path might be empty. Send_Files needs to handle this.

            # --- DICOM SEG Creation (if not de-identifying) ---
            if not deidentify and struct_file_path:
                logger.info("Creating DICOM SEG objects.")
                # Segmentation class also needs config for UIDs and output path (seg_path)
                segmentation_creator = Segmentations.Segmentations(
                    dcm_path=dcm_path, 
                    struct_path=struct_file_path, 
                    seg_path=seg_path, # Pass the output path
                    DEIDENTIFY=deidentify, # Should be False here
                    STUDY_INSTANCE_ID=STUDY_INSTANCE_ID
                )
                segmentation_creator.process()
                logger.info("DICOM SEG creation completed.")
            
            # --- Send Files --- 
            dest_ip = self.config.get("dicom_destination", {}).get("ip", "127.0.0.1")
            dest_port = self.config.get("dicom_destination", {}).get("port", 11112)
            dest_aet = self.config.get("dicom_destination", {}).get("ae_title", "DEST_AET")

            if os.path.exists(addition_path) and os.listdir(addition_path):
                logger.info(f"Sending processed files with overlays from {addition_path} to {dest_aet}@{dest_ip}:{dest_port}")
                sender_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aet)
                sender_overlay.send_dicom_folder()
            else:
                logger.info(f"No files in {addition_path} to send (overlay series).")

            if not deidentify and os.path.exists(seg_path) and os.listdir(seg_path):
                logger.info(f"Sending DICOM SEG files from {seg_path} to {dest_aet}@{dest_ip}:{dest_port}")
                sender_seg = Send_Files.SendFiles(seg_path, dest_ip, dest_port, dest_aet)
                sender_seg.send_dicom_folder()
            else:
                logger.info(f"No files in {seg_path} to send (SEG series), or de-identification is on.")

            logger.info(f"Processing for study {study_instance_uid} completed successfully.")
            self.fsm.cleanup_study_directory(study_instance_uid)
            return True

        except Exception as e:
            logger.error(f"Error processing study {study_instance_uid}: {e}", exc_info=True)
            self.fsm.quarantine_study(study_instance_uid, str(e))
            return False

# Example usage (for testing - will be integrated into the main application)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    # Dummy config and FSM for testing StudyProcessor
    # This requires the dependent modules (Contour_Addition etc.) to be in PYTHONPATH
    # and a valid DICOM dataset in the specified structure.
    # This test is complex to set up standalone and is better tested via integration tests.
    
    test_config = {
        "anonymization": {"enabled": False},
        "dicom_destination": {"ip": "127.0.0.1", "port": 104, "ae_title": "TEST_PACS"},
        "directories": {
            "working": "/home/ubuntu/CNCT_working_sp_test",
            "logs": "/home/ubuntu/CNCT_logs_sp_test"
        }
        # Add other necessary configs for Contour_Addition, Segmentations etc. if they are refactored to take config dict
    }

    # Need to mock FileSystemManager or create a real one
    class MockFSM:
        def __init__(self, config):
            self.working_dir = os.path.expanduser(config.get("directories", {}).get("working", "~/CNCT_working"))
            self.quarantine_dir = os.path.join(self.working_dir, "quarantine")
            os.makedirs(self.working_dir, exist_ok=True)
            os.makedirs(self.quarantine_dir, exist_ok=True)
            logger.info(f"MockFSM initialized. Working: {self.working_dir}")

        def get_study_path(self, study_instance_uid):
            return os.path.join(self.working_dir, f"UID_{study_instance_uid}")

        def quarantine_study(self, study_instance_uid, reason):
            logger.warning(f"MOCK: Quarantining study {study_instance_uid} due to: {reason}")
        
        def cleanup_study_directory(self, study_instance_uid):
            logger.info(f"MOCK: Cleaning up study directory for {study_instance_uid}")

    mock_fsm = MockFSM(test_config)
    processor = StudyProcessor(test_config, mock_fsm)

    # To test this, you would need to:
    # 1. Create a directory structure like /home/ubuntu/CNCT_working_sp_test/UID_SomeStudyUID/DCM/...
    # 2. Populate it with actual DICOM files and an RTSTRUCT in UID_SomeStudyUID/Structure/...
    # 3. Then call: processor.process_study("SomeStudyUID")
    logger.info("StudyProcessor initialized. Run a specific test case by creating data and calling process_study.")

    # Example: Create a dummy study structure for a hypothetical test
    test_study_uid = "1.2.3.4.5"
    dummy_study_dir = mock_fsm.get_study_path(test_study_uid)
    dummy_dcm_dir = os.path.join(dummy_study_dir, "DCM")
    dummy_struct_dir = os.path.join(dummy_study_dir, "Structure")
    os.makedirs(dummy_dcm_dir, exist_ok=True)
    os.makedirs(dummy_struct_dir, exist_ok=True)
    # Create dummy files (these won't be valid DICOMs, just for path testing)
    with open(os.path.join(dummy_dcm_dir, "ct1.dcm"), "w") as f: f.write("dummy ct")
    with open(os.path.join(dummy_struct_dir, "rtstruct.dcm"), "w") as f: f.write("dummy rtstruct")
    
    logger.info(f"Attempting to process dummy study: {test_study_uid}. This will likely fail due to dummy data.")
    # processor.process_study(test_study_uid) # This will fail as Contour_Addition etc. expect real DICOMs


