import os
from pynetdicom import AE
from pynetdicom.sop_class import CTImageStorage, SecondaryCaptureImageStorage, SegmentationStorage
from pydicom import dcmread
from pydicom.uid import ImplicitVRLittleEndian, JPEGExtended
import logging

# Import the logging configuration
from logging_config import setup_logging

# Ensure the logger is set up
setup_logging()

# Create a logger instance for this script
logger = logging.getLogger('Send_Files')

class SendFiles:

    def __init__(self, dcm_path, dest_ip='152.11.105.191', dest_port=8104, dest_aetitle="RIIPLXNAT"):
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.dest_aetitle = dest_aetitle
        self.dcm_path = dcm_path

    def send_dicom_folder(self):
        try:
            # Initialize the Application Entity
            ae = AE()

            # Add the requested contexts for different SOP Classes and Transfer Syntaxes
            ae.add_requested_context(CTImageStorage, ImplicitVRLittleEndian)
            ae.add_requested_context(SecondaryCaptureImageStorage, JPEGExtended)
            ae.add_requested_context(SegmentationStorage, ImplicitVRLittleEndian)

            filepath = self.dcm_path
            logger.info(f"Path to the DICOM directory: {filepath}")

            # Load the data
            dicom_files = [f for f in os.listdir(filepath) if f.endswith('.dcm')]

            # Associate with peer AE at IP and port
            assoc = ae.associate(
                self.dest_ip,
                self.dest_port,
                ae_title=self.dest_aetitle
            )

            if assoc.is_established:
                logger.info(f"Association established with {self.dest_aetitle} at {self.dest_ip}:{self.dest_port}")

                for dicom in dicom_files:
                    try:
                        ds = dcmread(os.path.join(filepath, dicom))
                        # Use the C-STORE service to send the dataset
                        status = assoc.send_c_store(ds)
                        if status and status.Status == 0x0000:
                            logger.info(f"C-STORE request for {dicom} successful: 0x{status.Status:04X}")
                        else:
                            logger.error(f"C-STORE request for {dicom} failed with status: 0x{status.Status:04X}" if status else "Connection timed out, was aborted or received invalid response")
                    except Exception as e:
                        logger.error(f"Error reading or sending DICOM file {dicom}: {e}")
            else:
                logger.error(f"Association rejected, aborted or never connected to {self.dest_aetitle} at {self.dest_ip}:{self.dest_port}")

        except Exception as e:
            logger.error(f"An error occurred during association or sending files: {e}")
        finally:
            # Ensure the association is released
            if assoc.is_established:
                assoc.release()
                logger.info("Association released")
