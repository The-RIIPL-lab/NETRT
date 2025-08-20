# NETRT TODO List

This document outlines potential improvements, bugs, and security considerations identified during a code review. It is intended to guide future development and refactoring efforts.

## 1. Refactoring & Code Quality

-   **[HIGH] Refactor Legacy Scripts into `netrt_core`**: The `study_processor` currently calls several external scripts (`Contour_Addition.py`, `Add_Burn_In.py`, `Segmentations.py`, `Send_Files.py`). This is the most significant technical debt. The logic from these scripts should be encapsulated into classes within the `netrt_core` package to improve modularity, maintainability, and consistency.

-   **[HIGH] Replace `print()` with Logging**: The legacy scripts use `print()` for status updates. This bypasses the application's logging configuration, leading to inconsistent and uncontrolled output. All `print()` statements should be replaced with calls to the appropriate `logging` instance (e.g., `logger.info()`, `logger.warning()`).

-   **[MEDIUM] Centralize Configuration**: The legacy scripts contain numerous hardcoded values (e.g., `SeriesNumber = 98`, `StudyID = "RTPlanShare"`, series descriptions). These should be moved into the `config.yaml` file to make the application more flexible and easier to configure without code changes.

-   **[MEDIUM] Break Down `StudyProcessor.process_study`**: The `process_study` method is very long and handles many different tasks (validation, anonymization, contouring, sending, etc.). It should be broken down into smaller, private methods (e.g., `_validate_study`, `_run_contour_pipeline`, `_send_results`) to improve readability and make it easier to test.

-   **[LOW] Improve `sys.path` Manipulation**: `main.py` uses `sys.path.insert(0, ...)` to make the `netrt_core` package importable. A more standard approach would be to structure the project to be installed as a package (e.g., with a `setup.py` or `pyproject.toml`) or to use a shell script wrapper that sets the `PYTHONPATH`.

## 2. Bugs & Reliability Issues

-   **[HIGH] Fragile File Sorting in `Contour_Addition.py`**: The script sorts DICOM slices using `files.sort(key=lambda x: int(re.findall(r'\d+', x)[-1]))`. This is unreliable as it depends on the slice number being the last integer in the filename. This will fail with many common naming conventions. 
    *   **Fix**: The logic should be changed to read the `InstanceNumber` (0020,0013) or `ImagePositionPatient` (0020,0032) tag from each DICOM file header and sort the files based on that metadata. The `Segmentations.py` script already does this correctly and can be used as a template.

-   **[MEDIUM] In-Place File Modification**: The `Add_Burn_In.py` script and the anonymization loop in `study_processor.py` modify files in-place. If the process is interrupted or fails, the original file may be left in a corrupted state. 
    *   **Fix**: A safer pattern is to write the modified file to a new temporary location and, only upon successful writing, replace the original file with the new one.

-   **[LOW] Broad Exception Handling**: The `main` function in `main.py` has a broad `except Exception as e:` block. While it prevents the application from crashing, it can sometimes hide specific error types that should be handled differently. Consider catching more specific exceptions where possible (e.g., `OSError` for file issues, `pynetdicom.errors` for network issues).

## 3. Security Considerations

-   **[MEDIUM] DICOM File Parsing Vulnerabilities**: The application relies on `pydicom` and other libraries to parse incoming DICOM files. A maliciously crafted DICOM file could potentially cause a denial-of-service by crashing the parser or consuming excessive resources. 
    *   **Mitigation**: The current approach of catching exceptions and quarantining the study is a good defense. Ensure that all file parsing is wrapped in `try...except` blocks. Keep the `pydicom` and `pynetdicom` libraries up-to-date to benefit from security patches.

-   **[LOW] Path Traversal Risk**: The application constructs file paths using `StudyInstanceUID`. While this UID is generally controlled by the sending modality, it is still external input. The current use of `os.path.join` on a trusted base directory (`working_dir`) provides good protection. 
    *   **Recommendation**: As a best practice, consider sanitizing the `StudyInstanceUID` to ensure it doesn't contain any path traversal characters (e.g., `../`, `..\`) before using it to construct a path, even though `os.path.join` mitigates this.

-   **[LOW] Information Disclosure in Logs**: The logs contain `StudyInstanceUID` and file paths. In a sensitive environment, this could be considered information disclosure. 
    *   **Recommendation**: This is generally acceptable for this type of application, but for high-security environments, consider if UIDs should be hashed or truncated in logs. The current logging level is configurable, which allows for less verbose logging in production.

