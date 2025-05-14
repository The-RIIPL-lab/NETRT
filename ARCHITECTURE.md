# NETRT Application Architecture

This document provides an overview of the refactored NETRT application architecture after Round 1 changes.

## 1. Overview

The NETRT application is designed to receive DICOM studies (images and RTSTRUCT files), process them to add contour overlays, perform anonymization as configured, and forward the results to a specified DICOM destination. The refactored architecture emphasizes modularity, configurability, and maintainability.

## 2. Core Components (`netrt_core` package)

The application is structured around a `netrt_core` package containing the following key modules:

*   **`config_loader.py`**: 
    *   Responsible for loading application settings from a YAML configuration file (e.g., `config.yaml`).
    *   Provides default settings if the configuration file is missing or incomplete.
    *   Handles path expansion for directory configurations.
*   **`logging_setup.py`**:
    *   Configures application-wide logging based on settings from the configuration file.
    *   Sets up separate log files for general application logs and transaction logs (e.g., DICOM receipt/send events) in a configurable logs directory.
*   **`file_system_manager.py`**:
    *   Manages all file system operations related to study processing.
    *   Creates and manages a configurable `working_directory` for temporary storage of incoming and processed studies.
    *   Handles the creation of study-specific subdirectories (e.g., `UID_<StudyInstanceUID>/DCM`, `UID_<StudyInstanceUID>/Structure`).
    *   Saves incoming DICOM files into the appropriate study structure.
    *   Manages a `quarantine_directory` (subdir within `working_directory`) for studies that fail processing.
    *   Cleans up study directories from the `working_directory` after successful processing and sending.
    *   (Future: Will integrate event-based file system watching for new study detection via `watchdog` library).
*   **`dicom_listener.py`**:
    *   Implements the DICOM C-STORE SCP (server) using `pynetdicom`.
    *   Listens for incoming DICOM associations on a configured IP address and port with a specific AE Title.
    *   Handles C-ECHO requests for connectivity testing.
    *   Handles C-STORE requests: receives DICOM datasets and uses the `FileSystemManager` to save them.
    *   Triggers the study processing pipeline (via a callback to `StudyProcessor` or through an event queue managed by `FileSystemManager` once study reception is deemed complete).
*   **`study_processor.py`**:
    *   Orchestrates the entire processing pipeline for a single DICOM study once all its files are received.
    *   Retrieves study data paths from the `FileSystemManager`.
    *   Coordinates various processing steps based on the application configuration:
        *   Anonymization (calling a refactored `DicomAnonymizer` utility).
        *   Contour processing (using `ContourProcessor`).
        *   DICOM SEG object creation (calling a `Segmentations` utility module, if enabled).
        *   Adding "Burn-In" disclaimers (calling an `Add_Burn_In` utility module).
        *   Sending processed files to the destination DICOM node (using a `Send_Files` utility module).
    *   Interacts with `FileSystemManager` to quarantine failed studies or clean up successful ones.
*   **`contour_processor.py`**:
    *   Handles the logic for extracting ROI (Region of Interest) data from RTSTRUCT files and image series using `rt-utils`.
    *   Implements the user-specified contour handling:
        *   Ignores ROIs containing configurable keywords (e.g., "skull").
        *   If multiple non-ignored ROIs are present, logs a warning and merges them into a single binary mask.
    *   Generates new DICOM image instances with the (merged) contour mask added to the overlay plane (e.g., group 0x6000).
    *   Ensures correct DICOM tagging for the new series (new SeriesInstanceUID, SOPInstanceUIDs, SeriesDescription, SeriesNumber, consistent StudyInstanceUID, FrameOfReferenceUID, etc.).

## 3. Utility Modules (Existing, to be refactored/integrated)

These modules from the original codebase are used by `StudyProcessor` and will be progressively refactored or confirmed for compatibility with the new core architecture:

*   **`DicomAnonymizer.py`**: 
    *   (To be refactored) Performs anonymization of DICOM datasets based on rules defined in the configuration file (e.g., removing specific tags like AccessionNumber, PatientID, rather than a fixed full anonymization).
*   **`Segmentations.py`**: 
    *   Handles the creation of DICOM Segmentation Objects (DICOM SEG) if this feature is enabled.
*   **`Add_Burn_In.py`**: 
    *   Adds a "FOR RESEARCH USE ONLY" or similar textual burn-in to the processed images.
*   **`Send_Files.py`**: 
    *   Handles sending DICOM files (C-STORE SCU) to the configured destination DICOM node.
*   **`ip_validation.py`**: 
    *   Validates destination IP addresses against a list of allowed networks/IPs defined in a JSON file (path specified in config).

## 4. Data Flow

1.  **Initialization**:
    *   The main application script loads the configuration using `ConfigLoader`.
    *   Logging is set up by `LoggingSetup`.
    *   `FileSystemManager`, `StudyProcessor`, and `DicomListener` (and other utilities) are instantiated with the loaded configuration.
2.  **DICOM Reception**:
    *   `DicomListener` starts and waits for incoming DICOM associations.
    *   Upon receiving DICOM files (C-STORE), it uses `FileSystemManager` to save them into a structured directory within the `working_directory` (e.g., `~/CNCT_working/UID_<StudyUID>/DCM/` and `~/CNCT_working/UID_<StudyUID>/Structure/`).
3.  **Study Completion & Processing Trigger**:
    *   Once all files for a study are received (detection mechanism to be refined, possibly via `FileSystemManager` and `DicomListener` event `EVT_CONN_CLOSE` or a file watcher), the `StudyProcessor` is invoked with the StudyInstanceUID.
4.  **Study Processing Pipeline (`StudyProcessor`)**:
    *   The `StudyProcessor` retrieves paths to the study's images and structure set.
    *   **Anonymization (Optional)**: If enabled in config, relevant DICOM tags are modified/removed.
    *   **Contour Processing (`ContourProcessor`)**: RTSTRUCT is parsed, specified ROIs are filtered/merged, and a new DICOM series with overlays is generated in an `Addition` subdirectory within the study's working folder.
    *   **Burn-In**: Textual disclaimers are added to the images in the `Addition` folder.
    *   **Segmentation (Optional)**: If enabled, DICOM SEG objects are created in a `Segmentations` subdirectory.
5.  **DICOM Sending**:
    *   The `StudyProcessor` uses the `Send_Files` utility to transmit the processed DICOM series (from `Addition` and optionally `Segmentations` subdirectories) to the destination DICOM node defined in the configuration.
6.  **Logging & Auditing**:
    *   Throughout the process, general application events and errors are logged to `application.log`.
    *   Key transaction events (e.g., study received from IP, study sent to IP, StudyInstanceUID) are logged to `transaction.log`.
7.  **Cleanup/Quarantine**:
    *   If processing and sending are successful, `FileSystemManager` cleans up the study's directory from the `working_directory`.
    *   If any critical error occurs, `FileSystemManager` moves the study's directory to the `quarantine_directory` for manual inspection.

## 5. Configuration

*   All primary configurations are managed via a central `config.yaml` file.
*   This includes DICOM listener/destination details, directory paths, logging preferences, anonymization rules, contour processing parameters, and feature flags.

## 6. Directory Structure (Example)

```
~/
|-- CNCT_working/                  (Configurable: directories.working)
|   |-- UID_1.2.3.456.789/          (Processing directory for a study)
|   |   |-- DCM/                    (Original DICOM images)
|   |   |   |-- image1.dcm
|   |   |   `-- ...
|   |   |-- Structure/              (Original RTSTRUCT files)
|   |   |   `-- rtstruct.dcm
|   |   |-- Addition/               (Processed images with overlays)
|   |   |   |-- overlay_image1.dcm
|   |   |   `-- ...
|   |   |-- Segmentations/          (Generated DICOM SEG objects, if enabled)
|   |   |   `-- seg.dcm
|   |   `-- (other temp files)
|   `-- quarantine/                 (Configurable: directories.quarantine_subdir)
|       `-- UID_9.8.7.654.321/      (Failed study moved here)
|-- CNCT_logs/                     (Configurable: directories.logs)
|   |-- application.log
|   `-- transaction.log
|-- NETRT/                         (Application source code)
|   |-- netrt_core/
|   |   |-- __init__.py
|   |   |-- config_loader.py
|   |   |-- logging_setup.py
|   |   |-- file_system_manager.py
|   |   |-- dicom_listener.py
|   |   |-- study_processor.py
|   |   `-- contour_processor.py
|   |-- tests/
|   |-- (old modules like DicomAnonymizer.py, Send_Files.py etc.)
|   |-- main.py                     (New main application entry point)
|   `-- config.yaml                 (Default or user-provided configuration)
```

This modular architecture aims to make NETRT more robust, easier to understand, maintain, and extend in future development rounds.

