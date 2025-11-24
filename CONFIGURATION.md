# NETRT Configuration Guide

Configuration is managed through a YAML file (default: `config.yaml`). If the file is missing or invalid, default values are used and a new configuration file is created.

## Configuration Structure

### DICOM Listener

```yaml
dicom_listener:
  host: "0.0.0.0"                    # IP address to bind to
  port: 11112                        # TCP port number
  ae_title: "NETRTCORE"              # Application Entity Title
  config_negotiated_transfer_syntax: true  # Use negotiated transfer syntax
```

### DICOM Destination

```yaml
dicom_destination:
  ip: "127.0.0.1"                    # Destination IP address
  port: 104                          # Destination port
  ae_title: "DEST_AET"               # Destination AE Title
```

### Directories

```yaml
directories:
  working: "~/CORRECT_working"          # Study processing directory
  logs: "~/CORRECT_logs"                # Log file directory
  quarantine_subdir: "quarantine"   # Quarantine subdirectory name
```

Paths starting with `~/` are expanded to the user's home directory.

### Processing Options

```yaml
processing:
  # Contour filtering
  ignore_contour_names_containing: ["skull"]
  
  # Overlay series settings
  overlay_series_number: 98
  overlay_series_description: "Processed DicomRT with Overlay"
  overlay_study_id: "RTPlanShare"
  
  # Burn-in disclaimer
  add_burn_in_disclaimer: true
  burn_in_text: "FOR RESEARCH USE ONLY - NOT FOR CLINICAL USE"
  
  # Segmentation series (if enabled)
  segmentation_series_number: 99
  segmentation_series_description_template: "RESEARCH USE ONLY: CONTOUR {}"
  segmentation_algorithm_name: "Radiation Oncologist"
  segmentation_algorithm_version: "v1.0"
  segmentation_tracking_id: "FOR RESEARCH USE ONLY"
  
  # Debug visualization
  debug_series_number: 101
  debug_series_description: "DEBUG: Contour Overlay Visualization"
```

### Anonymization

```yaml
anonymization:
  enabled: true                      # Enable/disable anonymization
  full_anonymization_enabled: false # Use comprehensive anonymization
  
  # Standard anonymization rules
  rules:
    remove_tags:                     # Tags to completely remove
      - "AccessionNumber"
      - "PatientID"
      - "ReferringPhysicianName"
      - "OtherPatientIDs"
      - "PatientBirthDate"
    blank_tags: []                   # Tags to set to empty string
    generate_random_id_prefix: ""    # Prefix for generated IDs
```

When `full_anonymization_enabled` is true, comprehensive anonymization rules are applied including date/time modification and UID regeneration.

### File System Watcher

```yaml
watcher:
  debounce_interval_seconds: 5       # Wait time after last file activity
  min_file_count_for_processing: 2   # Minimum files before processing
```

### Feature Flags

```yaml
feature_flags:
  enable_segmentation_export: false  # Create DICOM SEG objects
```

### Logging

```yaml
logging:
  level: "INFO"                      # Logging level
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  application_log_file: "application.log"
  transaction_log_file: "transaction.log"
  transaction_log_format: "%(asctime)s TXN [%(levelname)s]: %(message)s"
```

## Command Line Arguments

- `--config <path>`: Specify configuration file path (default: config.yaml)
- `--debug`: Enable debug visualization mode

## Default Behavior

If configuration sections are missing, the following defaults apply:

- **DICOM Listener**: Listens on all interfaces (0.0.0.0) port 11112
- **Working Directory**: `~/CORRECT_working`
- **Anonymization**: Enabled, removes AccessionNumber and PatientID
- **Processing**: Ignores contours containing "skull", adds burn-in disclaimer
- **Logging**: INFO level to both console and files

## Example Configuration

```yaml
dicom_listener:
  host: "152.11.105.71"
  port: 11116
  ae_title: "CORRECT_DEV"

dicom_destination:
  ip: "152.11.105.71"
  port: 4242
  ae_title: "RADIORIIPL"

processing:
  ignore_contour_names_containing: ["skull"]
  overlay_series_number: 999
  overlay_series_description: "RESEARCH ONLY: Treatment Plan CT w Mask"
  add_burn_in_disclaimer: true

anonymization:
  enabled: true
  rules:
    remove_tags:
      - "AccessionNumber"
      - "PatientID"
      - "PatientBirthDate"

feature_flags:
  enable_segmentation_export: false
```