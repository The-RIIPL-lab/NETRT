#!/usr/bin/env python3
import os
import sys
import pydicom
import logging
from DicomAnonymizer import DicomAnonymizer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_dicom():
    """Create a sample DICOM file for testing"""
    ds = pydicom.Dataset()
    ds.PatientName = "TEST^PATIENT"
    ds.PatientID = "TEST12345"
    ds.AccessionNumber = "ACC123456"
    ds.Modality = "CT"
    ds.StudyInstanceUID = "1.2.3.4.5.6"
    ds.SeriesInstanceUID = "1.2.3.4.5.6.1"
    ds.SOPInstanceUID = "1.2.3.4.5.6.1.1"
    ds.file_meta = pydicom.Dataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = True
    return ds

def test_regular_anonymization():
    """Test regular (partial) anonymization"""
    logger.info("=== Testing Regular Anonymization ===")
    
    # Create config that matches the default settings
    config = {
        "enabled": True,
        "full_anonymization_enabled": False,
        "rules": {
            "remove_tags": ["AccessionNumber", "PatientID"],
            "blank_tags": [],
            "generate_random_id_prefix": ""
        }
    }
    
    # Create anonymizer with this config
    anonymizer = DicomAnonymizer(config)
    
    # Create test dataset
    ds = create_test_dicom()
    logger.info(f"Original DICOM: PatientName={ds.PatientName}, PatientID={ds.PatientID}, AccessionNumber={ds.AccessionNumber}")
    
    # Apply anonymization
    anonymizer.anonymize(ds)
    
    # Check results
    logger.info(f"After regular anonymization:")
    logger.info(f"PatientName={ds.PatientName if hasattr(ds, 'PatientName') else 'REMOVED'}")
    logger.info(f"PatientID={ds.PatientID if hasattr(ds, 'PatientID') else 'REMOVED'}")
    logger.info(f"AccessionNumber={ds.AccessionNumber if hasattr(ds, 'AccessionNumber') else 'REMOVED'}")
    
    # Verify that PatientID and AccessionNumber are removed
    assert not hasattr(ds, 'PatientID'), "PatientID should be removed"
    assert not hasattr(ds, 'AccessionNumber'), "AccessionNumber should be removed"
    # Verify that PatientName is preserved
    assert hasattr(ds, 'PatientName'), "PatientName should be preserved"
    assert ds.PatientName == "TEST^PATIENT", "PatientName should not be changed"
    
    logger.info("Regular anonymization test: PASSED")

def test_full_anonymization():
    """Test full anonymization"""
    logger.info("\n=== Testing Full Anonymization ===")
    
    # Create config for full anonymization
    config = {
        "enabled": True,
        "full_anonymization_enabled": True,
        "rules": {
            "remove_tags": ["AccessionNumber", "PatientID"],
            "blank_tags": [],
            "generate_random_id_prefix": "TEST_"
        }
    }
    
    # Create anonymizer with this config
    anonymizer = DicomAnonymizer(config)
    
    # Create test dataset
    ds = create_test_dicom()
    original_uid = ds.StudyInstanceUID
    logger.info(f"Original DICOM: PatientName={ds.PatientName}, PatientID={ds.PatientID}, AccessionNumber={ds.AccessionNumber}")
    logger.info(f"Original UIDs: StudyInstanceUID={ds.StudyInstanceUID}")
    
    # Apply anonymization
    anonymizer.anonymize(ds)
    
    # Check results
    logger.info(f"After full anonymization:")
    logger.info(f"PatientName={ds.PatientName if hasattr(ds, 'PatientName') else 'REMOVED'}")
    logger.info(f"PatientID={ds.PatientID if hasattr(ds, 'PatientID') else 'REMOVED'}")
    logger.info(f"AccessionNumber={ds.AccessionNumber if hasattr(ds, 'AccessionNumber') else 'REMOVED'}")
    logger.info(f"StudyInstanceUID={ds.StudyInstanceUID}")
    
    # Verify that PatientName has been changed to an anonymous value
    assert hasattr(ds, 'PatientName'), "PatientName should exist but be anonymized"
    assert "ANONYMOUS" in str(ds.PatientName), "PatientName should contain ANONYMOUS"
    
    # Verify UIDs have been changed
    assert ds.StudyInstanceUID != original_uid, "StudyInstanceUID should be changed"
    
    logger.info("Full anonymization test: PASSED")

def test_disabled_anonymization():
    """Test behavior when anonymization is disabled"""
    logger.info("\n=== Testing Disabled Anonymization ===")
    
    # Create config with anonymization disabled
    config = {
        "enabled": False,
        "full_anonymization_enabled": False,
        "rules": {
            "remove_tags": ["AccessionNumber", "PatientID"],
            "blank_tags": [],
            "generate_random_id_prefix": ""
        }
    }
    
    # Create anonymizer with this config
    anonymizer = DicomAnonymizer(config)
    
    # Create test dataset
    ds = create_test_dicom()
    logger.info(f"Original DICOM: PatientName={ds.PatientName}, PatientID={ds.PatientID}, AccessionNumber={ds.AccessionNumber}")
    
    # Apply anonymization
    anonymizer.anonymize(ds)
    
    # Check results
    logger.info(f"After disabled anonymization:")
    logger.info(f"PatientName={ds.PatientName if hasattr(ds, 'PatientName') else 'REMOVED'}")
    logger.info(f"PatientID={ds.PatientID if hasattr(ds, 'PatientID') else 'REMOVED'}")
    logger.info(f"AccessionNumber={ds.AccessionNumber if hasattr(ds, 'AccessionNumber') else 'REMOVED'}")
    
    # Verify that AccessionNumber is still removed (per requirements)
    assert not hasattr(ds, 'AccessionNumber') or ds.AccessionNumber == "", "AccessionNumber should be removed even when anonymization is disabled"
    
    # PatientID should be handled according to config
    if "PatientID" in config["rules"]["remove_tags"]:
        assert not hasattr(ds, 'PatientID') or ds.PatientID == "", "PatientID should be removed as specified in the config"
    
    # PatientName should be preserved
    assert hasattr(ds, 'PatientName'), "PatientName should be preserved"
    assert ds.PatientName == "TEST^PATIENT", "PatientName should not be changed when anonymization is disabled"
    
    logger.info("Disabled anonymization test: PASSED")

if __name__ == "__main__":
    try:
        test_regular_anonymization()
        test_full_anonymization()
        test_disabled_anonymization()
        logger.info("\nAll tests PASSED!")
    except AssertionError as e:
        logger.error(f"Test FAILED: {e}")
        sys.exit(1)