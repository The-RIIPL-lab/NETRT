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

            # Ensure StudyInstanceUID is present
            if not hasattr(dataset, "StudyInstanceUID") or not dataset.StudyInstanceUID:
                logger.error("Received dataset missing StudyInstanceUID. Rejecting store.")
                return 0xA700  # Out of Resources - Or a more specific error

            # Use FileSystemManager to get the path for storing the file
            file_path = self.file_system_manager.save_incoming_dicom(dataset, event.file_meta)

            if file_path:
                logger.info(f"Stored DICOM file: {file_path} from {event.assoc.requestor.address}")
            else:
                logger.error("Failed to save DICOM file.")
                return 0xA700  # Or another appropriate error status

        except Exception as e:
            logger.error(f"Error handling C-STORE request: {e}", exc_info=True)
            return 0xC001  # Processing failure

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