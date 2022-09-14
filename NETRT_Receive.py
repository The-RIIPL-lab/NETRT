import os
import argparse
from unicodedata import name
from pydicom.filewriter import write_file_meta_info
from pydicom import dcmread
import numpy as np
# from rt_utils import RTStructBuilder
import matplotlib.pyplot as plt
from pynetdicom.sop_class import Verification
import signal
import time
import re
import Contour_Addition
import Contour_Extraction
import Send_Files
import JPEGToDicom
import PIL.Image
import numpy as np
import pydicom

from pynetdicom import (
    AE, debug_logger, evt, AllStoragePresentationContexts,
    ALL_TRANSFER_SYNTAXES
)

# parse commandline variables
message="""RIIPL Labs 2022 - Inline DicomRT contour and dose report generator"""

# About this server
parser = argparse.ArgumentParser(description=message)
parser.add_argument('-p', type=int, default=11112)
parser.add_argument('-i', default="152.11.105.224")
parser.add_argument('-aet', help='AE title of this server', default='RIIPLRT')

# About the destination server
parser.add_argument('-dp', type=int, default=9003)
parser.add_argument('-dip', default="ansirxnat.medeng.wfubmc.edu")
parser.add_argument('-daet', help='AE title of this server', default='TEST')
parser.add_argument('-v', default=False)
args = parser.parse_args()

# Define these variables with better names
local_port = args.p
local_ip = args.i
local_aetitle = args.aet
dest_port = args.dp
dest_ip = args.dip
dest_aetitle = args.daet

sequence_nums = []

# If started with verbose flag,
# run in debug mode
if args.v:
    print(" > Verbose mode is on.")
    debug_logger()


def handle_echo(event):
    """Handle a C-ECHO request event."""
    return 0x0000


def handle_store(event):
    try:
        # make folders only if the number of files received is less than one
        if len(sequence_nums) < 1:
            extract_accession = f'Accession_{event.dataset.AccessionNumber}'

            os.makedirs(extract_accession, exist_ok=True)

            # get the paths to the DCM and structure files
            dcm_folder = os.path.join(extract_accession, 'DCM')
            structure_folder = os.path.join(extract_accession, 'Structure')
            jpeg_folder = os.path.join(extract_accession, 'JPEG_Dicoms')

            # make the folders
            os.makedirs(dcm_folder)
            os.makedirs(structure_folder)
            os.makedirs(jpeg_folder)

        # get most recently created parent folder since it errors out sometimes otherwise
        all_subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
        latest_subdir = max(all_subdirs, key=os.path.getmtime)

        dcm_folder = os.path.join(latest_subdir, 'DCM')
        structure_folder = os.path.join(latest_subdir, 'Structure')

        # write structure file based on header metadata
        if 'Structure' in str(event.file_meta):

            fname = os.path.join(structure_folder, f'{event.request.AffectedSOPInstanceUID}.dcm')

            with open(fname, 'wb') as f:

                # Write the preamble, prefix and file meta information elements
                f.write(b'\x00' * 128)
                f.write(b'DICM')

                write_file_meta_info(f, event.file_meta)

                # Write the raw encoded dataset
                f.write(event.request.DataSet.getvalue())

        # write all other DCM files if they are not the structure file
        else:

            fname = os.path.join(dcm_folder, f'{event.request.AffectedSOPInstanceUID}.dcm')

            with open(fname, 'wb') as f:

                # Write the preamble, prefix and file meta information elements
                f.write(b'\x00' * 128)
                f.write(b'DICM')

                write_file_meta_info(f, event.file_meta)

                # Write the raw encoded dataset
                f.write(event.request.DataSet.getvalue())

        f.close()

    except Exception as err:
        print(err)

    print(' - Storage complete')
    return 0x0000


def handle_conn_close(event):
    """Handle a CONN_CLOSE event"""
    # print("Closing connection with IP Address: ", event.address)
    address, sequence_num = event.address

    sequence_nums.append(sequence_num)

    return sequence_nums


def handler(a, b):

    # print a message to the console
    # print("\nShut er down")

    # shutdown the application
    ae.shutdown()

    # get most recently created folder since it errors out sometimes otherwise
    all_subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
    latest_subdir = max(all_subdirs, key=os.path.getmtime)

    # get the path to the DCM folder
    dcm_path = os.path.join(latest_subdir, 'DCM')

    # get the path to the structure file
    struct_path = os.path.join(latest_subdir, 'Structure')
    struct_file = os.listdir(struct_path)[0]
    struct_path = os.path.join(struct_path, struct_file)

    # create an instance of ContourAddition and ContourExtraction with the paths to the DCM and structure files as arguments
    addition = Contour_Addition.ContourAddition(dcm_path, struct_path)
    extraction = Contour_Extraction.ContourExtraction(dcm_path, struct_path)

    jpeg_path = os.path.join(latest_subdir, 'JPEG_Dicoms')
    extraction_path = os.path.join(latest_subdir, 'Extraction')
    addition_path = os.path.join(latest_subdir, 'Addition')

    convert_jpeg_to_dicom = JPEGToDicom.JPEGToDICOM_Class(jpeg_path, extraction_path, dcm_path)

    # run the main function on each instance
    addition.process()
    extraction.process()
    convert_jpeg_to_dicom.process()
    
    send_files_jpeg = Send_Files.SendFiles(jpeg_path)
    send_files_jpeg.send_dicom_folder()
    
    send_files_overlay = Send_Files.SendFiles(addition_path)
    send_files_overlay.send_dicom_folder()

    print(" - ")
    return True


handlers = [
    (evt.EVT_C_STORE, handle_store),
    (evt.EVT_C_ECHO, handle_echo),
    (evt.EVT_CONN_CLOSE, handle_conn_close)
    ]

# The main process is intended to 
def main():

    # Create a new application entity to handle incoming images
    global ae
    ae = AE()
    ae.add_supported_context(Verification)
    storage_sop_classes = [cx.abstract_syntax for cx in AllStoragePresentationContexts]

    # add the various CT and MR contexts
    for uid in storage_sop_classes:
        ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)

    # Start the server in a non-blocking way
    service = ae.start_server((local_ip, local_port), evt_handlers=handlers, block=False, ae_title=local_aetitle)

    # Define a signal handler
    signal.signal(signal.SIGINT, handler)
    count = 0

    while True:
        print(f"{count}", end="\r", flush=True)
        time.sleep(0.2)

        # if length of received files is greater than 0, execute this block
        if len(sequence_nums) > 0:

            count += 1

            # if length of received files is less than count, execute this block
            if count > len(sequence_nums):
                handler('a', 'b')


print("\n",message, """
 - local_port : {}
 - local_ip : {}
 - local_aetitle : {}
 - dest_port : {}
 - nest_ip : {}
 - dest_aetitle""".format(local_port, local_ip, local_aetitle, dest_port, dest_ip))

main()