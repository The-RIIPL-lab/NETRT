import pydicom
from datetime import datetime
import hashlib
import re
import logging

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
                    "remove_tags": ["AccessionNumber"],
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
            # Minimal anonymization - only remove specific tags
            # Get custom tags to remove from config if available, otherwise use defaults
            self.tags_to_remove = self.config.get("rules", {}).get("remove_tags", ["AccessionNumber", "PatientID"])
            self.tags_to_empty = self.config.get("rules", {}).get("blank_tags", [])
        
        # Ensure AccessionNumber and PatientID are always in one of the lists
        if "AccessionNumber" not in self.tags_to_remove and "AccessionNumber" not in self.tags_to_empty:
            self.tags_to_remove.append("AccessionNumber")
        
        if "PatientID" not in self.tags_to_remove and "PatientID" not in self.tags_to_empty:
            self.tags_to_remove.append("PatientID")
        
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
        # Create a copy to avoid modifying the original
        anon_obj = dicom_obj.copy()
        
        # Remove identifiable tags
        for tag in self.tags_to_remove:
            if hasattr(anon_obj, tag):
                delattr(anon_obj, tag)
        
        # Empty specified tags
        for tag in self.tags_to_empty:
            if hasattr(anon_obj, tag):
                setattr(anon_obj, tag, '')
        
        # Handle special tags if doing full anonymization
        if self.full_anonymization:
            for tag, handler in self.special_tags.items():
                if hasattr(anon_obj, tag):
                    setattr(anon_obj, tag, handler(getattr(anon_obj, tag)))
            
            # Generate a new StudyInstanceUID
            if hasattr(anon_obj, 'StudyInstanceUID'):
                anon_obj.StudyInstanceUID = self._generate_uid(anon_obj.StudyInstanceUID)
            
            # Generate a new SeriesInstanceUID
            if hasattr(anon_obj, 'SeriesInstanceUID'):
                anon_obj.SeriesInstanceUID = self._generate_uid(anon_obj.SeriesInstanceUID)
            
            # Keep SOPInstanceUID but hash it
            if hasattr(anon_obj, 'SOPInstanceUID'):
                anon_obj.SOPInstanceUID = self._generate_uid(anon_obj.SOPInstanceUID)
        
        # Set PatientName and PatientID with optional prefix if they were removed
        if "PatientID" in self.tags_to_remove:
            anon_obj.PatientID = f"{self.id_prefix}ANONYMOUS"
        
        if "PatientName" in self.tags_to_remove:
            anon_obj.PatientName = f"{self.id_prefix}ANONYMOUS"
        
        return anon_obj

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