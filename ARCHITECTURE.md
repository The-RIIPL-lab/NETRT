# NETRT Application Architecture

## Overview

NETRT is a DICOM processing service that receives DICOM studies over the network, extracts contour data from RT Structure Sets, creates overlay series with merged contour masks, and forwards the processed results to a specified destination.

## Core Components

The application is built around the `netrt_core` package with the following modules:

### Configuration and Logging
- **`config_loader.py`**: Loads settings from YAML configuration file with defaults
- **`logging_setup.py`**: Configures application and transaction logging

### File System Management
- **`file_system_manager.py`**: Manages study directories, file operations, and filesystem monitoring
  - Creates `UID_<StudyInstanceUID>` directory structure
  - Implements watchdog-based file monitoring with debounce timers
  - Provides thread-safe processing locks
  - Handles quarantine and cleanup operations

### DICOM Operations
- **`dicom_listener.py`**: DICOM C-STORE SCP server using pynetdicom
  - Receives incoming DICOM files
  - Handles C-ECHO requests
  - Integrates with FileSystemManager for file storage

- **`dicom_sender.py`**: DICOM C-STORE SCU client
  - Sends processed files to destination PACS
  - Configurable presentation contexts

### Processing Pipeline
- **`study_processor.py`**: Orchestrates the complete processing workflow
- **`contour_processor.py`**: Handles RT Structure Set processing
  - Extracts ROI data using rt-utils
  - Merges contours into binary masks
  - Creates new DICOM series with overlay planes
  - Optional debug visualization (JPG and DICOM formats)

- **`burn_in_processor.py`**: Adds text disclaimers to processed images
- **`DicomAnonymizer.py`**: Handles DICOM anonymization with configurable rules

## Data Flow

### 1. Reception
DICOM files are received via C-STORE and saved to structured directories:
```
UID_<StudyInstanceUID>/
├── DCM/           # CT/MR images
└── Structure/     # RTSTRUCT files
```

### 2. Detection
Filesystem watcher monitors for file activity. After a configurable debounce period (default 5 seconds) with no new files, processing is triggered.

### 3. Processing Pipeline
1. **Validation**: Verify required directories and files exist
2. **Anonymization**: Remove or modify specified DICOM tags (optional)
3. **Contour Processing**: Extract and merge ROI contours, create overlay series
4. **Burn-in**: Add text disclaimers to pixel data (optional)
5. **Debug Output**: Generate visualization images and debug DICOM series (optional)

### 4. Output Structure
Processed files are organized in additional subdirectories:
```
UID_<StudyInstanceUID>/
├── DCM/
├── Structure/
├── Addition/       # Processed series with overlays
└── DebugDicom/     # Debug visualization series (if enabled)
```

### 5. Transmission and Cleanup
Processed series are sent to the configured destination via C-STORE. On success, the entire study directory is removed. On failure, the study is moved to quarantine.

## Configuration

All settings are managed through a single `config.yaml` file covering:
- DICOM listener and destination parameters
- Directory paths
- Processing options (contour filtering, series descriptions, etc.)
- Anonymization rules
- Feature flags

## Concurrency and Safety

- Thread-safe processing locks prevent duplicate processing of the same study
- Debounce mechanism ensures studies are only processed after file transfer completion
- Quarantine system preserves problematic studies for analysis
- Comprehensive logging tracks all operations for auditing

## Directory Structure

```
~/CNCT_working/                    # Working directory
├── UID_<StudyUID>/                # Individual study processing
│   ├── DCM/                       # Original images
│   ├── Structure/                 # RTSTRUCT files
│   ├── Addition/                  # Processed overlay series
│   └── DebugDicom/               # Debug visualization (optional)
└── quarantine/                    # Failed studies

~/CNCT_logs/                       # Log files
├── application.log                # General application events
└── transaction.log               # Study processing transactions
```