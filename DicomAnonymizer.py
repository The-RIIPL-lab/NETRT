import pydicom
from datetime import datetime
import hashlib
import re

class DicomAnonymizer:
    """
    A class to anonymize DICOM files according to NEMA standards while preserving
    image viewing capabilities.
    """
    
    def __init__(self):
        # Tags that should be removed completely
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
        
        # Tags that should be emptied (zero-length)
        self.tags_to_empty = [
            'AccessionNumber',
            'StudyID',
            'PerformingPhysicianName',
            'RequestingPhysician'
        ]
        
        # Tags that need special handling
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

    def anonymize(self, dicom_obj):
        """
        Anonymize a DICOM object while preserving essential imaging information.
        
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
        
        # Handle special tags
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
        
        # Set a generic PatientID and PatientName
        anon_obj.PatientID = "ANONYMOUS"
        anon_obj.PatientName = "ANONYMOUS"
        
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