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
from pynetdicom.sop_class import CTImageStorage, MRImageStorage
from pydicom.uid import ExplicitVRLittleEndian
from pydicom.uid import ImplicitVRLittleEndian, JPEGBaseline, ExplicitVRBigEndian
from pydicom.uid import (
    ExplicitVRLittleEndian, ImplicitVRLittleEndian,
    ExplicitVRBigEndian, DeflatedExplicitVRLittleEndian
)
import pydicom

from pydicom.filereader import read_dicomdir
from pydicom.data import get_testdata_files
import re

class SendFiles:

    def __init__(self, dcm_path):
        self.dcm_path = dcm_path

    def send_dicom_folder(self):
        debug_logger()

        # Initialise the Application Entity
        ae = AE()

        # Add a requested presentation context
        ae.add_requested_context(CTImageStorage, ImplicitVRLittleEndian)

        filepath = self.dcm_path

        print('Path to the DICOM directory: {}'.format(filepath))
        # load the data

        dicom_files = os.listdir(filepath)
        dicom_files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))

        for dicom in dicom_files:

            ds = dcmread(os.path.join(filepath, dicom))

            # ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian

            # Associate with peer AE at IP 127.0.0.1 and port 11112
            assoc = ae.associate("152.11.105.191", 8104, ae_title='RIIPL-DICOM')

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