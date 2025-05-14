from pathlib import Path
import os
import numpy as np
from rt_utils import RTStructBuilder
from math import isnan
import highdicom as hd
from pydicom.sr.codedict import codes
from pydicom.filereader import dcmread
from DicomAnonymizer import DicomAnonymizer

class Segmentations:

    def __init__(self, dcm_path, struct_path, seg_path, deidentify, STUDY_INSTANCE_ID='', RAND_ID='', debug=False):
        self.dcm_path = dcm_path
        self.struct_path = struct_path
        self.seg_path = seg_path
        self.deidentify = deidentify
        self.RAND_ID = RAND_ID
        self.StudyInstanceUID = STUDY_INSTANCE_ID

        if deidentify == True:
            print("Segmentation: Starting Anonymizer")
            # Create a minimal anonymization config
            anonymization_config = {
                "enabled": True,
                "full_anonymization_enabled": False,  # Only remove specific tags
                "rules": {
                    "remove_tags": ["AccessionNumber", "PatientID"],
                    "blank_tags": [],
                    "generate_random_id_prefix": ""  # No RT_ prefix by default
                }
            }
            
            # If a RAND_ID is provided, use it for the anonymized IDs
            if RAND_ID:
                anonymization_config["rules"]["generate_random_id_prefix"] = f"RT_{RAND_ID}_"
                
            self.anonymizer = DicomAnonymizer(anonymization_config)
    
    def process(self):

        # Load dicom struct files
        RTstruct= RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        # Provide a list of structures
        structures = RTstruct.get_roi_names()

        # Remove known problematic ROIs
        if '*Skull' in structures:
            structures.remove()

        # Evaluate ROIs
        print(" - Evaluating Segmentations")
        for struct in structures:
            try:
                dummy = RTstruct.get_roi_mask_by_name(struct)
            except Exception:
                print("WARNING: %s is an unreadable ROI." % struct)
                structures.remove(struct)
                continue
            t=np.where(dummy > 0, 1, 0)
            print(" >>> Structure: {} is sized at {}".format(
                struct,
                (dummy > 0 ).sum()
            ))

        print("  - These structures exist in RT:\n", structures)

        # Build Struct masks
        mask_dict = {}

        # overlay layer only supports binary mask. No different colors for each structure
        for struct in structures:
            try:
                # load by name
                mask_3d = RTstruct.get_roi_mask_by_name(struct)

            except KeyError:
                print("ERROR: unable to locate mask: %s" % struct)
                continue

            except Exception as err:
                print("OTHER ERROR: {}".format(err))
                continue

            # Assign mask value for each different mask
            mask_dict[struct] = np.where(mask_3d > 0, True, False)

            # flip the mask
            mask_dict[struct] = np.flip(mask_dict[struct],axis=2)
            
        # check segmentation folder
        if os.path.isdir(self.seg_path) == False:
            os.mkdir(self.seg_path)
        
        for struct in mask_dict.keys():
            mask_array=mask_dict[struct]
            out_file = os.path.join(self.seg_path, struct + ".dcm")
            self.create_segmentation_dcm(self.dcm_path, mask_array, struct, out_file)


    def create_segmentation_dcm(self, reference_dicom, mask_array, struct_name, out_file):
        
        dcm_path=Path(reference_dicom)
        unsorted_image_files = dcm_path.glob('*.dcm')
        
        image_files={}
        for image_file in unsorted_image_files:
            data=dcmread(str(image_file))
            image_files[data.InstanceNumber] = image_file
            
        sorted_image_files = dict(sorted(image_files.items()))
        
        image_datasets = [dcmread(str(value)) for value in list(sorted_image_files.values())]
        
        mask = np.zeros(
            shape=(
                len(image_datasets),
                image_datasets[0].Rows,
                image_datasets[0].Columns
            ),
            dtype=bool
        )
        
        # print(mask.shape)
        
        for i in range(0,mask_array.shape[2],1):
            mask[i] = mask_array[:,:,i]

        # Describe the algorithm that created the segmentation
        algorithm_identification = hd.AlgorithmIdentificationSequence(
            name='Radiation Oncologist',
            version='v1.0',
            family=codes.cid270.Person
        )

        # Describe the segment
        description_segment_1 = hd.seg.SegmentDescription(
            segment_number=1,
            segment_label=struct_name,
            segmented_property_category=codes.cid7150.Tissue,
            segmented_property_type=codes.cid7166.ConnectiveTissue,
            algorithm_type=hd.seg.SegmentAlgorithmTypeValues.MANUAL,
            algorithm_identification=algorithm_identification,
            tracking_uid=hd.UID(),
            tracking_id='FOR RESEARCH USE ONLY'
        )
        
        # Create the Segmentation instance
        seg_dataset = hd.seg.Segmentation(
            source_images=image_datasets,
            pixel_array=mask,
            segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
            segment_descriptions=[description_segment_1],
            series_instance_uid=hd.UID(),
            series_number=99,
            series_description=f"RESEACH USE ONLY : CONTOUR {struct_name}",
            sop_instance_uid=hd.UID(),
            instance_number=1,
            manufacturer=data.Manufacturer,
            manufacturer_model_name=data.ManufacturerModelName,
            software_versions="",
            device_serial_number='',
            omit_empty_frames=False
        )

        # Deidentify the patient information if required
        if self.deidentify == True:
            seg_dataset = self.anonymizer.anonymize(seg_dataset)
            # If RAND_ID is provided, set the patient identifiers directly
            if self.RAND_ID:
                seg_dataset.PatientName = f"RT_{self.RAND_ID}".upper()
                seg_dataset.PatientID = f"RT_{self.RAND_ID}".upper()

        seg_dataset.save_as(out_file)