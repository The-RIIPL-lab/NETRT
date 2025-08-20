# NETRT TODO List

This document outlines potential improvements, bugs, and security considerations identified during a code review. The highest priority items from the previous version have been addressed.

## 1. High Priority - Next Steps

-   **[HIGH] Implement Automated Testing**: The single most valuable improvement from this point would be to add a testing framework (like `pytest`) and create a suite of unit and integration tests. This would ensure that future changes don't break existing functionality and would allow for more confident development.
    -   **Unit Tests**: Create tests for individual components like `ContourProcessor`, `BurnInProcessor`, and `DicomAnonymizer` to verify their logic with sample inputs.
    -   **Integration Tests**: Create tests for the full `StudyProcessor` pipeline to ensure all the components work together correctly.

## 2. Refactoring & Code Quality (Future Improvements)

-   **[LOW] Simplify Anonymization Configuration**: The `DicomAnonymizer` class and its corresponding section in `config.yaml` are quite complex. A future effort could simplify these rules to make them easier to understand and manage.

-   **[LOW] Improve `sys.path` Manipulation**: `main.py` uses `sys.path.insert(0, ...)` to make the `netrt_core` package importable. A more standard approach would be to structure the project to be installable (e.g., with a `pyproject.toml`) or to use a shell script wrapper that sets the `PYTHONPATH`.

## 3. Security Considerations

*These items are generally well-mitigated by the current design but are worth keeping in mind for any future modifications.*

-   **[MEDIUM] DICOM File Parsing Vulnerabilities**: The application relies on `pydicom` to parse incoming DICOM files. A maliciously crafted file could potentially cause a denial-of-service. 
    *   **Mitigation**: The current approach of catching exceptions and quarantining the study is a good defense. Ensure that all file parsing remains wrapped in `try...except` blocks and keep dependencies up-to-date.

-   **[LOW] Path Traversal Risk**: The application constructs file paths from a `StudyInstanceUID`. 
    *   **Mitigation**: The current use of `os.path.join` on a trusted base directory provides good protection. As a best practice, consider sanitizing the UID to ensure it contains no path characters before use.

-   **[LOW] Information Disclosure in Logs**: The logs contain `StudyInstanceUID` and file paths, which could be considered sensitive in some environments. 
    *   **Mitigation**: This is generally acceptable, but the configurable logging level allows for less verbose output in production if needed.