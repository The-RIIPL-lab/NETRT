import os
import logging
from pydicom import dcmread
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES
from pynetdicom.sop_class import AllStoragePresentationContexts

logger = logging.getLogger(__name__)

class DicomSender:
    """A class to handle sending DICOM files to a remote AE."""

    def __init__(self, host, port, ae_title):
        """
        Initializes the DicomSender.

        Args:
            host (str): The IP address of the destination.
            port (int): The port number of the destination.
            ae_title (str): The AE Title of the destination.
        """
        self.host = host
        self.port = port
        self.ae_title = ae_title
        self.ae = AE()
        # Add all standard storage presentation contexts
        for context in AllStoragePresentationContexts:
            self.ae.add_requested_context(context.abstract_syntax, ALL_TRANSFER_SYNTAXES)

    def send_directory(self, directory_path):
        """
        Sends all DICOM files in a given directory.

        Args:
            directory_path (str): The absolute path to the directory containing DICOM files.
        
        Returns:
            bool: True if all files were sent successfully, False otherwise.
        """
        logger.info(f"Attempting to send files from {directory_path} to {self.ae_title}@{self.host}:{self.port}")
        
        if not os.path.isdir(directory_path):
            logger.error(f"Directory not found: {directory_path}")
            return False

        dicom_files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) if f.lower().endswith('.dcm')]
        if not dicom_files:
            logger.warning(f"No DICOM files found in {directory_path} to send.")
            return True # No files to send is not a failure

        assoc = self.ae.associate(self.host, self.port, ae_title=self.ae_title)

        if not assoc.is_established:
            logger.error(f"Association rejected, aborted or never connected to {self.ae_title}@{self.host}:{self.port}")
            return False

        success = True
        try:
            for filepath in dicom_files:
                try:
                    ds = dcmread(filepath)
                    status = assoc.send_c_store(ds)
                    if status and status.Status == 0x0000:
                        logger.debug(f"Successfully sent {filepath}")
                    else:
                        logger.error(f"Failed to send {filepath}. Status: {status}")
                        success = False
                except Exception as e:
                    logger.error(f"Exception while sending file {filepath}: {e}", exc_info=True)
                    success = False
        finally:
            assoc.release()
            logger.info("Association released.")
        
        return success
