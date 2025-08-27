# NETRT Technical Details

## Processing Workflow

### Study Reception and Detection

**File Organization**: Incoming DICOM files are automatically sorted into structured directories:
```
UID_<StudyInstanceUID>/
├── DCM/          # CT/MR image series
└── Structure/    # RTSTRUCT files
```

**Completion Detection**: A watchdog-based file monitor implements a debounce mechanism:
- Monitors file system events in the working directory
- Starts a countdown timer after each file activity
- Default debounce interval: 5 seconds
- Minimum file count required: 2 files
- Processing triggers only after debounce period completes with no new activity

**Concurrent Processing Protection**: Thread-safe locks prevent multiple processing attempts on the same study simultaneously.

### Core Processing Pipeline

**1. Input Validation**
- Verifies DCM directory exists and contains files
- Locates RTSTRUCT file in Structure directory
- Quarantines studies missing required components

**2. Anonymization** (Optional)
- Configurable tag removal or modification
- Two modes: standard (specific tags) or comprehensive (extensive anonymization)
- Operates on both image series and RTSTRUCT files

**3. Contour Processing**
- Loads RTSTRUCT using rt-utils library
- Filters ROIs based on configurable name patterns
- Merges remaining contours into unified 3D binary mask
- Creates new DICOM series with overlay planes (group 0x6000)

**4. Series Generation**
- New SeriesInstanceUID and SOPInstanceUIDs generated
- Configurable series descriptions and numbers
- Maintains original study context (StudyInstanceUID, FrameOfReferenceUID)
- Updates timestamps to processing time

**5. Burn-in Processing** (Optional)
- Overlays text disclaimer directly into pixel data
- Configurable text content and positioning
- Uses OpenCV for text rendering

**6. Debug Visualization** (Optional)
- Generates JPG images showing contour overlays
- Creates Secondary Capture DICOM series for PACS viewing
- High-quality matplotlib-based rendering
- Useful for quality assurance and verification

### Network Operations

**DICOM Listener (C-STORE SCP)**
- Multi-threaded pynetdicom server
- Supports comprehensive storage SOP classes
- Handles multiple transfer syntaxes
- Integrates with file system manager for automatic processing

**DICOM Sender (C-STORE SCU)**
- Configurable presentation contexts
- Batch directory transmission
- Error handling and retry logic
- Transaction logging for audit trails

## File System Management

### Directory Structure
```
Working Directory/
├── UID_<StudyUID_1>/
│   ├── DCM/                    # Original images
│   ├── Structure/              # RTSTRUCT files
│   ├── Addition/               # Processed overlay series
│   └── DebugDicom/            # Debug visualization (optional)
├── UID_<StudyUID_2>/
└── quarantine/                 # Failed studies
    └── UID_<StudyUID_3>_<timestamp>/
```

### File Monitoring Implementation
- Uses Python watchdog library for efficient file system monitoring
- Handles file creation, modification, and close events
- Implements recursive directory monitoring
- Ignores processing output directories to prevent loops

### Error Handling and Recovery
- Failed studies automatically moved to quarantine
- Detailed error logging with stack traces
- Preserves original data for manual analysis
- Configurable retry mechanisms

## Configuration Architecture

### Hierarchical Configuration Loading
1. Default values defined in code
2. User configuration file (YAML) merged with defaults
3. Command-line arguments override file settings
4. Environment-specific path expansion

### Dynamic Settings
- Home directory path expansion (`~/` prefix)
- Runtime debugging mode activation
- Feature flag controls for optional components

## Logging and Monitoring

### Dual Logging System
- **Application Log**: General system events, errors, debugging
- **Transaction Log**: Structured audit trail for processing events

### Transaction Event Types
```
PROCESSING_START   - Study processing initiated
PROCESSING_SUCCESS - Study completed successfully  
PROCESSING_FAILED  - Study processing failed
SENDING_START      - DICOM transmission started
SENDING_SUCCESS    - DICOM transmission completed
```

### Log Rotation and Management
- Configurable log levels and formats
- File and console output handlers
- Structured logging for automated parsing

## Performance and Scalability

### Memory Management
- Streaming DICOM file processing
- Efficient numpy array operations for mask generation
- Automatic cleanup of temporary data structures

### Processing Optimization
- Concurrent study processing (with locks for safety)
- Efficient contour merge algorithms
- Minimal disk I/O through direct memory operations

### Resource Monitoring
- Working directory cleanup after successful processing
- Quarantine system prevents disk space exhaustion
- Configurable processing parameters for resource control

## Security Considerations

### Data Protection
- Configurable anonymization removes PHI
- Temporary file secure handling
- No persistent storage of sensitive data

### Network Security
- DICOM AE Title validation
- Configurable network binding interfaces
- Audit logging for all network operations

### Error Information Disclosure
- Sanitized error messages in logs
- StudyInstanceUID tracking without patient information
- Secure quarantine of problematic data

## Integration Patterns

### PACS Integration
- Standard DICOM C-STORE operations
- Compatible with major PACS vendors
- Configurable presentation contexts for interoperability

### Workflow Integration
- Event-driven processing model
- RESTful monitoring endpoints (future enhancement)
- Standard exit codes for process management

### Quality Assurance
- Debug visualization for processing verification
- Comprehensive audit trails
- Quarantine system for manual review of failures