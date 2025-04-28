from pathlib import Path
import numpy as np
from rt_utils import RTStructBuilder
from math import isnan
import highdicom as hd
from pydicom.sr.codedict import codes
from pydicom.filereader import dcmread
from DicomAnonymizer import DicomAnonymizer
from logger_module import setup_logger

# Get logger
logger = setup_logger()

class Segmentations:
    """
    Class for creating DICOM-SEG files from RT structure sets.
    
    This class processes DICOM RT structure sets to create DICOM segmentation objects
    that can be displayed in standard DICOM viewers.
    """

    def __init__(self, dcm_path, struct_path, seg_path, deidentify, STUDY_INSTANCE_ID='', RAND_ID='', debug=False):
        """
        Initialize the Segmentations processor.
        
        Args:
            dcm_path (str or Path): Path to the directory containing DICOM image files
            struct_path (str or Path): Path to the RT structure set file
            seg_path (str or Path): Path to save the output segmentation files
            deidentify (bool): Whether to anonymize the output segmentation files
            STUDY_INSTANCE_ID (str, optional): Study instance UID to use if deidentifying
            RAND_ID (str, optional): Random ID to use for anonymization
            debug (bool, optional): Enable debug mode
        """
        self.dcm_path = dcm_path
        self.struct_path = struct_path
        self.seg_path = seg_path
        self.deidentify = deidentify
        self.RAND_ID = RAND_ID
        self.StudyInstanceUID=STUDY_INSTANCE_ID

        if deidentify == True:
            logger.info("Starting Anonymizer")
            self.anonymizer = DicomAnonymizer()
    
    def process(self):
        """
        Process the RT structure set to create DICOM-SEG files.
        
        This method:
        1. Loads the RT structure set
        2. Extracts structures from the RT structure set
        3. Creates a binary mask for each structure
        4. Creates a DICOM-SEG file for each structure
        
        Returns:
            None
        """
        # Load dicom struct files
        RTstruct= RTStructBuilder.create_from(
            dicom_series_path=self.dcm_path,
            rt_struct_path=self.struct_path
        )

        # Provide a filtered list of structures (exclude known problematic ones)
        orig_structures = RTstruct.get_roi_names()
        structures = [s for s in orig_structures if s != '*Skull']

        # Evaluate segmentations without mutating the list during iteration
        valid_structures = []
        logger.info("Evaluating Segmentations")
        for struct in structures:
            try:
                dummy = RTstruct.get_roi_mask_by_name(struct)
            except Exception:
                logger.warning(f"{struct} is an unreadable ROI.")
                continue
            count = (dummy > 0).sum()
            logger.info(f"Structure: {struct} is sized at {count}")
            valid_structures.append(struct)

        structures = valid_structures
        logger.info(f"These structures exist in RT: {structures}")

        # Build Struct masks
        mask_dict = {}

        # overlay layer only supports binary mask. No different colors for each structure
        for struct in structures:
            try:
                # load by name
                mask_3d = RTstruct.get_roi_mask_by_name(struct)

            except KeyError:
                logger.error(f"Unable to locate mask: {struct}")
                continue

            except Exception as err:
                logger.error(f"Error processing structure {struct}: {err}")
                continue

            # Assign mask value for each different mask
            mask_dict[struct] = np.where(mask_3d > 0, True, False)

            # flip the mask
            mask_dict[struct] = np.flip(mask_dict[struct],axis=2)
            
        # check/create segmentation folder using pathlib
        seg_dir = Path(self.seg_path)
        seg_dir.mkdir(exist_ok=True)
        
        for struct, mask_array in mask_dict.items():
            out_file = seg_dir / f"{struct}.dcm"
            self.create_segmentation_dcm(self.dcm_path, mask_array, struct, out_file)


    def create_segmentation_dcm(self, reference_dicom, mask_array, struct_name, out_file):
        """
        Create a DICOM-SEG file from a binary mask.
        
        Args:
            reference_dicom (str or Path): Path to the directory containing reference DICOM files
            mask_array (numpy.ndarray): 3D binary mask representing the structure
            struct_name (str): Name of the structure
            out_file (str or Path): Path to save the output DICOM-SEG file
            
        Returns:
            None
        """
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
            seg_dataset.PatientName = str("RT_" + self.RAND_ID).upper()
            seg_dataset.PatientID = str("RT_" + self.RAND_ID).upper()

        seg_dataset.save_as(out_file)