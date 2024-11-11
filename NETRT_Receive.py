import os, sys
import argparse
import signal
import time
import threading
import random
import shutil
import pydicom
from pydicom.filewriter import write_file_meta_info
from pydicom import dcmread
from pydicom.uid import generate_uid
from pynetdicom.sop_class import Verification
import Contour_Addition
import Send_Files
import Add_Burn_In
#import Reorient_Dicoms
import Segmentations
import logging

from pynetdicom import (
    AE, debug_logger, evt, AllStoragePresentationContexts, ALL_TRANSFER_SYNTAXES
)

# create a basic logger
logging.basicConfig(
    level=logging.INFO,  # Set the desired logging level
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('NETRT.log'),  # Save log messages to a file
    ]
)

# Create a logger instance
logger = logging.getLogger('NETRT')

# parse commandline variables
message="""RIIPL Labs 2022-2024 - Inline DicomRT contour and dose report generator"""
logger.info('Start server')

# About this server
parser = argparse.ArgumentParser(description=message)
parser.add_argument('-p', type=int, default=11112)
parser.add_argument('-i', default="127.0.0.1")
parser.add_argument('-aet', help='AE title of this server', default='RIIPLRT')

# About the destination server
parser.add_argument('-dp', type=int, default=8104)
parser.add_argument('-dip', default="152.11.105.191")
parser.add_argument('-daet', help='AE title of this server', default='RIIPLXNAT')

# Add Deidentify
parser.add_argument('-D', default=True)
args = parser.parse_args()

# Define these variables with better names
local_port = args.p
local_ip = args.i
local_aetitle = args.aet
dest_port = args.dp
dest_ip = args.dip
dest_aetitle = args.daet
# Set the deidentify variable by default
global DEIDENTIFY
DEIDENTIFY = args.D

if DEIDENTIFY == True:
    logger.info("Running in with de-identification flag ON.")
else:
    logger.info("Running in with de-identification flag OFF.")

def handle_echo(event):
    logger.info("ECHO detected")
    return 0x0000

def handle_store(event):
    logger.info("Handle event detected")
    try:
        # Create a new accession folder
        extract_accession = f'UID_{event.dataset.StudyInstanceUID}'
        logger.info("Receiving {}".format(extract_accession))
        extract_accession = os.path.join('.', extract_accession)
        
        if os.path.isdir(extract_accession) == False:
            os.makedirs(extract_accession, exist_ok=True)

        # get the paths to the DCM and structure files
        dcm_folder = os.path.join(extract_accession, 'DCM')
        structure_folder = os.path.join(extract_accession, 'Structure')
        seg_folder = os.path.join(extract_accession, 'Segmentations')

        # make the folders
        folder_list=[ dcm_folder, structure_folder]
        for folder in folder_list:
            if os.path.isdir(folder)==False:
                logger.info("Creating %s" % folder)
                os.mkdir(folder)

        # get most recently created parent folder since it errors out sometimes otherwise
        all_subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
        latest_subdir = max(all_subdirs, key=os.path.getmtime)

        dcm_folder = os.path.join(latest_subdir, 'DCM')
        structure_folder = os.path.join(latest_subdir, 'Structure')
        seg_folder = os.path.join(latest_subdir, 'Segmentations')

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
    logger.info("Connect close event detected")
    return 0x0000

"""Handle completed sequence storage"""
def handler(a):
    logger.info("Handler event detected. Starting pipeline")

    # Storage Type: Secondary Capture Image Storage
    # This should be consistent for all SCAN SERIES in the SESSION
    STUDY_INSTANCE_ID = pydicom.uid.generate_uid()
    FOD_REF_ID= pydicom.uid.generate_uid()

    # This should be the MEDIA Storage SOP (instance, not class). 
    # Consistent consistent within the file but different between scan series
    SC_SOPInstanceUID = pydicom.uid.generate_uid(prefix='1.2.840.10008.5.1.4.1.1.7.')

    # Storage Type: CT Image Storage
    CT_SOPInstanceUID = pydicom.uid.generate_uid(prefix='1.2.840.10008.5.1.4.1.1.2.')

    # Create a new random id
    if DEIDENTIFY:
        global RAND_ID
        letters='abcdfhjklmnopqrstvwxyz'
        RAND_ID=''.join(random.choice(letters) for x in range(8))
        print("RANDOM ID is %s" % RAND_ID)
    else:
        RAND_ID=""

    # get most recently created folder since it errors out sometimes otherwise
    # all_subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
    # latest_subdir = max(all_subdirs, key=os.path.getmtime)
    latest_subdir=a

    # get the path to the DCM folder
    dcm_path = os.path.join(latest_subdir, 'DCM')

    # get the path to the structure file
    struct_path = os.path.join(latest_subdir, 'Structure')

    seg_path = os.path.join(latest_subdir, 'Segmentations')

    if len(os.listdir(struct_path)) == 0:
        print("Empty directory")
        return False

    # Potential Error point: Missing Structure file
    struct_file = os.listdir(struct_path)[0]
    struct_path = os.path.join(struct_path, struct_file)


    # create an instance of ContourAddition and ContourExtraction with the paths to the DCM and structure files as arguments
    if DEIDENTIFY:
        addition = Contour_Addition.ContourAddition(dcm_path, struct_path, DEIDENTIFY, STUDY_INSTANCE_ID, CT_SOPInstanceUID, FOD_REF_ID, RAND_ID)
    else:
        addition = Contour_Addition.ContourAddition(dcm_path, struct_path, DEIDENTIFY, STUDY_INSTANCE_ID, CT_SOPInstanceUID, FOD_REF_ID)

    addition_path = os.path.join(latest_subdir, 'Addition')

    # run the main function on each instance
    print("START: Running Mask Addition Process")
    addition.process()
    print("END: Running Mask Addition Process")

    # Create Segmentations
    print("START: CREATING SEGMENTATION DICOMS")
    print(f"struct_path is: {struct_path}")
    segmentation = Segmentations.Segmentations(dcm_path, struct_path, seg_path , STUDY_INSTANCE_ID)
    segmentation.process()
        
    #reorient = Reorient_Dicoms.Reorient_Dicoms(addition_path)
    #reorient.reorient_driver()
    
    burn_in = Add_Burn_In.Add_Burn_In(addition_path)
    burn_in.apply_watermarks()
    
    print("START: SENDING Masked DICOMS")
    send_files_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aetitle)
    send_files_overlay.send_dicom_folder()

    # print("START: SENDING Masked DICOMS")
    send_files_segmentations = Send_Files.SendFiles(seg_path, dest_ip, dest_port, dest_aetitle)
    send_files_segmentations.send_dicom_folder()

    # print("START: SENDING RTSTRUCT DICOM")
    # send_files_struct = Send_Files.SendFiles(os.path.join(latest_subdir, 'Structure'), dest_ip, dest_port, dest_aetitle)
    # send_files_struct.send_dicom_folder()

    print("END: Completing pipeline")
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
    logger.info("Server stopped by interrupt.")
    print("\n ---- Stopping Server ----")
    
    sys.exit(0)

# return a list of directories that match the Accession Pattern
def find_accession_directories(my_dir:str):
    Accession_directories = [os.path.join(d,'DCM') for d in os.listdir(my_dir) if d.startswith('UID_')]
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
            abs_pd=os.path.join(os.getcwd(), os.path.dirname(pd))
            if handler(abs_pd):
                print(" > Removing full Accession directory")
                sys.exit(0)  
                currently_processing.remove(pd)
                return True
            else:
                print(" X: DEBUG error. unable to complete handler()")
                logger.error("Unable to complete handler()")
                return False
    else:
        print("{} is currently processing".format(pd))
        return False

def main():

    # Create ae 
    ae = create_new_application_entity()
    logger.info("Creating application entity")

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

print("\n",message)
print(""" - OPEN TO RECEIVE ON > {} IP: {}:{}""".format(local_aetitle,local_ip, local_port))
print(""" - FORWARDING TO > {} IP: {}:{}""".format(dest_aetitle, dest_ip, dest_port))

# Let's run the main function 
if __name__ == "__main__":
    main()
