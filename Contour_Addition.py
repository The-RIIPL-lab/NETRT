import os
import numpy as np
from pydicom import uid
from pydicom.tag import Tag
from pydicom import dcmread
from rt_utils import RTStructBuilder
from pydicom.pixels import pack_bits
import datetime
import re
from DicomAnonymizer import DicomAnonymizer

class ContourAddition:

    def __init__(self, dcm_path, struct_path, deidentify, STUDY_INSTANCE_ID='', CT_SOPInstanceUID='', FOD_REF_ID='', RAND_ID=''):
        self.dcm_path = dcm_path
        self.struct_path = struct_path
        self.deidentify = deidentify
        self.RAND_ID = RAND_ID
        self.SOPInstanceUID = CT_SOPInstanceUID
        self.StudyInstanceUID = STUDY_INSTANCE_ID
        self.FrameOfReferenceUID = FOD_REF_ID

        if deidentify == True:
            print("Addition: Starting Anonymizer")
            # Create a minimal anonymization config
            anonymization_config = {
                "enabled": True,
                "full_anonymization_enabled": False,  # Only remove specific tags
                "rules": {
                    "remove_tags": ["AccessionNumber", "PatientID" ],
                    "blank_tags": [],
                    "generate_random_id_prefix": ""  # No RT_ prefix by default
                }
            }
            
            # If a RAND_ID is provided, use it for the anonymized IDs
            if RAND_ID:
                anonymization_config["rules"]["generate_random_id_prefix"] = f"RT_{RAND_ID}_"
                
            self.anonymizer = DicomAnonymizer(anonymization_config)

    def process(self):

        # Generate a new SeriesInstanceUID for the series
        SeriesInstanceUID = uid.generate_uid()

        # Debug - print this path again
        print("DICOM Path:", self.dcm_path)

        # Load dicom files
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
        print("  - Evaluating Segmentations")
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
            mask_dict[struct] = np.where(mask_3d > 0, 1, 0)

            # flip the mask
            mask_dict[struct] = np.flip(mask_dict[struct], axis=2)
            
        # get a list of all structural files
        files = os.listdir(self.dcm_path)

        # Create Overlay layer function
        output_directory = os.path.join(os.path.dirname(os.path.abspath(self.dcm_path)), 'Addition')

        if os.path.isdir(output_directory) == False:
            os.mkdir(output_directory)

        def add_overlay_layers(ds, mask_dict, match):
            slice_number = int(match) - 1
            slice_str = str(slice_number)
            
            # add padding 0s dynamically
            if len(slice_str) < 5:
               slice_str  = '0' * (5 - len(slice_str)) + slice_str

            hex_start = 0x6000

            MediaSOPClassUID = '1.2.840.10008.5.1.4.1.1.2' # defined for the whole scan series

            for mask in mask_dict.keys():
                mask_array = mask_dict[mask]
                mask_slice = mask_array[:, :, slice_number]
                mask_slice = np.ma.masked_where(mask_slice == 0, mask_slice)
                    
                packed_bytes = pack_bits(mask_slice)

                # These classes are consistent
                #ds.file_meta.MediaSOPClassUID = MediaSOPClassUID
                ds.SOPClassUID = MediaSOPClassUID

                # There change image to image
                ds.file_meta.MediaSOPInstanceUID = uid.generate_uid(prefix='1.2.840.10008.5.1.4.1.1.2.')
                ds.SOPInstanceUID = ds.file_meta.MediaSOPInstanceUID 
                
                ds.StudyDescription = "RESEARCH ONLY: Unapproved Treatment Plan CT w Mask"
                ds.SeriesDescription = "RESEARCH ONLY: Unapproved Treatment Plan CT w Mask"

                # Consistent within all study/session/scans
                #ds.StudyInstanceUID = self.StudyInstanceUID

                # Different for each scan in the series, but same image to image
                ds.SeriesInstanceUID = SeriesInstanceUID

                ds.SeriesNumber = 98
                
                # Consistent within all study/session/scans
                #ds.FrameOfReferenceUID = self.FrameOfReferenceUID

                ds.Modality = 'CT'
                ds.ContentDate = str(datetime.date.today()).replace('-','')
                ds.AcquisitionDate = str(datetime.date.today()).replace('-','')
                ds.SeriesDate = str(datetime.date.today()).replace('-','')
                ds.StudyDate = str(datetime.date.today()).replace('-','')

                ds.add_new(Tag(hex_start, 0x0040), 'CS', 'R')
                ds.add_new(Tag(hex_start, 0x0050), 'SS', [1, 1])
                ds.add_new(Tag(hex_start, 0x0100), 'US', 8)
                ds.add_new(Tag(hex_start, 0x0102), 'US', 0)
                ds.add_new(Tag(hex_start, 0x022), 'LO', mask)
                ds.add_new(Tag(hex_start, 0x1500), 'LO', mask)
                ds.add_new(Tag(hex_start, 0x3000), 'OW', packed_bytes)
                ds.add_new(Tag(hex_start, 0x0010), 'US', mask_slice.shape[0])
                ds.add_new(Tag(hex_start, 0x0011), 'US', mask_slice.shape[1])

                ds.StudyID = "RTPlanShare"

                dt = datetime.time(0, 1, 1, 10)
                ds.StudyTime = dt.strftime('%H%M%S.%f')

                dt = datetime.time(0, 1, 3, 30)
                ds.SeriesTime = dt.strftime('%H%M%S.%f')

                dt = datetime.time(0, 1, 7, 30)
                ds.ContentTime = dt.strftime('%H%M%S.%f')

                dt = datetime.time(0, 1, 9, 30)
                ds.AcquisitionTime = dt.strftime('%H%M%S.%f')

                if (0x0040, 0x0275) in ds:
                    del ds[0x0040, 0x0275]
                if (0x0010, 0x1000) in ds:
                    del ds[0x0010, 0x1000] # delete retired IDs

                if (0x0008, 0x0012) in ds:
                    del ds[0x0008, 0x0012] # delete instance creation dates
                    del ds[0x0008, 0x0013] # delete Instance cretaion times
                
                if self.deidentify == True:
                    anonymized_dcm = self.anonymizer.anonymize(ds)
                    
                    # If RAND_ID is provided, set the patient identifiers directly
                    # This allows backward compatibility with the original code
                    if self.RAND_ID:
                        anonymized_dcm.PatientID = f"RT_{self.RAND_ID}".upper()
                        anonymized_dcm.PatientName = f"RT_{self.RAND_ID}".upper()
                        
                    hex_start = hex_start + 2
                    out_fn = os.path.join(output_directory, f"CT-with-overlay-{slice_str}.dcm")
                    anonymized_dcm.save_as(out_fn)
                    return anonymized_dcm
                else:
                    hex_start = hex_start + 2
                    out_fn = os.path.join(output_directory, f"CT-with-overlay-{slice_str}.dcm")
                    ds.save_as(out_fn)
                    return ds


        ## FROM PYDICOM EXAMPLE
        # Read the anatomical dicom file
        # skip files with no SliceLocation (eg scout views)
        slices = []
        skipcount = 0
        
        def get_sort_key(filename):
            """
            Determines the sort key for a DICOM file.
            Tries to extract the last integer from the filename. If that fails,
            it reads the DICOM file and uses the InstanceNumber tag.
            """
            try:
                # Primary method: extract the last integer from the filename.
                return int(re.findall(r'\d+', filename)[-1])
            except (IndexError, ValueError):
                # Fallback method: read the InstanceNumber from the DICOM header.
                print(f"Could not find slice number in filename '{filename}', falling back to DICOM header.")
                try:
                    full_path = os.path.join(self.dcm_path, filename)
                    dcm = dcmread(full_path, stop_before_pixels=True)
                    return dcm.InstanceNumber
                except Exception as e:
                    # If DICOM header reading fails, return a large number to sort it last.
                    print(f"Could not read DICOM header for {filename}: {e}. It will be sorted last.")
                    return float('inf')

        files.sort(key=get_sort_key)
        print("file count: {}".format(len(files)))

        #SeriesInstanceUID = pydicom.uid.generate_uid() # defined for the whole scan series
        
        headers = []
        
        for f in files:
            ds = dcmread(os.path.join(self.dcm_path, f))
            headers.append((ds[0x0020, 0x0013].value, f))
    
            # sort by header information (image number) and return a list of filenames sorted accordingly 
            files = [f for _, f in sorted(headers)]
            
        counter = 0

        for f in files:
        
            counter = counter + 1

            fds = dcmread(os.path.join(self.dcm_path, f))
            number = f.split('.')[-2]
            
            if int(number) > 300:
              number = fds.ImagePositionPatient[2]
              print(" >> File Number %i" % number)
            
            if hasattr(fds, 'SliceLocation'):
                # Add the overlay layer
                # fds = add_overlay_layers(fds, mask_dict, number)
                slices.append(fds)
                fds = add_overlay_layers(fds, mask_dict, counter)
            else:
                skipcount = skipcount + 1

        print("skipped, no SliceLocation: {}".format(skipcount))