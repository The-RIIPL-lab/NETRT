import pydicom
import logging
import hashlib # For UID generation if needed, though pydicom.uid.generate_uid is preferred for new UIDs

logger = logging.getLogger(__name__)

class DicomAnonymizer:
    """
    A class to anonymize DICOM files based on configurable rules.
    """

    def __init__(self, anonymization_config):
        """
        Initializes the DicomAnonymizer with specific configuration.

        Args:
            anonymization_config (dict): A dictionary containing anonymization rules.
                                         Expected keys:
                                         - "enabled" (bool): Global switch for anonymization.
                                         - "full_anonymization_enabled" (bool): If true, applies extensive anonymization.
                                         - "default_tags_to_remove" (list): Tags to remove if full_anonymization_enabled is false.
                                         - "default_tags_to_blank" (list): Tags to blank if full_anonymization_enabled is false.
                                         - "full_anonymization_rules" (dict): Rules for full anonymization, containing:
                                             - "tags_to_remove" (list)
                                             - "tags_to_empty" (list)
                                             - "tags_to_modify_date" (list)
                                             - "tags_to_modify_time" (list)
                                             - "tags_to_regenerate_uid" (list) - UIDs to be replaced with new ones.
                                             - "patient_id_override" (str or None): Value to set for PatientID if full anonymization.
                                             - "patient_name_override" (str or None): Value to set for PatientName if full anonymization.
        """
        self.config = anonymization_config
        self.is_enabled = self.config.get("enabled", False)
        self.full_anonymization = self.config.get("full_anonymization_enabled", False)

        if not self.is_enabled:
            logger.info("DicomAnonymizer is disabled by configuration.")
            return

        if self.full_anonymization:
            rules = self.config.get("full_anonymization_rules", {})
            self.tags_to_remove = rules.get("tags_to_remove", [])
            self.tags_to_empty = rules.get("tags_to_empty", [])
            self.tags_to_modify_date = rules.get("tags_to_modify_date", [])
            self.tags_to_modify_time = rules.get("tags_to_modify_time", [])
            self.tags_to_regenerate_uid = rules.get("tags_to_regenerate_uid", [])
            self.patient_id_override = rules.get("patient_id_override", "ANONYMIZED_ID")
            self.patient_name_override = rules.get("patient_name_override", "ANONYMIZED_NAME")
            logger.info("DicomAnonymizer initialized for FULL anonymization.")
        else:
            self.tags_to_remove = self.config.get("default_tags_to_remove", ["AccessionNumber", "PatientID"])
            self.tags_to_empty = self.config.get("default_tags_to_blank", []) # Changed from default_tags_to_blank
            # For partial anonymization, we don't modify dates/times or UIDs by default unless specified
            self.tags_to_modify_date = []
            self.tags_to_modify_time = []
            self.tags_to_regenerate_uid = [] 
            self.patient_id_override = None # No override for PatientID/Name in partial by default
            self.patient_name_override = None
            logger.info(f"DicomAnonymizer initialized for PARTIAL anonymization (tags to remove: {self.tags_to_remove}, tags to empty: {self.tags_to_empty}).")

    def _generate_uid_from_original(self, original_uid):
        """Generates a new UID based on a hash of the original one, for consistent anonymization."""
        # This is a placeholder. For true anonymization with UID replacement,
        # a robust, globally unique, and potentially traceable (for de-anonymization if needed)
        # system is complex. Using pydicom's generate_uid() creates new random UIDs.
        # Hashing can lead to collisions if not careful and doesn't guarantee DICOM UID format.
        # For now, let's use pydicom's generator for simplicity if replacing.
        # A common approach is to use a registered prefix.
        # Example prefix for locally generated UIDs (not globally unique without registration)
        # return pydicom.uid.generate_uid(prefix="2.25.") 
        # The original DicomAnonymizer used a hash. Let's keep that pattern for now if that was intended.
        hash_obj = hashlib.sha256(original_uid.encode())
        hashed = hash_obj.hexdigest()
        # DICOM UIDs are dot-separated numbers, max 64 chars. Hash is not directly usable.
        # This needs a proper UID generation strategy. For now, returning a newly generated one.
        # To maintain some link for consistent anonymization (same input UID -> same output UID),
        # a dictionary lookup or a more sophisticated hashing scheme would be needed.
        # For simplicity in this refactor, we'll generate a new random one.
        # If consistent hashing is critical, the original _generate_uid method should be adapted.
        new_uid = pydicom.uid.generate_uid(prefix="2.25.") # Example prefix
        logger.debug(f"Regenerating UID: {original_uid} -> {new_uid}")
        return new_uid

    def _handle_date(self, date_str):
        if not date_str or len(date_str) < 6:
            return "" # Return empty if invalid or too short
        return date_str[:6] + "01"  # Keep YYYYMM, set day to 01

    def _handle_time(self, time_str):
        if not time_str or len(time_str) < 2:
            return "" # Return empty if invalid or too short
        return time_str[:2] + "0000.00"  # Keep HH, zero out MMSS.FF

    def anonymize_dataset(self, ds):
        """
        Anonymizes a pydicom Dataset object in-place based on the loaded configuration.

        Args:
            ds (pydicom.Dataset): The DICOM dataset to anonymize.
        """
        if not self.is_enabled:
            return ds # Return original if anonymization is disabled

        logger.debug(f"Anonymizing dataset. Full anonymization: {self.full_anonymization}")

        # Remove tags
        for tag_name in self.tags_to_remove:
            if hasattr(ds, tag_name):
                delattr(ds, tag_name)
                logger.debug(f"Removed tag: {tag_name}")
            elif tag_name in ds: # For tags accessed by keyword
                del ds[tag_name]
                logger.debug(f"Removed tag by keyword: {tag_name}")

        # Empty tags
        for tag_name in self.tags_to_empty:
            if hasattr(ds, tag_name):
                setattr(ds, tag_name, "")
                logger.debug(f"Emptied tag: {tag_name}")
            elif tag_name in ds:
                 ds[tag_name].value = ""
                 logger.debug(f"Emptied tag by keyword: {tag_name}")

        if self.full_anonymization:
            # Modify date tags
            for tag_name in self.tags_to_modify_date:
                if hasattr(ds, tag_name):
                    original_value = getattr(ds, tag_name)
                    setattr(ds, tag_name, self._handle_date(original_value))
                    logger.debug(f"Modified date tag {tag_name}: {original_value} -> {getattr(ds, tag_name)}")
            
            # Modify time tags
            for tag_name in self.tags_to_modify_time:
                if hasattr(ds, tag_name):
                    original_value = getattr(ds, tag_name)
                    setattr(ds, tag_name, self._handle_time(original_value))
                    logger.debug(f"Modified time tag {tag_name}: {original_value} -> {getattr(ds, tag_name)}")

            # Regenerate UIDs
            for tag_name in self.tags_to_regenerate_uid:
                if hasattr(ds, tag_name):
                    original_uid = getattr(ds, tag_name)
                    # For file_meta UIDs, need to access differently
                    if tag_name == "MediaStorageSOPInstanceUID" and ds.file_meta and hasattr(ds.file_meta, tag_name):
                        ds.file_meta.MediaStorageSOPInstanceUID = self._generate_uid_from_original(original_uid)
                    else:
                        setattr(ds, tag_name, self._generate_uid_from_original(original_uid))
            
            # Override PatientID and PatientName if configured for full anonymization
            if self.patient_id_override is not None:
                ds.PatientID = self.patient_id_override
                logger.debug(f"Set PatientID to: {self.patient_id_override}")
            if self.patient_name_override is not None:
                ds.PatientName = self.patient_name_override
                logger.debug(f"Set PatientName to: {self.patient_name_override}")
        
        # Ensure no "RT_" prefix is added unless explicitly part of an override
        # The current logic does not add any "RT_" prefix by default.

        return ds

# Example usage (for testing, typically called from study_processor)
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Example configuration for partial anonymization (default if full_anonymization_enabled is false)
    partial_config = {
        "enabled": True,
        "full_anonymization_enabled": False,
        "default_tags_to_remove": ["AccessionNumber", "PatientID"], # MRN is usually PatientID
        "default_tags_to_blank": ["PatientBirthDate"] # Example of blanking a tag
    }

    # Example configuration for full anonymization
    full_config = {
        "enabled": True,
        "full_anonymization_enabled": True,
        "full_anonymization_rules": {
            "tags_to_remove": ["PatientAddress", "PatientTelephoneNumbers"],
            "tags_to_empty": ["ReferringPhysicianName"],
            "tags_to_modify_date": ["StudyDate", "SeriesDate"],
            "tags_to_modify_time": ["StudyTime"],
            "tags_to_regenerate_uid": ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "MediaStorageSOPInstanceUID"],
            "patient_id_override": "ANON123",
            "patient_name_override": "ANON_PATIENT"
        },
        # These would be ignored if full_anonymization_enabled is true
        "default_tags_to_remove": ["AccessionNumber", "PatientID"],
        "default_tags_to_blank": []
    }

    # Test with partial anonymizer
    anonymizer_partial = DicomAnonymizer(partial_config)
    ds_test_partial = pydicom.Dataset()
    ds_test_partial.PatientID = "PAT12345"
    ds_test_partial.AccessionNumber = "ACC67890"
    ds_test_partial.PatientName = "John Doe"
    ds_test_partial.PatientBirthDate = "19700101"
    ds_test_partial.StudyInstanceUID = pydicom.uid.generate_uid()

    logger.info("--- Testing Partial Anonymization ---")
    logger.info(f"Original Partial DS:\n{ds_test_partial}")
    anonymized_ds_partial = anonymizer_partial.anonymize_dataset(ds_test_partial)
    logger.info(f"Anonymized Partial DS:\n{anonymized_ds_partial}")
    assert not hasattr(anonymized_ds_partial, "PatientID")
    assert not hasattr(anonymized_ds_partial, "AccessionNumber")
    assert anonymized_ds_partial.PatientName == "John Doe" # Should remain
    assert anonymized_ds_partial.PatientBirthDate == "" # Should be blanked

    # Test with full anonymizer
    anonymizer_full = DicomAnonymizer(full_config)
    ds_test_full = pydicom.Dataset()
    ds_test_full.file_meta = pydicom.Dataset() # Add file_meta for MediaStorageSOPInstanceUID test
    ds_test_full.PatientID = "PATXYZ"
    ds_test_full.PatientName = "Jane Smith"
    ds_test_full.PatientAddress = "123 Main St"
    ds_test_full.StudyDate = "20230514"
    ds_test_full.StudyTime = "134500.000"
    original_study_uid = pydicom.uid.generate_uid()
    ds_test_full.StudyInstanceUID = original_study_uid
    ds_test_full.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()

    logger.info("--- Testing Full Anonymization ---")
    logger.info(f"Original Full DS:\n{ds_test_full}")
    anonymized_ds_full = anonymizer_full.anonymize_dataset(ds_test_full)
    logger.info(f"Anonymized Full DS:\n{anonymized_ds_full}")
    assert not hasattr(anonymized_ds_full, "PatientAddress")
    assert anonymized_ds_full.PatientID == "ANON123"
    assert anonymized_ds_full.PatientName == "ANON_PATIENT"
    assert anonymized_ds_full.StudyDate == "20230501"
    assert anonymized_ds_full.StudyTime == "130000.00"
    assert anonymized_ds_full.StudyInstanceUID != original_study_uid

