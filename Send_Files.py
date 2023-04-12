from pynetdicom import AE, debug_logger
# StoragePresentationContexts, build_role, build_context, debug_logger
from pynetdicom import *
import os
from pydicom import dcmread
from pynetdicom.sop_class import CTImageStorage, SecondaryCaptureImageStorage
from pydicom.uid import ImplicitVRLittleEndian, JPEGExtended


class SendFiles:

    def __init__(self, dcm_path, dest_ip='152.11.105.191', dest_port=8104, dest_aetitle="RIIPLXNAT"):
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.dest_aetitle = dest_aetitle
        self.dcm_path = dcm_path

    def send_dicom_folder(self):

        debug_logger()

        # Initialise the Application Entity
        ae = AE()

        # Add the CT image context for the 
        # ExplicitVRLittleEndian = '1.2.840.10008.1.2.1'
        # JPEGExtended='1.2.840.10008.1.2.4.51'
        ae.add_requested_context(CTImageStorage, ImplicitVRLittleEndian)
        ae.add_requested_context(SecondaryCaptureImageStorage, JPEGExtended)

        filepath = self.dcm_path
        print('Path to the DICOM directory: {}'.format(filepath))

        # load the data
        dicom_files = os.listdir(filepath)
        # Associate with peer AE at IP 127.0.0.1 and port 11112
        assoc = ae.associate(
            self.dest_ip,
            self.dest_port,
            ae_title=self.dest_aetitle,
            # contexts=selected_contexts,
            # ext_neg=negotiation_items
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
                print(ds)
                # Check the status of the storage request
                if status:
                    # If the storage request succeeded this will be 0x0000
                    print('C-STORE request status: 0x{0:04x}'.format(status.Status))
                else:
                    print('Connection timed out, was aborted or received invalid response')
        else:
            print('Association rejected, aborted or never connected')

        # Release the association
        assoc.release()
