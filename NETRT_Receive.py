from genericpath import isdir
from logging.handlers import WatchedFileHandler
from multiprocessing import cpu_count
import os, sys
import argparse
from unicodedata import name
from pydicom.filewriter import write_file_meta_info
from pydicom import dcmread
from pydicom.uid import generate_uid
import numpy as np
# from rt_utils import RTStructBuilder
import matplotlib.pyplot as plt
from pynetdicom.sop_class import Verification
from pynetdicom import _config
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
import shutil
import threading
import random
import string


# Dump raw data into file
#_config.STORE_RECV_CHUNKED_DATASET = True

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
parser.add_argument('-dip', default="152.11.105.191")
parser.add_argument('-daet', help='AE title of this server', default='RIIPLXNAT')

# Add
parser.add_argument('-D', default=False)

# Verbose mode versus not
parser.add_argument('-v', default=False)
args = parser.parse_args()

# Define these variables with better names
local_port = args.p
local_ip = args.i
local_aetitle = args.aet
dest_port = args.dp
dest_ip = args.dip
dest_aetitle = args.daet

global DEBUG
DEBUG = args.D

# If started with verbose flag,
# run in debug mode
if args.v:
    print(" > Verbose mode is on.")
    debug_logger()

if args.D:
    print(" > DEBUG mode is on. \nUID information will be removed and Patient Info will be modified ")

def handle_echo(event):
    print(" > Echo event!", end='\n')
    return 0x0000


def handle_store(event):

    try:
        # Create a new accession folder
        extract_accession = f'Accession_{event.dataset.AccessionNumber}'
        extract_accession = os.path.join('.', extract_accession)
        
        if os.path.isdir(extract_accession) == False:
            print("\nCreating folder: %s" % extract_accession)
            os.makedirs(extract_accession, exist_ok=True)

        # get the paths to the DCM and structure files
        dcm_folder = os.path.join(extract_accession, 'DCM')
        structure_folder = os.path.join(extract_accession, 'Structure')
        jpeg_folder = os.path.join(extract_accession, 'JPEG_Dicoms')

        # make the folders
        folder_list=[ dcm_folder, structure_folder, jpeg_folder ]
        for folder in folder_list:
            if os.path.isdir(folder)==False:
                print("Creating %s" % folder)
                os.mkdir(folder)

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

    return 0x0000

"""Handle a CONN_CLOSE event"""
def handle_conn_close(event):
    #address, sequence_num = event.address
    #sequence_nums.append(sequence_num)
    return 0x0000

"""Handle completed sequence storage"""
def handler(a):

    # Announce the pipeline
    print("Starting pipeline")

    if DEBUG:
        global RAND_ID
        RAND_ID=''.join(random.choice(string.ascii_letters) for x in range(8))
        print("RANDOM ID is %s" % RAND_ID)
    else:
        RAND_ID=""

    if DEBUG:
        RAND_UID=generate_uid(entropy_srcs=[RAND_ID])
        print(RAND_UID)

    # get most recently created folder since it errors out sometimes otherwise
    #all_subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
    #latest_subdir = max(all_subdirs, key=os.path.getmtime)

    latest_subdir=a

    # get the path to the DCM folder
    dcm_path = os.path.join(latest_subdir, 'DCM')

    # get the path to the structure file
    struct_path = os.path.join(latest_subdir, 'Structure')
    print("DEBUG")
    print(os.listdir(struct_path))
    struct_file = os.listdir(struct_path)[0]
    struct_path = os.path.join(struct_path, struct_file)

    # create an instance of ContourAddition and ContourExtraction with the paths to the DCM and structure files as arguments
    addition = Contour_Addition.ContourAddition(dcm_path, struct_path, DEBUG, RAND_ID, RAND_UID)
    extraction = Contour_Extraction.ContourExtraction(dcm_path, struct_path) 

    jpeg_path = os.path.join(latest_subdir, 'JPEG_Dicoms')
    extraction_path = os.path.join(latest_subdir, 'Extraction')
    addition_path = os.path.join(latest_subdir, 'Addition')

    convert_jpeg_to_dicom = JPEGToDicom.JPEGToDICOM_Class(jpeg_path, extraction_path,
    dcm_path, DEBUG, RAND_ID, RAND_UID)

    # run the main function on each instance
    addition.process()
    extraction.process()
    convert_jpeg_to_dicom.process()
    
    send_files_jpeg = Send_Files.SendFiles(jpeg_path, dest_ip, dest_port, dest_aetitle)
    send_files_jpeg.send_dicom_folder()
    
    send_files_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aetitle)
    send_files_overlay.send_dicom_folder()
    print("Completing pipeline")
    return True

handlers = [
    (evt.EVT_C_STORE, handle_store),
    (evt.EVT_C_ECHO, handle_echo),
    (evt.EVT_CONN_CLOSE, handle_conn_close)
    ]

"""Returns a new Application Entity with supported contexts"""
def create_new_application_entity():
    ae = AE()
    ae.add_supported_context(Verification)
    storage_sop_classes = [cx.abstract_syntax for cx in AllStoragePresentationContexts]
    for uid in storage_sop_classes:
        ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)
    return ae

def int_handler(signum, frame):
    print("\n ---- Stopping Server ----")
    sys.exit(0)

# return a list of directories that match the Accession Pattern
def find_accession_directories(my_dir:str):
    Accession_directories = [os.path.join(d,'DCM') for d in os.listdir(my_dir) if d.startswith('Accession')]
    return(Accession_directories)

def fileInDirectory(my_dir: str):
    onlyfiles = [f for f in os.listdir(my_dir) if os.path.isfile(os.path.join(my_dir, f))]
    return(onlyfiles)

# function comparing two lists
def listComparison(OriginalList: list, NewList: list):
    differencesList = [x for x in NewList if x not in OriginalList]
    return(differencesList)

def fileWatcher(watchDirectory: str, pollTime: int):
    while True:
        if 'watching' not in locals(): 
            previousFileList = fileInDirectory(watchDirectory)
            watching = 1
        
        time.sleep(pollTime)
        newFileList = fileInDirectory(watchDirectory)
        fileDiff = listComparison(previousFileList, newFileList)
        previousFileList = newFileList

        if watching == 1 & len(fileDiff) > 0:
            print("Downloading... {}".format(len(newFileList)), end="\r")

        if len(fileDiff) == 0:
            print("Download Complete")
            return True

def fileWatcherService(pd,currently_processing):
    if pd not in currently_processing:
        # Start the watcher
        print(" - Now watching: {}".format(pd))
        currently_processing.append(pd)
        result=fileWatcher(pd, 3)
        if result:
            print(" > Dicom Directory: %s" % pd)
            abs_pd=os.path.join(
                os.getcwd(),
                os.path.dirname(pd))
            if handler(abs_pd):
                print(" > Removing full Accession directory")
                shutil.rmtree(abs_pd)
                currently_processing.remove(pd)
                return True
            else:
                print(" X: DEBUG error. unable to complete handler()")
                return False
    else:
        print("{} is currently processing".format(pd))
        return False

def main():

    ae = create_new_application_entity()

    # Create a CTRL+C signal to stop the server
    signal.signal(signal.SIGINT, int_handler)

    # Start the server in a blocking way
    print(" ---- Starting Server -----")
    service = ae.start_server(
        (local_ip, local_port), 
        evt_handlers=handlers, 
        block=False, 
        ae_title=local_aetitle)

    global currently_processing
    currently_processing=[]
    threads={}
    while True:

        # Get a list of Accession directories
        processing_dirs = find_accession_directories(".")
        if len(processing_dirs) > 0:
            for pd in processing_dirs:
                if pd not in currently_processing:
                    print("\n > New directory found: %s" % pd)
                    acc=os.path.dirname(pd)
                    threads[acc] = threading.Thread(target=fileWatcherService,
                        args=(pd,currently_processing))
                    time.sleep(1)
                    threads[acc].start()
                    print("\n --- Thread started ---")

        time.sleep(1)
        for t in list(threads.keys()):
            if threads[t].is_alive() == False:
                del threads[t]

        print("Currently Processing {}".format(list(threads)), end="\r")
        


        # if length of received files is greater than 0, execute this block
        # if len(sequence_nums) > 0:
        #     count += 1
        #     # if length of received files is less than count, execute this block
        #     if count > len(sequence_nums):
        #         print("Executing Handler")
        #         #handler('a', 'b')

print("\n",message)
print(""" - OPEN TO RECIEVE ON > {} IP: {}:{}""".format(local_aetitle,local_ip, local_port))
print(""" - FORWARDING TO > {} IP: {}:{}""".format(dest_aetitle, dest_ip, dest_port))

# Let's run the main function 
if __name__ == "__main__":
    main()
