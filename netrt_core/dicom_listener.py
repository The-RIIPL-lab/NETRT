# netrt_core/dicom_listener.py

import os
import logging
import pydicom
from pydicom.filewriter import write_file_meta_info
from pynetdicom import AE, evt, AllStoragePresentationContexts, ALL_TRANSFER_SYNTAXES
from pynetdicom.sop_class import Verification

# Placeholder for a more sophisticated logger, to be configured centrally
logger = logging.getLogger(__name__)

class DicomListener:
    """Handles DICOM C-STORE server setup and events."""

    def __init__(self, host, port, ae_title, study_processor_callback, file_system_manager):
        """Initialize the DICOM listener.

        Args:
            host (str): The IP address to listen on.
            port (int): The port number to listen on.
            ae_title (str): The AE title of this server.
            study_processor_callback (callable): Callback function to trigger study processing.
            file_system_manager (FileSystemManager): Instance of the FileSystemManager.
        """
        self.host = host
        self.port = port
        self.ae_title = ae_title
        self.study_processor_callback = study_processor_callback
        self.file_system_manager = file_system_manager
        self.ae = AE(ae_title=self.ae_title)
        self._configure_ae()

    def _configure_ae(self):
        """Configure supported presentation contexts for the AE."""
        self.ae.add_supported_context(Verification)
        storage_sop_classes = [cx.abstract_syntax for cx in AllStoragePresentationContexts]
        for uid in storage_sop_classes:
            self.ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)

    def _handle_echo(self, event):
        """Handle a C-ECHO request event."""
        logger.info("C-ECHO request received from {} ".format(event.assoc.requestor.address))
        return 0x0000  # Success

    def _handle_store(self, event):
        """Handle a C-STORE request event."""
        try:
            dataset = event.dataset
            # The dataset has been decoded using the negotiated transfer syntax
            # dataset.file_meta = event.file_meta

            # Ensure StudyInstanceUID is present
            if not hasattr(dataset, "StudyInstanceUID") or not dataset.StudyInstanceUID:
                logger.error("Received dataset missing StudyInstanceUID. Rejecting store.")
                return 0xA700 # Out of Resources - Or a more specific error

            # Use FileSystemManager to get the path for storing the file
            # This will also handle creation of the study directory structure
            # within the configured working directory.
            # The FileSystemManager will return the full path to the file.
            file_path = self.file_system_manager.save_incoming_dicom(dataset, event.file_meta)

            if file_path:
                logger.info(f"Stored DICOM file: {file_path} from {event.assoc.requestor.address}")
            else:
                logger.error("Failed to save DICOM file.")
                return 0xA700 # Or another appropriate error status

        except Exception as e:
            logger.error(f"Error handling C-STORE request: {e}", exc_info=True)
            return 0xC001 # Processing failure

        return 0x0000  # Success

    def _handle_conn_close(self, event):
        """Handle a connection close event."""
        logger.info("Connection closed with {}.".format(event.assoc.requestor.address))
        # Here, we might trigger the study processor if all files for a study are received.
        # This logic will be refined with the FileSystemManager and StudyProcessor.
        # For now, we assume the FileSystemManager or StudyProcessor handles study completion detection.
        
        # Example: Get the study path from the association if stored there, or manage via FileSystemManager
        # study_path = self.file_system_manager.get_study_path_for_association(event.assoc.name) # Hypothetical
        # if study_path and self.file_system_manager.is_study_reception_complete(study_path): # Hypothetical
        #    self.study_processor_callback(study_path)
        return 0x0000

    def start(self):
        """Start the DICOM listener server."""
        handlers = [
            (evt.EVT_C_ECHO, self._handle_echo),
            (evt.EVT_C_STORE, self._handle_store),
            (evt.EVT_CONN_CLOSE, self._handle_conn_close),
            # (evt.EVT_ACCEPTED, self._handle_association_accepted), # For more detailed association logging
            # (evt.EVT_RELEASED, self._handle_association_released), # For more detailed association logging
        ]

        logger.info(f"Starting DICOM server on {self.host}:{self.port} with AE Title: {self.ae_title}")
        # Start server in a non-blocking manner if it needs to be managed by a main loop
        # For now, let's assume it might be blocking or managed externally.
        self.ae.start_server((self.host, self.port), evt_handlers=handlers, block=True)

    def stop(self):
        """Stop the DICOM listener server."""
        logger.info("Stopping DICOM server...")
        self.ae.shutdown()

# Example usage (will be part of the main application script later)
if __name__ == "__main__":
    # This is for testing the module directly, not for production use.
    # Real implementation will use proper configuration and integration.
    logging.basicConfig(level=logging.INFO)
    
    # Dummy FileSystemManager and StudyProcessor for testing
    class DummyFSM:
        def __init__(self, working_dir):
            self.working_dir = working_dir
            os.makedirs(self.working_dir, exist_ok=True)
            logger.info(f"DummyFSM initialized with working_dir: {self.working_dir}")

        def save_incoming_dicom(self, dataset, file_meta):
            study_uid = dataset.StudyInstanceUID
            sop_instance_uid = dataset.SOPInstanceUID
            study_path = os.path.join(self.working_dir, f"UID_{study_uid}")
            
            # Determine if it's an RTSTRUCT or image
            # This logic needs to be robust, using SOPClassUID or Modality
            is_rtstruct = "RTSTRUCT" in str(dataset.SOPClassUID) or (hasattr(dataset, "Modality") and dataset.Modality == "RTSTRUCT")

            if is_rtstruct:
                series_dir_name = "Structure"
            else:
                series_dir_name = "DCM" # Or perhaps use SeriesInstanceUID for subfolders
            
            series_path = os.path.join(study_path, series_dir_name)
            os.makedirs(series_path, exist_ok=True)
            
            filename = f"{sop_instance_uid}.dcm"
            filepath = os.path.join(series_path, filename)
            
            try:
                # Create a new file meta information for writing
                file_meta_to_write = pydicom.Dataset()
                file_meta_to_write.MediaStorageSOPClassUID = dataset.SOPClassUID
                file_meta_to_write.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
                file_meta_to_write.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian # Or negotiated TS
                file_meta_to_write.ImplementationClassUID = pydicom.uid.generate_uid(prefix="1.2.3.") # Our UID
                file_meta_to_write.ImplementationVersionName = "NETRT_CORE_0.1"

                # Write the DICOM file
                dataset.file_meta = file_meta_to_write
                dataset.is_little_endian = True
                dataset.is_implicit_VR = True
                dataset.save_as(filepath, write_like_original=False)
                logger.info(f"DummyFSM: Saved {filepath}")
                return filepath
            except Exception as e:
                logger.error(f"DummyFSM: Error saving {filepath}: {e}", exc_info=True)
                return None

    class DummySP:
        def process_study(self, study_path):
            logger.info(f"DummySP: Processing study at {study_path}")

    # Configuration (replace with actual config loading)
    config = {
        "dicom_listener": {
            "host": "0.0.0.0",
            "port": 11112,
            "ae_title": "NETRTCORE"
        },
        "directories": {
            "working": "/home/ubuntu/CNCT_working_test_listener"
        }
    }

    fsm = DummyFSM(working_dir=config["directories"]["working"])
    sp = DummySP()

    listener = DicomListener(
        host=config["dicom_listener"]["host"],
        port=config["dicom_listener"]["port"],
        ae_title=config["dicom_listener"]["ae_title"],
        study_processor_callback=sp.process_study, # This callback needs to be more sophisticated
        file_system_manager=fsm
    )
    try:
        listener.start() # This will block
    except KeyboardInterrupt:
        logger.info("DICOM listener stopped by user.")
    finally:
        listener.stop()

