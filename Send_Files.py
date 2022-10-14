#!/usr/bin/python
"""
Storage SCU example.

This demonstrates a simple application entity that support the RT Plan
Storage SOP Class as SCU. For this example to work, there must be an
SCP listening on the specified host and port.

For help on usage,
python storescu.py -h
"""

from pynetdicom import AE, StoragePresentationContexts
from pynetdicom import *
import os
from pydicom import dcmread
from pynetdicom import AE, debug_logger
from pynetdicom.sop_class import CTImageStorage, SecondaryCaptureImageStorage
from pydicom.uid import (
    ExplicitVRLittleEndian, ImplicitVRLittleEndian
)
import pydicom

from pydicom.filereader import read_dicomdir
from pydicom.data import get_testdata_files
import re

class SendFiles:

    def __init__(self, dcm_path, dest_ip='152.11.105.191', dest_port=8104, dest_aetitle="RIIPLXNAT"):
        self.dest_ip=dest_ip
        self.dest_port=dest_port
        self.dest_aetitle=dest_aetitle
        self.dcm_path = dcm_path

    def send_dicom_folder(self):
        #debug_logger()

        # Initialise the Application Entity
        ae = AE()

        # Add a requested presentation context
        ae.add_requested_context(CTImageStorage, ImplicitVRLittleEndian)
        ae.add_requested_context(SecondaryCaptureImageStorage, ExplicitVRLittleEndian)

        filepath = self.dcm_path

        print('Path to the DICOM directory: {}'.format(filepath))
        # load the data

        dicom_files = os.listdir(filepath)
        dicom_files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        for dicom in dicom_files:

            ds = dcmread(os.path.join(filepath, dicom))

            # Associate with peer AE at IP 127.0.0.1 and port 11112
            assoc = ae.associate(
                self.dest_ip, 
                self.dest_port,
                ae_title=self.dest_aetitle)

            if assoc.is_established:
                # Use the C-STORE service to send the dataset
                # returns the response status as a pydicom Dataset
                status = assoc.send_c_store(ds)

                # Check the status of the storage request
                if status:
                    # If the storage request succeeded this will be 0x0000
                    print('C-STORE request status: 0x{0:04x}'.format(status.Status))
                else:
                    print('Connection timed out, was aborted or received invalid response')

                # Release the association
                assoc.release()
            else:
                print('Association rejected, aborted or never connected')