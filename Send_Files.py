from pynetdicom import AE
from pynetdicom import *
from pynetdicom.sop_class import Verification
from pathlib import Path
import logging
logger = logging.getLogger('NETRT')
from pydicom import dcmread
from pynetdicom.sop_class import CTImageStorage, SecondaryCaptureImageStorage, SegmentationStorage, RTStructureSetStorage
from pydicom.uid import ImplicitVRLittleEndian, JPEGExtended12Bit


class SendFiles:
    """
    Class for sending DICOM files to a destination PACS server.
    
    This class handles the DICOM network operations to send files to
    a remote PACS server using the DICOM protocol.
    """

    def __init__(self, dcm_path, dest_ip, dest_port, dest_aetitle):
        """
        Initialize the SendFiles processor.
        
        Args:
            dcm_path (str or Path): Path to the directory containing DICOM files to send
            dest_ip (str): IP address of the destination PACS server
            dest_port (int): Port number of the destination PACS server
            dest_aetitle (str): AE title of the destination PACS server
        """
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.dest_aetitle = dest_aetitle
        self.dcm_path = dcm_path

    def send_dicom_folder(self):
        """
        Send all DICOM files in the specified directory to the destination PACS server.
        
        This method:
        1. Initializes the DICOM Application Entity
        2. Establishes an association with the destination PACS server
        3. Performs a C-ECHO to verify connectivity
        4. Sends each DICOM file using C-STORE operations
        5. Releases the association when complete
        
        Returns:
            None
        """
        # Initialise the Application Entity
        ae = AE()

        # Add the CT image context for the 
        ae.add_requested_context(CTImageStorage, ImplicitVRLittleEndian)
        ae.add_requested_context(SecondaryCaptureImageStorage,JPEGExtended12Bit)
        ae.add_requested_context(SegmentationStorage, ImplicitVRLittleEndian)
        ae.add_requested_context(Verification)
        # ae.add_requested_context(RTStructureSetStorage)

        # Use pathlib for directory operations
        dcm_dir = Path(self.dcm_path)
        logger.info(f'Path to the DICOM directory: {dcm_dir}')

        # load the data
        dicom_paths = [p for p in dcm_dir.iterdir() if p.is_file()]
        
        assoc = ae.associate(
            self.dest_ip,
            self.dest_port,
            ae_title=self.dest_aetitle
        )

        if assoc.is_established:
            # Perform C-ECHO before sending
            echo_status = assoc.send_c_echo()
            if not echo_status or echo_status.Status != 0x0000:
                logger.error(f"C-ECHO test failed with status: {getattr(echo_status, 'Status', 'None')}. Aborting send.")
                assoc.release()
                return
            for cx in assoc.accepted_contexts:
                cx._as_scu = True
            for dicom_path in dicom_paths:
                ds = dcmread(dicom_path)
                # print(cx)
                # Use the C-STORE service to send the dataset
                # returns the response status as a pydicom Dataset
                status = assoc.send_c_store(ds)
                # print(ds)
                # Check the status of the storage request
                if status:
                    # If the storage request succeeded this will be 0x0000
                    #print('C-STORE request status: 0x{0:04x}'.format(status.Status))
                    pass
                else:
                    logger.error('Connection timed out, was aborted or received invalid response')
        else:
            logger.error(f'Association rejected, aborted or never connected {self.dest_aetitle} - {self.dest_ip}:{self.dest_port}')

        # Release the association
        assoc.release()
