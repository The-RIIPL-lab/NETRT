from pynetdicom import AE
from pynetdicom import *
import os
from pydicom import dcmread
from pynetdicom.sop_class import CTImageStorage, SecondaryCaptureImageStorage, SegmentationStorage, RTStructureSetStorage
from pydicom.uid import ImplicitVRLittleEndian, JPEGExtended12Bit


class SendFiles:

    def __init__(self, dcm_path, dest_ip, dest_port, dest_aetitle):
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.dest_aetitle = dest_aetitle
        self.dcm_path = dcm_path

    def send_dicom_folder(self):

        # Initialise the Application Entity
        ae = AE()

        # Add the CT image context for the 
        ae.add_requested_context(CTImageStorage, ImplicitVRLittleEndian)
        ae.add_requested_context(SecondaryCaptureImageStorage,JPEGExtended12Bit)
        ae.add_requested_context(SegmentationStorage, ImplicitVRLittleEndian)
        #ae.add_requested_context(RTStructureSetStorage)

        filepath = self.dcm_path
        print('Path to the DICOM directory: {}'.format(filepath))

        # load the data
        dicom_files = os.listdir(filepath)
        
        assoc = ae.associate(
            self.dest_ip,
            self.dest_port,
            ae_title=self.dest_aetitle
        )

        if assoc.is_established:
            for cx in assoc.accepted_contexts:
                cx._as_scu = True
            for dicom in dicom_files:
                ds = dcmread(os.path.join(filepath, dicom))
                # print(cx)
                # Use the C-STORE service to send the dataset
                # returns the response status as a pydicom Dataset
                status = assoc.send_c_store(ds)
                # print(ds)
                # Check the status of the storage request
                if status:
                    # If the storage request succeeded this will be 0x0000
                    print('C-STORE request status: 0x{0:04x}'.format(status.Status))
                else:
                    print('Connection timed out, was aborted or received invalid response')
        else:
            print(f'Association rejected, aborted or never connected {self.dest_aetitle} - {self.dest_ip}:{self.dest_port}')

        # Release the association
        assoc.release()
