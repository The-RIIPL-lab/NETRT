# NETRT - Networked DICOM RT-Structure Processing Tool

## Overview

NETRT is a lightweight Python application designed to receive DICOM files (including RT Structure sets) on a network port, process them to extract contour data, and export new DICOM series with contour masks applied to the overlay plane of the structural images. The tool aims to be flexible and easily configurable for use in research and collaborative environments.

This version includes significant refactoring and enhancements from Round 1 and Round 2 development phases, focusing on modularity, configurability, improved logging, and user-requested features.

## Key Features (Post Round 2)

-   **DICOM Listener**: Receives DICOM studies over the network using pynetdicom.
-   **Modular Core**: Refactored codebase into a `netrt_core` package with distinct modules for listening, study processing, file system management, configuration, logging, and contour processing.
-   **Configurable Anonymization**: 
    -   Anonymization can be globally enabled/disabled.
    -   Supports both "full" and "partial" (default) anonymization modes, controlled via `config.yaml`.
    -   Partial mode defaults to removing only `AccessionNumber` and `PatientID`.
    -   Full mode applies extensive rules for tag removal, blanking, date/time modification, and UID regeneration.
    -   No "RT_" prefix is added to patient identifiers by default.
-   **Detailed Transaction Logging**: A separate transaction log (`transaction.log`) captures key events for each study, including source IP, StudyInstanceUID, destination details, and timestamps for reception, processing, and sending events.
-   **External Configuration**: All major operational parameters are managed through an external `config.yaml` file. See [CONFIGURATION.md](CONFIGURATION.md) for details.
-   **Directory Management**: Configurable directories for working files, logs, and quarantined studies.
-   **Event-Based File System Monitoring**: Uses `watchdog` for efficient detection of incoming studies.
-   **Contour Processing**: 
    -   Extracts contour data from DICOM RTSTRUCT files (leveraging `rt-utils`).
    -   Ignores specified contours (e.g., "skull", "patient_outline") based on configuration.
    -   Merges multiple non-ignored contours into a single binary mask.
    -   Exports new DICOM series with the contour mask in the overlay plane.
    -   (Legacy modules `Contour_Addition.py`, `Add_Burn_In.py`, `Segmentations.py` are still part of the processing pipeline but are targeted for future refactoring).
-   **DICOM Sending**: Sends processed DICOM series to a configured destination PACS/server.
-   **Deployment Options**:
    -   **Docker**: Recommended for deployment. A `Dockerfile` is provided for building a containerized application. See [DEPLOYMENT.md](DEPLOYMENT.md).
    -   **Systemd**: An example systemd service unit file (`netrt.service.example`) is provided for running the application as a service on Linux hosts. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Getting Started

1.  **Configuration**: Create or customize your `config.yaml` file. Refer to [CONFIGURATION.md](CONFIGURATION.md).
2.  **Deployment**: Choose your deployment method (Docker or systemd) and follow the instructions in [DEPLOYMENT.md](DEPLOYMENT.md).

## Code Structure

-   `main.py`: Main application entry point.
-   `netrt_core/`: Core application logic modules.
    -   `config_loader.py`: Loads and manages `config.yaml`.
    -   `logging_setup.py`: Configures application and transaction logging.
    -   `dicom_listener.py`: Handles incoming DICOM C-STORE operations.
    -   `file_system_manager.py`: Manages study directories and monitors for new files.
    -   `study_processor.py`: Orchestrates the processing pipeline for each study.
    -   `contour_processor.py`: (Intended for refactored contour logic - current processing still relies heavily on legacy scripts).
-   `DicomAnonymizer.py`: Class for DICOM anonymization based on configuration.
-   `Contour_Addition.py`, `Add_Burn_In.py`, `Segmentations.py`, `Send_Files.py`, `ip_validation.py`: Legacy scripts integrated into the workflow, pending further refactoring.
-   `tests/`: Unit and integration tests.
-   `Dockerfile`: For building the Docker image.
-   `netrt.service.example`: Example systemd unit file.
-   `requirements.txt`: Python dependencies.

## Further Development (Round 3 and Beyond)

-   Refactor legacy processing scripts (`Contour_Addition.py`, etc.) into the `netrt_core` structure.
-   Implement multi-planar contour overlay exports (Axial, Coronal, Sagittal).
-   Advanced performance optimizations and parallel processing if needed.
-   Expand unit and integration test coverage.

## Contributing

Contributions and feedback are welcome. Please refer to the project repository for issue tracking and contribution guidelines.

