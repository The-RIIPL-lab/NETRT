# NETRT Configuration Guide

This document provides a comprehensive guide to configuring the NETRT application. Configuration is primarily managed through a YAML file (default: `config.yaml`) and can be supplemented by command-line arguments.

## Configuration File (`config.yaml`)

The application loads its configuration from a YAML file. If the specified file is not found or is invalid, a default configuration will be used, and a new `config.yaml` with default values will be created.

### Top-Level Structure

The `config.yaml` file is organized into several main sections:

```yaml
dicom_listener: { ... }
dicom_destination: { ... }
directories: { ... }
logging: { ... }
anonymization: { ... }
processing: { ... }
watcher: { ... }
feature_flags: { ... }
```

### 1. `dicom_listener`

Configures the DICOM C-STORE SCP (Service Class Provider) that listens for incoming DICOM studies.

-   `host`: (String) The IP address the DICOM listener should bind to. Default: `"0.0.0.0"` (listens on all available network interfaces).
-   `port`: (Integer) The port number for the DICOM listener. Default: `11112`.
-   `ae_title`: (String) The Application Entity Title of the NETRT DICOM listener. Default: `"NETRTCORE"`.
-   `config_negotiated_transfer_syntax`: (Boolean) If `true`, when saving incoming DICOM files, the listener will attempt to use the negotiated transfer syntax from the DICOM association. If `false` or if a negotiated syntax is not available/applicable, it defaults to a standard explicit VR little endian syntax. Default: `true`.

### 2. `dicom_destination`

Configures the destination DICOM C-STORE SCU (Service Class User) to which processed studies will be sent.

-   `ip`: (String) The IP address of the destination DICOM server/PACS. Default: `"127.0.0.1"`.
-   `port`: (Integer) The port number of the destination DICOM server/PACS. Default: `104`.
-   `ae_title`: (String) The Application Entity Title of the destination DICOM server/PACS. Default: `"DEST_AET"`.

### 3. `directories`

Defines paths for various operational directories. Paths starting with `~/` will be expanded to the user's home directory.

-   `working`: (String) The root directory where incoming studies are temporarily stored and processed. Default: `"~/CNCT_working"`.
-   `logs`: (String) The directory where log files (application and transaction logs) will be stored. Default: `"~/CNCT_logs"`.
-   `quarantine_subdir`: (String) The name of the subdirectory within the `working` directory where studies that fail processing are moved. Default: `"quarantine"`.
-   `ip_validation_file`: (String) Path to the JSON file containing rules for IP address validation (if used by `ip_validation.py`). Default: `"./valid_networks.json"`.

### 4. `logging`

Configures application-wide logging and specific transaction logging.

-   `level`: (String) The minimum logging level for the application. Standard Python logging levels (e.g., `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`). Default: `"INFO"`.
-   `format`: (String) The format string for general application log messages. Uses Python logging format codes. Default: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`.
-   `application_log_file`: (String) The name of the main application log file, stored in the `logs` directory. Default: `"application.log"`.
-   `transaction_log_file`: (String) The name of the transaction log file, stored in the `logs` directory. This log captures key events for each study processed. Default: `"transaction.log"`.
-   `transaction_log_format`: (String) The format string for transaction log messages. Default: `"%(asctime)s TXN [%(levelname)s]: %(message)s"`.

### 5. `anonymization`

Controls the DICOM anonymization process.

-   `enabled`: (Boolean) Global switch to enable or disable all anonymization. If `false`, no anonymization is performed. Default: `true`.
-   `full_anonymization_enabled`: (Boolean) If `true` and `enabled` is also `true`, extensive anonymization rules defined in `full_anonymization_rules` are applied. If `false` but `enabled` is `true`, a partial/default anonymization is performed based on `default_tags_to_remove` and `default_tags_to_blank`. Default: `false`.
-   `default_tags_to_remove`: (List of Strings) A list of DICOM tag keywords to be completely removed from datasets when `full_anonymization_enabled` is `false`. Default: `["AccessionNumber", "PatientID"]`.
-   `default_tags_to_blank`: (List of Strings) A list of DICOM tag keywords whose values will be set to empty strings when `full_anonymization_enabled` is `false`. Default: `[]`.
-   `full_anonymization_rules`: (Dictionary) Contains detailed rules applied when `full_anonymization_enabled` is `true`.
    -   `tags_to_remove`: (List of Strings) Tags to remove.
    -   `tags_to_empty`: (List of Strings) Tags to set to zero-length.
    -   `tags_to_modify_date`: (List of Strings) Date tags (YYYYMMDD) whose day part will be set to `01`.
    -   `tags_to_modify_time`: (List of Strings) Time tags (HHMMSS.FFFFFF) whose minute, second, and fractional second parts will be set to `00`.
    -   `tags_to_regenerate_uid`: (List of Strings) DICOM UIDs that will be replaced with newly generated UIDs.
    -   `patient_id_override`: (String or `null`) If specified, the PatientID tag will be set to this value. If `null` or not present, PatientID might be removed or handled by other rules.
    -   `patient_name_override`: (String or `null`) If specified, the PatientName tag will be set to this value. If `null` or not present, PatientName might be removed or handled by other rules.
    *(See `DEFAULT_CONFIG` in `netrt_core/config_loader.py` for the default set of full anonymization rules)*

### 6. `processing`

Configures parameters related to the study processing pipeline, especially contour and segmentation handling.

-   `ignore_contour_names_containing`: (List of Strings) A list of case-insensitive substrings. Any RTSTRUCT ROI name containing one of these substrings will be ignored during contour processing (e.g., not merged or used for overlay). Default: `["skull", "patient_outline"]`.
-   `default_series_description`: (String) The default Series Description to be used for the new DICOM series created with contour overlays. Default: `"Processed DicomRT with Overlay"`.
-   `default_series_number_overlay`: (Integer) The default Series Number for the new DICOM series with contour overlays. Default: `9901`.
-   `default_series_number_seg`: (Integer) The default Series Number for new DICOM SEG objects, if created. Default: `9902`.
-   `add_burn_in_disclaimer`: (Boolean) If `true`, a text disclaimer will be burned into the pixel data of the generated overlay series. Default: `true`.
-   `burn_in_text`: (String) The text to be used for the burn-in disclaimer if `add_burn_in_disclaimer` is `true`. Default: `"FOR RESEARCH USE ONLY - NOT FOR CLINICAL USE"`.

### 7. `watcher`

Configures the file system watcher that monitors the incoming directory for new studies.

-   `debounce_interval_seconds`: (Integer) The time in seconds the watcher will wait after the last file event in a study directory before considering the study reception complete and triggering processing. This helps ensure all files of a study have arrived. Default: `5`.
-   `min_file_count_for_processing`: (Integer) The minimum number of files that must be present in a study's subdirectory (e.g., `DCM` or `Structure`) before the watcher considers it for the debounce timer. This can help prevent processing prematurely if only a few initial files have arrived. Default: `2`.

### 8. `feature_flags`

Allows enabling or disabling certain application features.

-   `enable_segmentation_export`: (Boolean) If `true`, the application will attempt to generate and export DICOM SEG objects from RTSTRUCT contours. Default: `false`.

## Command-Line Arguments

The application supports the following command-line arguments:

-   `--config <path_to_config.yaml>`: Specifies the path to the configuration file. If not provided, the application will look for `config.yaml` in the current working directory (or the directory where `main.py` is located, depending on execution context).
    Example: `python main.py --config /etc/netrt/production_config.yaml`

## Default Configuration

If `config.yaml` is not found or is invalid, the application will use internal default values and attempt to write these defaults to a new `config.yaml` file. The default values are defined in `netrt_core/config_loader.py` and cover all the options described above.

It is recommended to copy the default `config.yaml` and customize it for your environment rather than relying on automatic creation, especially for production deployments.

