import hashlib
import logging
import pydicom
import tempfile
import os
import shutil

logger = logging.getLogger(__name__)

class DicomAnonymizer:
    """
    A class to anonymize DICOM files according to NEMA standards while preserving
    image viewing capabilities. Supports configurable anonymization levels.
    """
    
    def __init__(self, anonymization_config=None):
        """
        Initialize the DicomAnonymizer with the provided configuration.
        
        Args:
            anonymization_config (dict): Configuration for anonymization settings
        """
        self.config = anonymization_config or {}
        
        # Set default config if not provided
        if not self.config:
            self.config = {
                "enabled": True,
                "full_anonymization_enabled": False,
                "rules": {
                    "remove_tags": ["AccessionNumber", "PatientID"],
                    "blank_tags": [],
                    "generate_random_id_prefix": ""
                }
            }
        
        # Get full anonymization flag
        self.full_anonymization = self.config.get("full_anonymization_enabled", False)
        
        # Define tags to remove or blank based on anonymization level
        if self.full_anonymization:
            # Full anonymization - comprehensive list
            self.tags_to_remove = [
                'PatientName',
                'PatientID',
                'PatientBirthDate',
                'PatientSex',
                'PatientAge',
                'PatientWeight',
                'PatientAddress',
                'PatientTelephoneNumbers',
                'PatientMotherBirthName',
                'OtherPatientIDs',
                'OtherPatientNames',
                'PatientBirthName',
                'PatientSize',
                'MilitaryRank',
                'BranchOfService',
                'EthnicGroup',
                'PatientComments',
                'DeviceSerialNumber',
                'PlateID',
                'InstitutionName',
                'InstitutionAddress',
                'ReferringPhysicianName',
                'ReferringPhysicianAddress',
                'ReferringPhysicianTelephoneNumbers',
                'PhysiciansOfRecord',
                'OperatorsName',
                'AdmittingDiagnosesDescription'
            ]
            
            self.tags_to_empty = [
                'AccessionNumber',
                'StudyID',
                'PerformingPhysicianName',
                'RequestingPhysician'
            ]
        else:
            # Partial anonymization - only remove specific tags from config
            self.tags_to_remove = self.config.get("rules", {}).get("remove_tags", ["AccessionNumber", "PatientID"])
            self.tags_to_empty = self.config.get("rules", {}).get("blank_tags", [])
        
        # Ensure AccessionNumber is always removed or emptied regardless of anonymization setting
        if "AccessionNumber" not in self.tags_to_remove and "AccessionNumber" not in self.tags_to_empty:
            self.tags_to_remove.append("AccessionNumber")
        
        # Tags that need special handling if doing full anonymization
        self.special_tags = {}
        if self.full_anonymization:
            self.special_tags = {
                'StudyDate': self._handle_date,
                'SeriesDate': self._handle_date,
                'AcquisitionDate': self._handle_date,
                'ContentDate': self._handle_date,
                'StudyTime': self._handle_time,
                'SeriesTime': self._handle_time,
                'AcquisitionTime': self._handle_time,
                'ContentTime': self._handle_time
            }
        
        # Get the custom ID prefix if specified
        self.id_prefix = self.config.get("rules", {}).get("generate_random_id_prefix", "")
        
        logger.debug(f"DicomAnonymizer initialized with config: {self.config}")
        logger.debug(f"Full anonymization enabled: {self.full_anonymization}")
        logger.debug(f"Tags to remove: {self.tags_to_remove}")
        logger.debug(f"Tags to empty: {self.tags_to_empty}")

    def anonymize(self, dicom_obj):
        """
        Anonymize a DICOM object according to the configured rules.
        
        Args:
            dicom_obj: A pydicom.dataset.FileDataset object
            
        Returns:
            pydicom.dataset.FileDataset: Anonymized DICOM object
        """
        # Ensure we're working with a DICOM object
        if not isinstance(dicom_obj, pydicom.dataset.Dataset):
            logger.error("Object provided for anonymization is not a pydicom Dataset")
            return dicom_obj
        
        # Remove identifiable tags
        for tag in self.tags_to_remove:
            if hasattr(dicom_obj, tag):
                delattr(dicom_obj, tag)
        
        # Empty specified tags
        for tag in self.tags_to_empty:
            if hasattr(dicom_obj, tag):
                setattr(dicom_obj, tag, '')
        
        # Handle special tags if doing full anonymization
        if self.full_anonymization:
            for tag, handler in self.special_tags.items():
                if hasattr(dicom_obj, tag):
                    setattr(dicom_obj, tag, handler(getattr(dicom_obj, tag)))
            
            # Generate a new StudyInstanceUID
            if hasattr(dicom_obj, 'StudyInstanceUID'):
                dicom_obj.StudyInstanceUID = self._generate_uid(dicom_obj.StudyInstanceUID)
            
            # Generate a new SeriesInstanceUID
            if hasattr(dicom_obj, 'SeriesInstanceUID'):
                dicom_obj.SeriesInstanceUID = self._generate_uid(dicom_obj.SeriesInstanceUID)
            
            # Keep SOPInstanceUID but hash it
            if hasattr(dicom_obj, 'SOPInstanceUID'):
                dicom_obj.SOPInstanceUID = self._generate_uid(dicom_obj.SOPInstanceUID)
            
            # Set PatientName to anonymous if it was removed
            # Note: We need to create a new attribute after deleting it
            if "PatientName" in self.tags_to_remove:
                new_patient_id = self._generate_patient_id()
                dicom_obj.PatientName = f"{self.id_prefix}ANONYMOUS_{new_patient_id}"
                
                # Also set a new PatientID that matches the anonymous name
                dicom_obj.PatientID = new_patient_id
        else:
            # Default behavior for partial anonymization
            # Ensure AccessionNumber is always cleared even if not in remove list
            if hasattr(dicom_obj, 'AccessionNumber'):
                dicom_obj.AccessionNumber = ""
            
            # Ensure PatientID is handled according to config
            if "PatientID" in self.tags_to_remove and hasattr(dicom_obj, 'PatientID'):
                dicom_obj.PatientID = ""
        
        return dicom_obj

    def anonymize_file(self, filepath):
        """Anonymize a single DICOM file in place, using a temporary file for safety."""
        try:
            ds = pydicom.dcmread(filepath)
            anonymized_ds = self.anonymize(ds)

            temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), prefix=".tmp-")
            anonymized_ds.save_as(temp_path, enforce_file_format=True)
            os.close(temp_fd)

            shutil.move(temp_path, filepath)
            logger.debug(f"Successfully anonymized and replaced {filepath}")
        except Exception as e:
            logger.error(f"Failed to anonymize file {filepath}: {e}", exc_info=True)
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def _generate_patient_id(self):
        """Generate a random patient ID for full anonymization"""
        import uuid
        # Generate a short unique identifier (8 characters)
        return str(uuid.uuid4()).replace('-', '')[:8]

    def _handle_date(self, date_str):
        """Modify date while preserving year/month"""
        if not date_str:
            return ''
        try:
            # Keep year and month, set day to 01
            return date_str[:6] + '01'
        except:
            return ''

    def _handle_time(self, time_str):
        """Modify time while preserving hour"""
        if not time_str:
            return ''
        try:
            # Keep hour, zero out minutes and seconds
            return time_str[:2] + '0000.000'
        except:
            return ''

    def _generate_uid(self, original_uid):
        """
        Generate a new UID based on the original one to maintain consistency
        while ensuring uniqueness
        """
        # Create a hash of the original UID
        hash_obj = hashlib.sha256(original_uid.encode())
        hashed = hash_obj.hexdigest()
        
        # Ensure the new UID is valid according to DICOM standards
        # Use a prefix that indicates this is an anonymized UID
        prefix = "2.25." # Registered prefix for locally generated UIDs
        
        # Convert hash to a number sequence and truncate to ensure valid length
        numeric_hash = int(hashed[:16], 16)
        
        return f"{prefix}{numeric_hash}"