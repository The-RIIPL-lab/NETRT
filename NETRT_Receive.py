import sys
from pathlib import Path
import argparse
import signal
import time
import threading
import random
import shutil
import pydicom
from pydicom.filewriter import dcmwrite
from pynetdicom.sop_class import Verification
import Contour_Addition
import Send_Files
import Add_Burn_In
import Segmentations
from logger_module import setup_logger

from pynetdicom import (
    AE, debug_logger, evt, AllStoragePresentationContexts, ALL_TRANSFER_SYNTAXES
)

# Create a logger instance
logger = setup_logger()

# parse commandline variables
message="""RIIPL Labs 2022-2025 - Inline DicomRT contour and dose report generator"""
logger.info('Start server')

# About this server
parser = argparse.ArgumentParser(description=message)
parser.add_argument('-p', type=int, default=11119)
parser.add_argument('-i', default="127.0.0.1")
parser.add_argument('-aet', help='AE title of this server', default='RIIPLRT')

# About the destination server
parser.add_argument('-dp', type=int, default=4242)
parser.add_argument('-dip', default="152.11.105.71")
parser.add_argument('-daet', help='AE title of this server', default='RADIORIIPL')

# Removed network validation argument to drop IP range checking

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
# Perform DICOM C-ECHO test to verify connectivity to destination AE
ae_echo = AE()
ae_echo.add_requested_context(Verification)
logger.info(f"Testing DICOM C-ECHO connectivity to {dest_aetitle} at {dest_ip}:{dest_port}")
assoc_echo = ae_echo.associate(dest_ip, dest_port, ae_title=dest_aetitle)
if assoc_echo.is_established:
    status_echo = assoc_echo.send_c_echo()
    assoc_echo.release()
    if not status_echo or status_echo.Status != 0x0000:
        logger.error(f"DICOM C-ECHO test failed with status: {getattr(status_echo, 'Status', 'None')}")
        sys.exit(1)
    logger.info("DICOM C-ECHO test succeeded")
else:
    logger.error("Failed to establish association for C-ECHO test")
    sys.exit(1)

# Set the deidentify variable by default
global DEIDENTIFY
if args.D == 'False' or args.D == False:
    DEIDENTIFY = False
else:
    DEIDENTIFY = True

if DEIDENTIFY == True:
    logger.info("Running in with de-identification flag ON.")
else:
    logger.info("Running in with de-identification flag OFF.")

def handle_echo(event):
    """
    Handle DICOM C-ECHO request.
    
    Args:
        event: The echo event
        
    Returns:
        int: Status code 0x0000 (Success)
    """
    logger.info("ECHO detected")
    return 0x0000

def handle_store(event):
    """
    Handle DICOM C-STORE request by saving received DICOM files to the appropriate directories.
    
    This function creates a directory structure for each study and saves the received
    DICOM files according to their type (RTSTRUCT vs other images). It uses pydicom’s
    save_as() to avoid the is_little_endian warning and speed up writes.
    """
    logger.info("C-STORE request: SOP Class %s / SOP Instance %s",
                event.dataset.SOPClassUID,
                event.dataset.SOPInstanceUID)
    try:
        # Build base study folder
        study_uid = event.dataset.StudyInstanceUID
        base_dir       = Path(f"UID_{study_uid}")
        dcm_folder     = base_dir / "DCM"
        struct_folder  = base_dir / "Structure"
        seg_folder     = base_dir / "Segmentations"
        for folder in (dcm_folder, struct_folder, seg_folder):
            folder.mkdir(parents=True, exist_ok=True)

        # Choose output folder based on SOP Class
        if event.file_meta.MediaStorageSOPClassUID.name == "RT Structure Set Storage":
            out_file = struct_folder / f"{event.request.AffectedSOPInstanceUID}.dcm"
        else:
            out_file = dcm_folder / f"{event.request.AffectedSOPInstanceUID}.dcm"

        # Prepare dataset for saving
        ds = event.dataset
        ds.file_meta = event.file_meta
        ds.save_as(out_file, 
                   implicit_vr=event.context.transfer_syntax.is_implicit_VR,
                   little_endian=event.context.transfer_syntax.is_little_endian
                )

        # Keep track of the latest study directory for release handling
        global _last_study_dir
        _last_study_dir = base_dir

        logger.info("Stored to %s", out_file)
    except Exception as err:
        logger.error("Failed to store DICOM: %s", err)

    # Return Success status
    return 0x0000

def handle_conn_close(event):
    """
    Handle a DICOM connection close event.
    
    Args:
        event: The connection close event
        
    Returns:
        int: Status code 0x0000 (Success)
    """
    logger.info("Connect close event detected")
    return 0x0000

def handler(a):
    """
    Handle completed sequence storage and process the stored DICOM files.
    
    This function serves as the main pipeline controller that:
    1. Generates unique IDs for the DICOM files
    2. Creates a random ID for de-identification if needed
    3. Processes the DICOM files through contour addition and burn-in
    4. Sends the processed files to the destination PACS
    
    Args:
        a: Path to the accession directory
        
    Returns:
        bool: True if processing completed successfully, False otherwise
    """
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
        letters = 'abcdfhjklmnopqrstvwxyz'
        RAND_ID = ''.join(random.choice(letters) for x in range(8)).upper()
        logger.info(f"Random ID is {RAND_ID}")
    else:
        RAND_ID=""

    # get most recently created folder since it errors out sometimes otherwise
    # all_subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
    # latest_subdir = max(all_subdirs, key=os.path.getmtime)
    # Convert latest_subdir to pathlib.Path
    latest_subdir = Path(a)

    # define path directories using pathlib
    base_dir = latest_subdir
    dcm_path = base_dir / 'DCM'
    struct_path = base_dir / 'Structure'
    seg_path = base_dir / 'Segmentations' 

    print(struct_path)

    # Ensure the Structure directory is not empty
    if not any(struct_path.iterdir()):
        logger.error("Empty directory")
        return False

    # Use the first structure file found
    struct_file = next(struct_path.iterdir())
    struct_path = struct_path / struct_file.name

    # 02/07/2025 - I am removing JPEG creation again because of alignment issues with the mask!!
    # # Create an instance of ContourExtraction with the path to the DCM files as argument
    # contour_extraction = ContourExtraction(dcm_path, struct_path)
    # print("START: Running Contour Extraction Process")
    # contours = contour_extraction.process()
    # print("END: Running Contour Extraction Process")

    # create an instance of ContourAddition with the paths to the DCM and structure files as arguments
    logger.info(f"De-identify is set to {DEIDENTIFY}")
    if DEIDENTIFY == True:
        addition = Contour_Addition.ContourAddition(dcm_path, struct_path, DEIDENTIFY, STUDY_INSTANCE_ID, CT_SOPInstanceUID, FOD_REF_ID, RAND_ID)
    else:
        addition = Contour_Addition.ContourAddition(dcm_path, struct_path, DEIDENTIFY, STUDY_INSTANCE_ID, CT_SOPInstanceUID, FOD_REF_ID)

    # Path to the Addition folder
    addition_path = base_dir / 'Addition'

    # run the main function on each instance
    logger.info("START: Running Mask Addition Process")
    addition.process()
    logger.info("END: Running Mask Addition Process")

    # Create Segmentations
    if DEIDENTIFY == False:
        logger.info("START: CREATING SEGMENTATION DICOMS")
        logger.debug(f"struct_path: {struct_path}")
        segmentation = Segmentations.Segmentations(dcm_path, struct_path, seg_path, DEIDENTIFY, STUDY_INSTANCE_ID)
        segmentation.process()
    
    # ALWAYS add the burn in disclaimer on the T1w images
    burn_in = Add_Burn_In.Add_Burn_In(addition_path)
    burn_in.apply_watermarks()
    
    logger.info("START: SENDING Masked DICOMS")
    send_files_overlay = Send_Files.SendFiles(addition_path, dest_ip, dest_port, dest_aetitle)
    send_files_overlay.send_dicom_folder()

    # The SEG file is created as an overlay on the original image. Thus, only available in deidenfied mode.
    # THIS DOES NOT HAVE "FOR RESEARCH USE ONLY APPENDED"
    if DEIDENTIFY == False:
        logger.info("START: SENDING DICOM SEG FILE")
        send_files_segmentations = Send_Files.SendFiles(seg_path, dest_ip, dest_port, dest_aetitle)
        send_files_segmentations.send_dicom_folder()

    # This assumes that the Structure image used for countour is already in PACS, but the RTSTRUCT is not. 
    # if DEIDENTIFY == False:
    #     print("START: SENDING RTSTRUCT DICOM")
    #     send_files_struct = Send_Files.SendFiles(os.path.join(latest_subdir, 'Structure'), dest_ip, dest_port, dest_aetitle)
    #     send_files_struct.send_dicom_folder()

    logger.info("END: Completing pipeline")
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
    logger.info("---- Stopping Server ----")
    
    sys.exit(0)

# return a list of directories that match the Accession Pattern
def find_accession_directories(my_dir: str):
    """
    Find accession directories under my_dir; each directory starting with 'UID_'
    and return the path to its 'DCM' subdirectory.
    """
    base_dir = Path(my_dir)
    accession_dirs = []
    for d in base_dir.iterdir():
        if d.is_dir() and d.name.startswith('UID_'):
            accession_dirs.append(d / 'DCM')
    return accession_dirs

def fileInDirectory(my_dir: str):
    """
    Return list of files (names) in the given directory.
    """
    dir_path = Path(my_dir)
    return [p.name for p in dir_path.iterdir() if p.is_file()]

# function comparing two lists
def listComparison(OriginalList: list, NewList: list):
    differencesList = [x for x in NewList if x not in OriginalList]
    return(differencesList)

def fileWatcher(watchDirectory: str, pollTime: int):
    """
    Watches a directory for new files and monitors download progress.
    
    Args:
        watchDirectory (str): Path to directory to monitor
        pollTime (int): Time in seconds between polls
        
    Returns:
        bool: True when download is complete
    """
    while True:
        if 'watching' not in locals():
            previousFileList = fileInDirectory(watchDirectory)
            watching = 1
        
        time.sleep(pollTime)
        newFileList = fileInDirectory(watchDirectory)
        fileDiff = listComparison(previousFileList, newFileList)
        previousFileList = newFileList

        if watching == 1 and len(fileDiff) > 0:
            logger.info(f"Downloading... {len(newFileList)}")

        if len(fileDiff) == 0:
            logger.info("Download complete")
            return True

def fileWatcherService(pd,currently_processing):
    if pd not in currently_processing:
        # Start the watcher
        logger.info(f"Now watching: {pd}")
        currently_processing.append(pd)
        result=fileWatcher(pd, 3)
        if result:
            logger.info(f"Dicom Directory: {pd}")
            # Determine absolute accession directory path
            abs_pd = Path(pd).parent.resolve()
            # Execute handler on the accession directory
            if handler(abs_pd):
                logger.info(f"Removing full Accession directory: {abs_pd}")
                #shutil.rmtree(abs_pd)
                currently_processing.remove(pd)
                return True
            else:
                logger.error("Unable to complete handler()")
                return False
    else:
        logger.info(f"{pd} is currently processing")
        return False

def main():
    # Create ae
    ae = create_new_application_entity()
    logger.info("Creating application entity")

    # Create a CTRL+C signal to stop the server
    signal.signal(signal.SIGINT, int_handler)

    # Start the server in a blocking way
    logger.info("---- Starting Server -----")
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
                    logger.info(f"New directory found: {pd}")
                    # Determine accession directory from DCM path
                    acc = Path(pd).parent
                    threads[acc] = threading.Thread(target=fileWatcherService,
                        args=(pd,currently_processing))
                    time.sleep(2)
                    threads[acc].start()
                    logger.info("Thread started")

        time.sleep(1)
        for t in list(threads.keys()):
            if threads[t].is_alive() == False:
                del threads[t]

        # Only log when there are active processing threads
        if threads:
            logger.info(f"Currently Processing {list(threads)[0]}")

logger.info(message)
logger.info(f"OPEN TO RECEIVE ON > {local_aetitle} IP: {local_ip}:{local_port}")
logger.info(f"FORWARDING TO > {dest_aetitle} IP: {dest_ip}:{dest_port}")

# Let's run the main function 
if __name__ == "__main__":
    main()
