import os, sys
import argparse
import signal
import time
import random
import shutil
from pydicom.filewriter import write_file_meta_info
from pydicom.uid import generate_uid
from pynetdicom.sop_class import Verification
import Contour_Addition
import Send_Files
import Add_Burn_In
#import Segmentations
import logging

from pynetdicom import (
    AE, debug_logger, evt, AllStoragePresentationContexts, ALL_TRANSFER_SYNTAXES
)

# Import the logging configuration
from logging_config import setup_logging

# Ensure the logger is set up
setup_logging()

# Create a logger instance for this script
logger = logging.getLogger('NETRT_Receive')

# Parse commandline variables
message = "RIIPL Labs 2022-2024 - Inline DicomRT contour and dose report generator"
logger.info(message)

parser = argparse.ArgumentParser(description=message)
parser.add_argument('-p', type=int, default=11112, help='Local port')
parser.add_argument('-i', default="127.0.0.1", help='Local IP address')
parser.add_argument('-aet', default='RIIPLRT', help='AE title of this server')

# About the destination server
parser.add_argument('-dp', type=int, default=8104, help='Destination port')
parser.add_argument('-dip', default="152.11.105.191", help='Destination IP address')
parser.add_argument('-daet', default='RIIPLXNAT', help='AE title of destination server')

# Add Deidentify
parser.add_argument('-D', action='store_true', help='Enable de-identification (default: True)')
args = parser.parse_args()

local_port = args.p
local_ip = args.i
local_aetitle = args.aet
dest_port = args.dp
dest_ip = args.dip
dest_aetitle = args.daet
DEIDENTIFY = args.D

if DEIDENTIFY:
    logger.info("Running in with de-identification flag ON.")
else:
    logger.info("Running in with de-identification flag OFF.")

def handle_echo(event):
    logger.info("ECHO detected")
    return 0x0000

def handle_store(event):
    try:
        extract_accession = f'UID_{event.dataset.StudyInstanceUID}'
        logger.info(f"Receiving {extract_accession}")
        extract_accession = os.path.join('.', extract_accession)
        
        if not os.path.isdir(extract_accession):
            os.makedirs(extract_accession, exist_ok=True)

        dcm_folder = os.path.join(extract_accession, 'DCM')
        structure_folder = os.path.join(extract_accession, 'Structure')
        #seg_folder = os.path.join(extract_accession, 'Segmentations')

        folder_list = [dcm_folder, structure_folder]
        for folder in folder_list:
            if not os.path.isdir(folder):
                logger.info(f"Creating {folder}")
                os.mkdir(folder)

        # Write structure file based on header metadata
        if 'Structure' in str(event.file_meta):
            fname = os.path.join(structure_folder, f'{event.request.AffectedSOPInstanceUID}.dcm')
        else:
            fname = os.path.join(dcm_folder, f'{event.request.AffectedSOPInstanceUID}.dcm')

        with open(fname, 'wb') as f:
            f.write(b'\x00' * 128)
            f.write(b'DICM')
            write_file_meta_info(f, event.file_meta)
            f.write(event.request.DataSet.getvalue())

    except Exception as err:
        logger.error(f"Error handling store event: {err}")
    return 0x0000

def handle_conn_close(event):
    logger.info("Connect close event detected")
    return 0x0000

def handler(a):
    try:
        STUDY_INSTANCE_ID = generate_uid()
        FOD_REF_ID = generate_uid()
        SC_SOPInstanceUID = generate_uid(prefix='1.2.840.10008.5.1.4.1.1.7.')
        CT_SOPInstanceUID = generate_uid(prefix='1.2.840.10008.5.1.4.1.1.2.')

        RAND_ID = ''.join(random.choice('abcdfhjklmnopqrstvwxyz') for x in range(8)) if DEIDENTIFY else ""

        latest_subdir = a
        dcm_path = os.path.join(latest_subdir, 'DCM')
        struct_path = os.path.join(latest_subdir, 'Structure')
        #seg_path = os.path.join(latest_subdir, 'Segmentations')

        if not os.listdir(struct_path):
            logger.warning("Empty directory")
            return False

        struct_file = os.listdir(struct_path)[0]
        struct_path = os.path.join(struct_path, struct_file)

        addition = Contour_Addition.ContourAddition(dcm_path, struct_path, DEIDENTIFY, STUDY_INSTANCE_ID, CT_SOPInstanceUID, FOD_REF_ID, RAND_ID) if DEIDENTIFY else \
                   Contour_Addition.ContourAddition(dcm_path, struct_path, DEIDENTIFY, STUDY_INSTANCE_ID, CT_SOPInstanceUID, FOD_REF_ID)
        
        addition_path = os.path.join(dcm_path, 'Addition')

        logger.info("START: Running Mask Addition Process")
        addition.process()
        logger.info("END: Running Mask Addition Process")

        #logger.info("START: CREATING SEGMENTATION DICOMS")
        #segmentation = Segmentations.Segmentations(dcm_path, struct_path, seg_path, STUDY_INSTANCE_ID)
        #segmentation.process()

        logger.info("START: Adding Image Burn In")
        burn_in = Add_Burn_In.Add_Burn_In(addition_path)
        burn_in.apply_watermarks()
        logger.info("END: Adding Image Burn In")

        logger.info("START: SENDING Masked DICOMS")
        send_files_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aetitle)
        send_files_overlay.send_dicom_folder()

        #logger.info("START: SENDING SEGMENTATION DICOMS")
        #send_files_segmentations = Send_Files.SendFiles(seg_path, dest_ip, dest_port, dest_aetitle)
        #send_files_segmentations.send_dicom_folder()

        logger.info("END: Completing pipeline")
    except Exception as err:
        logger.error(f"Error in handler: {err}")
        return False
    return True

handlers = [
    (evt.EVT_C_STORE, handle_store),
    (evt.EVT_C_ECHO, handle_echo),
    (evt.EVT_CONN_CLOSE, handle_conn_close)
]

def create_new_application_entity():
    ae = AE()
    ae.add_supported_context(Verification)
    for uid in [cx.abstract_syntax for cx in AllStoragePresentationContexts]:
        ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)
    return ae

def int_handler(signum, frame):
    logger.info("Server stopped by interrupt.")
    print("\n ---- Stopping Server ----")
    sys.exit(0)

def find_accession_directories(my_dir: str):
    return [os.path.join(d, 'DCM') for d in os.listdir(my_dir) if d.startswith('UID_')]

def fileInDirectory(my_dir: str):
    return [f for f in os.listdir(my_dir) if os.path.isfile(os.path.join(my_dir, f))]

def listComparison(OriginalList: list, NewList: list):
    return [x for x in NewList if x not in OriginalList]

def fileWatcher(watchDirectory: str, pollTime: int):
    previousFileList = fileInDirectory(watchDirectory)
    while True:
        time.sleep(pollTime)
        newFileList = fileInDirectory(watchDirectory)
        fileDiff = listComparison(previousFileList, newFileList)
        previousFileList = newFileList

        if fileDiff:
            print(f"Downloading... {len(newFileList)} files", end="\r")
        else:
            print("Download Complete")
            return True

def fileWatcherService(pd, currently_processing):
    logger.info(f"watching: {pd}")
    currently_processing.append(pd)
    result = fileWatcher(pd, 10)
    logger.debug(f"fileWatcher result for {pd}: {result}")
    if result:
        abs_pd = os.path.join(os.getcwd(), os.path.dirname(pd))
        logger.debug(f"Handler called with absolute path: {abs_pd}")
        if handler(abs_pd):
            logger.info("Objective complete! Removing DICOM data.")
            shutil.rmtree(abs_pd)  # Remove the directory after processing
            currently_processing.remove(pd)
            return True
        else:
            logger.error("X: DEBUG error. unable to complete handler.")
    else:
        logger.error(f"Error in fileWatcherService for {pd}")
    return False

def main():
    ae = create_new_application_entity()
    logger.info("Creating application entity")

    signal.signal(signal.SIGINT, int_handler)

    print("\n ---- Starting Server -----")
    service = ae.start_server(
        (local_ip, local_port), 
        evt_handlers=handlers, 
        block=False, 
        ae_title=local_aetitle
    )

    currently_processing = []
    threads = {}
    
    try:
        while True:
            processing_dirs = find_accession_directories(".")
            logger.debug(f"Processing directories found: {processing_dirs}")
            for pd in processing_dirs:
                if fileWatcherService(pd, currently_processing):
                    logger.info(f"Completed processing: {pd}")

            time.sleep(1)

            # Remove finished threads
            for t in list(threads.keys()):
                if not threads[t].is_alive():
                    del threads[t]
                    logger.debug(f"Removed thread for {t}")
                    
            print(f"Currently Processing: {list(threads.keys())}", end="\r")
    
    except KeyboardInterrupt:
        logger.info("Server stopped by interrupt.")
        sys.exit(0)
    finally:
        service.shutdown()

if __name__ == "__main__":
    main()
