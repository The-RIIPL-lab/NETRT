# netrt_core/file_system_manager.py

import os
import shutil
import logging
import time
import pydicom
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class NewStudyEventHandler(FileSystemEventHandler):
    """Handles file system events to detect newly completed studies."""
    def __init__(self, file_system_manager, study_processor_callback):
        super().__init__()
        self.fsm = file_system_manager
        self.study_processor_callback = study_processor_callback
        # Use a dictionary to track activity in study directories and debounce
        self.study_activity_timers = {}
        self.debounce_interval = self.fsm.config.get("watcher", {}).get("debounce_interval_seconds", 7 )
        self.min_file_count_for_processing = self.fsm.config.get("watcher", {}).get("min_file_count_for_processing", 5 )

    def _is_processing_output_dir(self, path):
        """Check if path is in a processing output directory that should be ignored for triggering."""
        path_parts = path.split(os.sep)
        # Check if any part of the path contains these directory names
        return any(part in ["Addition", "Segmentations"] for part in path_parts)

    def _is_study_directory(self, path):
        return os.path.isdir(path) and os.path.basename(path).startswith("UID_")

    def _get_study_uid_from_path(self, path):
        basename = os.path.basename(path)
        if basename.startswith("UID_"):
            return basename[4:] # Remove "UID_"
        return None

    def _check_and_process_study(self, study_path):
        study_uid = self._get_study_uid_from_path(study_path)
        if not study_uid:
            return

        # Basic check: does DCM and Structure (if expected) exist?
        dcm_dir = os.path.join(study_path, "DCM")
        # struct_dir = os.path.join(study_path, "Structure") # Not all studies might have RTSTRUCT initially

        if not os.path.isdir(dcm_dir) or not os.listdir(dcm_dir):
            logger.debug(f"Debounce check: DCM directory for {study_uid} is still empty or not found. Waiting.")
            return
        
        # Count total files in DCM and Structure to ensure some content
        total_files = 0
        if os.path.isdir(dcm_dir):
            total_files += len([f for f in os.listdir(dcm_dir) if os.path.isfile(os.path.join(dcm_dir, f))])
        struct_dir = os.path.join(study_path, "Structure")
        if os.path.isdir(struct_dir):
            total_files += len([f for f in os.listdir(struct_dir) if os.path.isfile(os.path.join(struct_dir, f))])

        if total_files < self.min_file_count_for_processing:
            logger.debug(f"Debounce check: Study {study_uid} has only {total_files} files, less than min {self.min_file_count_for_processing}. Waiting.")
            return

        # Check if study is already being processed and acquire lock
        if self.fsm.is_study_being_processed(study_uid):
            logger.info(f"Study {study_uid} is already being processed. Skipping duplicate processing.")
            return

        if not self.fsm.acquire_study_lock(study_uid):
            logger.info(f"Could not acquire lock for study {study_uid}. It may be in processing by another thread.")
            return

        logger.info(f"Debounce interval ended for study {study_uid}. Triggering processing.")
        if study_uid in self.study_activity_timers: # Ensure it was being tracked
            del self.study_activity_timers[study_uid] # Remove timer
            
            try:
                # Call the study processor
                self.study_processor_callback(study_uid)
            except Exception as e:
                logger.error(f"Error during study processing for {study_uid}: {e}", exc_info=True)
            finally:
                # Always release the lock when done
                self.fsm.release_study_lock(study_uid)

    def _start_debounce_timer(self, study_path):
        study_uid = self._get_study_uid_from_path(study_path)
        if not study_uid:
            return

        if study_uid in self.study_activity_timers:
            self.study_activity_timers[study_uid].cancel() # Cancel existing timer
        
        timer = threading.Timer(self.debounce_interval, self._check_and_process_study, args=[study_path])
        self.study_activity_timers[study_uid] = timer
        timer.start()
        logger.debug(f"Started debounce timer for study {study_uid} in path {study_path}")

    def on_created(self, event):
        super().on_created(event)
        # Handle creation of new study directories UID_*
        if event.is_directory and self._is_study_directory(event.src_path):
            logger.info(f"New study directory created: {event.src_path}")
            self._start_debounce_timer(event.src_path)
        elif not event.is_directory:
            # Ignore files in processing output directories
            if self._is_processing_output_dir(event.src_path):
                logger.debug(f"Ignoring file creation event in processing directory: {event.src_path}")
                return
                
            # A file was created. Check if it is within a known study directory.
            study_dir = os.path.dirname(os.path.dirname(event.src_path))
            if self._is_study_directory(study_dir):
                logger.debug(f"File created in study {study_dir}: {event.src_path}")
                self._start_debounce_timer(study_dir)

    def on_modified(self, event):
        super().on_modified(event)
        # Often, directory modification events are more reliable for knowing when contents are settled.
        if event.is_directory and self._is_study_directory(event.src_path):
            logger.debug(f"Study directory modified: {event.src_path}")
            self._start_debounce_timer(event.src_path)
        elif not event.is_directory:
            # Ignore files in processing output directories
            if self._is_processing_output_dir(event.src_path):
                logger.debug(f"Ignoring file modification event in processing directory: {event.src_path}")
                return
                
            study_dir = os.path.dirname(os.path.dirname(event.src_path))
            if self._is_study_directory(study_dir):
                logger.debug(f"File modified in study {study_dir}: {event.src_path}")
                self._start_debounce_timer(study_dir)
        
    def on_closed(self, event):
        super().on_closed(event)
        if not event.is_directory:
            # Ignore files in processing output directories
            if self._is_processing_output_dir(event.src_path):
                logger.debug(f"Ignoring file closed event in processing directory: {event.src_path}")
                return
                
            study_dir = os.path.dirname(os.path.dirname(event.src_path))
            if self._is_study_directory(study_dir):
                logger.info(f"File closed in study {study_dir}: {event.src_path}. Debouncing.")
                self._start_debounce_timer(study_dir)

import threading # Required for Timer in NewStudyEventHandler

class FileSystemManager:
    def __init__(self, config, study_processor_callback=None):
        """Initialize the FileSystemManager.

        Args:
            config (dict): Application configuration containing directory paths.
            study_processor_callback (callable): Callback for when a new study is ready.
        """
        self.config = config
        self.working_dir = os.path.expanduser(config.get("directories", {}).get("working", "~/CNCT_working"))
        self.quarantine_subdir = config.get("directories", {}).get("quarantine_subdir", "quarantine")
        self.quarantine_dir = os.path.join(self.working_dir, self.quarantine_subdir)
        self.logs_dir = os.path.expanduser(config.get("directories", {}).get("logs", "~/CNCT_logs"))

        # Add a lock dictionary to track processing studies
        self.processing_locks = {}

        os.makedirs(self.working_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        logger.info(f"FileSystemManager initialized. Working: {self.working_dir}, Quarantine: {self.quarantine_dir}, Logs: {self.logs_dir}")
        
        self.study_processor_callback = study_processor_callback
        self.observer = None
        if self.study_processor_callback:
            self.event_handler = NewStudyEventHandler(self, self.study_processor_callback)
            self.observer = Observer()
        else:
            logger.warning("No study_processor_callback provided to FileSystemManager. Watchdog observer not started.")

    def is_study_being_processed(self, study_uid):
        """Check if a study is currently being processed."""
        return study_uid in self.processing_locks and self.processing_locks[study_uid].locked()

    def acquire_study_lock(self, study_uid):
        """Try to acquire a lock for study processing. Returns True if successful, False if already locked."""
        if study_uid not in self.processing_locks:
            self.processing_locks[study_uid] = threading.Lock()
        
        # Try to acquire the lock without blocking
        return self.processing_locks[study_uid].acquire(blocking=False)

    def release_study_lock(self, study_uid):
        """Release the processing lock for a study."""
        if study_uid in self.processing_locks and self.processing_locks[study_uid].locked():
            self.processing_locks[study_uid].release()
            logger.debug(f"Released processing lock for study {study_uid}")

    def start_watching(self):
        if self.observer and self.study_processor_callback:
            self.observer.schedule(self.event_handler, self.working_dir, recursive=True)
            try:
                self.observer.start()
                logger.info(f"Started watching working directory for new studies: {self.working_dir}")
            except Exception as e:
                logger.error(f"Failed to start watchdog observer: {e}", exc_info=True)
        elif not self.study_processor_callback:
             logger.error("Cannot start watching: study_processor_callback was not provided during FSM initialization.")
        else:
            logger.info("Watchdog observer not configured, not starting.")

    def stop_watching(self):
        if self.observer and self.observer.is_alive():
            # Stop all timers in the event handler before stopping the observer
            if hasattr(self.event_handler, "study_activity_timers"):
                for study_uid, timer in list(self.event_handler.study_activity_timers.items()):
                    timer.cancel()
                    logger.debug(f"Cancelled active debounce timer for study {study_uid} during shutdown.")
                self.event_handler.study_activity_timers.clear()
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped watching working directory.")

    def get_study_path(self, study_instance_uid):
        return os.path.join(self.working_dir, f"UID_{study_instance_uid}")

    def save_incoming_dicom(self, dataset, file_meta, negotiated_transfer_syntax=None):
        try:
            study_uid = dataset.StudyInstanceUID
            sop_instance_uid = dataset.SOPInstanceUID
            study_path = self.get_study_path(study_uid)

            sop_class_uid = dataset.SOPClassUID
            modality = getattr(dataset, "Modality", "").upper()
            is_rtstruct = "1.2.840.10008.5.1.4.1.1.481.3" in str(sop_class_uid) or modality == "RTSTRUCT"

            series_dir_name = "Structure" if is_rtstruct else "DCM"
            series_path = os.path.join(study_path, series_dir_name)
            os.makedirs(series_path, exist_ok=True)
            
            filename = f"{sop_instance_uid}.dcm"
            filepath = os.path.join(series_path, filename)
            
            # Ensure file_meta is appropriate for writing
            ds_file_meta = pydicom.Dataset(file_meta)  # Make a copy to modify
            ds_file_meta.MediaStorageSOPClassUID = sop_class_uid
            ds_file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
            
            if negotiated_transfer_syntax:
                ds_file_meta.TransferSyntaxUID = negotiated_transfer_syntax
            elif not hasattr(ds_file_meta, "TransferSyntaxUID") or not ds_file_meta.TransferSyntaxUID:
                logger.warning(f"No negotiated transfer syntax provided for {sop_instance_uid}. Defaulting to ImplicitVRLittleEndian.")
                ds_file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

            # Set required DICOM meta information
            ds_file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
            ds_file_meta.ImplementationVersionName = "NETRT_CORE_WD_0.1"

            # Set the dataset file meta information
            dataset.file_meta = ds_file_meta
            
            # Ensure the DICM prefix is initiated
            if not hasattr(dataset, 'is_implicit_VR') or not hasattr(dataset, 'is_little_endian'):
                if ds_file_meta.TransferSyntaxUID.is_implicit_VR:
                    dataset.is_implicit_VR = True
                    dataset.is_little_endian = True  # Implicit VR is always Little Endian
                else:  # Explicit VR
                    dataset.is_implicit_VR = False
                    dataset.is_little_endian = ds_file_meta.TransferSyntaxUID.is_little_endian

            # Save the dataset ensuring DICM header is included
            dataset.save_as(filepath, enforce_file_format=True)
            logger.info(f"Saved DICOM file: {filepath} with TS: {ds_file_meta.TransferSyntaxUID}")
            return filepath
        except Exception as e:
            logger.error(f"Error saving DICOM file {getattr(dataset, 'SOPInstanceUID', 'UNKNOWN_SOPUID')}: {e}", exc_info=True)
            return None

    def quarantine_study(self, study_instance_uid, reason="Unknown error"):
        study_path = self.get_study_path(study_instance_uid)
        if os.path.exists(study_path):
            quarantine_study_path = os.path.join(self.quarantine_dir, f"UID_{study_instance_uid}")
            # Ensure the target quarantine path doesn't already exist to avoid shutil.move error
            if os.path.exists(quarantine_study_path):
                logger.warning(f"Quarantine path {quarantine_study_path} already exists. Appending timestamp.")
                quarantine_study_path = f"{quarantine_study_path}_{int(time.time())}"
            try:
                shutil.move(study_path, quarantine_study_path)
                logger.warning(f"Moved study {study_instance_uid} to quarantine: {quarantine_study_path}. Reason: {reason}")
            except Exception as e:
                logger.error(f"Failed to move study {study_instance_uid} to quarantine: {e}", exc_info=True)
        else:
            logger.warning(f"Attempted to quarantine non-existent study path: {study_path}")

    def cleanup_study_directory(self, study_instance_uid):
        study_path = self.get_study_path(study_instance_uid)
        if os.path.exists(study_path):
            try:
                shutil.rmtree(study_path)
                logger.info(f"Successfully cleaned up study directory: {study_path}")
            except Exception as e:
                logger.error(f"Error cleaning up study directory {study_path}: {e}", exc_info=True)
        else:
            logger.info(f"Attempted to clean up non-existent study directory: {study_path}")

# Example usage (for testing - will be integrated into the main application)
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    
    def dummy_study_processor(study_uid):
        logger.info(f"MAIN_TEST: Dummy study processor called for study UID: {study_uid}")
        # In a real app, this would queue the study_uid for processing by StudyProcessor instance

    test_config = {
        "directories": {
            "working": "/home/ubuntu/CNCT_working_fsm_watchdog_test",
            "logs": "/home/ubuntu/CNCT_logs_fsm_watchdog_test",
            "quarantine_subdir": "failed_studies"
        },
        "watcher": {
            "debounce_interval_seconds": 3,
            "min_file_count_for_processing": 1 # For simple test
        }
    }
    fsm = FileSystemManager(test_config, dummy_study_processor)
    fsm.start_watching()
    logger.info(f"FSM watching dir: {fsm.working_dir}. Create subdirectories like UID_teststudy/DCM/file.dcm to test.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping watcher.")
    finally:
        fsm.stop_watching()
        logger.info("FSM watcher stopped.")

