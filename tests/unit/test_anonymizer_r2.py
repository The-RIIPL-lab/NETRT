import unittest
import pydicom
import os
import yaml
import shutil

# Adjust import path to access DicomAnonymizer from the parent directory of netrt_core
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from DicomAnonymizer import DicomAnonymizer # Assuming DicomAnonymizer.py is in the root NETRT directory
from netrt_core.config_loader import load_config, DEFAULT_CONFIG

class TestDicomAnonymizerRound2(unittest.TestCase):

    def setUp(self):
        """Set up test environment; create dummy DICOM files and configs."""
        self.test_dir = "/tmp/test_anonymizer_r2"
        os.makedirs(self.test_dir, exist_ok=True)

        # Create a sample DICOM dataset
        self.ds = pydicom.Dataset()
        self.ds.PatientName = "Test^Patient"
        self.ds.PatientID = "PAT12345"
        self.ds.AccessionNumber = "ACC67890"
        self.ds.StudyInstanceUID = pydicom.uid.generate_uid()
        self.ds.SeriesInstanceUID = pydicom.uid.generate_uid()
        self.ds.SOPInstanceUID = pydicom.uid.generate_uid()
        self.ds.PatientBirthDate = "19800101"
        self.ds.StudyDate = "20230101"
        self.ds.StudyTime = "120000"
        self.ds.InstitutionName = "Test Hospital"
        self.ds.file_meta = pydicom.Dataset() # Add file_meta for MediaStorageSOPInstanceUID test
        self.ds.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()

        # Default config for partial anonymization (as per config_loader.py)
        self.partial_anon_config = {
            "enabled": True,
            "full_anonymization_enabled": False,
            "default_tags_to_remove": ["AccessionNumber", "PatientID"],
            "default_tags_to_blank": ["PatientBirthDate"],
            # full_anonymization_rules are ignored here
        }

        # Config for full anonymization (as per config_loader.py)
        self.full_anon_config = {
            "enabled": True,
            "full_anonymization_enabled": True,
            "full_anonymization_rules": {
                "tags_to_remove": ["PatientName", "AccessionNumber", "InstitutionName"],
                "tags_to_empty": ["PatientBirthDate"],
                "tags_to_modify_date": ["StudyDate"],
                "tags_to_modify_time": ["StudyTime"],
                "tags_to_regenerate_uid": ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "MediaStorageSOPInstanceUID"],
                "patient_id_override": "ANON_FULL_ID",
                "patient_name_override": "ANON_FULL_NAME" # This will be applied if PatientName is not in tags_to_remove
            },
             # default rules are ignored when full_anonymization_enabled is true
            "default_tags_to_remove": [], 
            "default_tags_to_blank": []
        }
        
        # Config with anonymization disabled
        self.disabled_anon_config = {
            "enabled": False,
            "full_anonymization_enabled": False # This doesn't matter if enabled is False
        }

    def tearDown(self):
        """Clean up test environment."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_partial_anonymization(self):
        """Test partial anonymization based on default_tags_to_remove/blank."""
        anonymizer = DicomAnonymizer(self.partial_anon_config)
        ds_anon = self.ds.copy()
        anonymizer.anonymize_dataset(ds_anon)

        self.assertNotIn("AccessionNumber", ds_anon)
        self.assertNotIn("PatientID", ds_anon)
        self.assertEqual(ds_anon.PatientBirthDate, "")
        self.assertEqual(ds_anon.PatientName, "Test^Patient") # Should remain
        self.assertEqual(ds_anon.StudyInstanceUID, self.ds.StudyInstanceUID) # Should not be regenerated
        self.assertEqual(ds_anon.InstitutionName, "Test Hospital") # Should remain

    def test_full_anonymization(self):
        """Test full anonymization based on full_anonymization_rules."""
        anonymizer = DicomAnonymizer(self.full_anon_config)
        ds_anon = self.ds.copy()
        original_study_uid = ds_anon.StudyInstanceUID
        original_sop_uid = ds_anon.SOPInstanceUID
        original_media_sop_uid = ds_anon.file_meta.MediaStorageSOPInstanceUID

        anonymizer.anonymize_dataset(ds_anon)

        self.assertNotIn("AccessionNumber", ds_anon)
        self.assertNotIn("InstitutionName", ds_anon)
        # PatientName is in tags_to_remove for this specific full_anon_config, so it should be removed.
        # If patient_name_override was to be used, PatientName should not be in tags_to_remove.
        # Let's adjust the test config slightly for clarity on override vs remove.
        
        # Re-test with PatientName NOT in tags_to_remove to check override
        current_full_config = yaml.safe_load(yaml.safe_dump(self.full_anon_config)) # deepcopy
        current_full_config["full_anonymization_rules"]["tags_to_remove"] = ["AccessionNumber", "InstitutionName"] # PatientName removed from remove list
        anonymizer_override_test = DicomAnonymizer(current_full_config)
        ds_anon_override = self.ds.copy()
        anonymizer_override_test.anonymize_dataset(ds_anon_override)
        self.assertEqual(ds_anon_override.PatientName, "ANON_FULL_NAME")
        self.assertEqual(ds_anon_override.PatientID, "ANON_FULL_ID")

        # Original full test with PatientName in tags_to_remove
        anonymizer_remove_test = DicomAnonymizer(self.full_anon_config) # Original full_anon_config
        ds_anon_remove = self.ds.copy()
        anonymizer_remove_test.anonymize_dataset(ds_anon_remove)
        self.assertNotIn("PatientName", ds_anon_remove) # Removed as per config
        self.assertEqual(ds_anon_remove.PatientID, "ANON_FULL_ID") # Overridden

        self.assertEqual(ds_anon_remove.PatientBirthDate, "") # Emptied
        self.assertEqual(ds_anon_remove.StudyDate, "20230101"[:6] + "01") # Modified
        self.assertEqual(ds_anon_remove.StudyTime, "12" + "0000.00") # Modified
        self.assertNotEqual(ds_anon_remove.StudyInstanceUID, original_study_uid)
        self.assertNotEqual(ds_anon_remove.SOPInstanceUID, original_sop_uid)
        self.assertNotEqual(ds_anon_remove.file_meta.MediaStorageSOPInstanceUID, original_media_sop_uid)

    def test_anonymization_disabled(self):
        """Test that no changes occur if anonymization is disabled."""
        anonymizer = DicomAnonymizer(self.disabled_anon_config)
        ds_original_copy = self.ds.copy()
        ds_processed = self.ds.copy()
        anonymizer.anonymize_dataset(ds_processed)
        self.assertEqual(ds_processed, ds_original_copy) # No changes should be made

    def test_empty_config_rules(self):
        """Test behavior with empty rule lists in config."""
        empty_rules_config = {
            "enabled": True,
            "full_anonymization_enabled": True,
            "full_anonymization_rules": {
                "tags_to_remove": [],
                "tags_to_empty": [],
                "tags_to_modify_date": [],
                "tags_to_modify_time": [],
                "tags_to_regenerate_uid": [],
                "patient_id_override": "EMPTY_ID",
                "patient_name_override": "EMPTY_NAME"
            }
        }
        anonymizer = DicomAnonymizer(empty_rules_config)
        ds_anon = self.ds.copy()
        anonymizer.anonymize_dataset(ds_anon)

        self.assertEqual(ds_anon.PatientName, "EMPTY_NAME")
        self.assertEqual(ds_anon.PatientID, "EMPTY_ID")
        self.assertEqual(ds_anon.AccessionNumber, self.ds.AccessionNumber) # Should remain
        self.assertEqual(ds_anon.StudyDate, self.ds.StudyDate) # Should remain

if __name__ == "__main__":
    unittest.main()

