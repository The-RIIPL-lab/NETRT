import pydicom
import glob
import numpy as np
import os
from pydicom.uid import generate_uid


class Reorient_Dicoms:

    def __init__(self, directory):
        self.directory = directory

    def reorient_driver(self):

        imgs = glob.glob(os.path.join(self.directory, '*.dcm'))

        # save the pixel arr in an SL:array dict and then stack the array by ascending order of SL.
        st, arr = {}, []

        for img_ in imgs:
            try:
                img = pydicom.read_file(img_)
                x, y, z = img.ImagePositionPatient
                st[(x, y, z)] = img.pixel_array
            except:
                # Some dicom doesn't include pixel info. ignore them.
                print(img_)

        # find the origin of the coordinate
        origin = [float(x) for x in min(st.keys())]
        for i in sorted(st.keys(), key=lambda x: x[2]):
            arr.append(st[i])
        img_3d = np.stack(arr)

        # read the header info
        tbs = pydicom.read_file(imgs[0])
        z_spacing = tbs.SliceThickness
        x_spacing = tbs.PixelSpacing[0]
        y_spacing = tbs.PixelSpacing[1]
        StudyInstanceUID = tbs.StudyInstanceUID
        SeriesInstanceUID = tbs.SeriesInstanceUID
        try:
            SeriesDescription = tbs.SeriesDescription
        except:
            SeriesDescription = ''

        new_series_uid1 = generate_uid(prefix=None)
        new_series_uid2 = generate_uid(prefix=None)

        # create folders for coronal and sagittal views
        # coronal_dir = os.path.join(self.directory, 'coronal')
        # sagittal_dir = os.path.join(self.directory, 'sagittal')
        
        # os.makedirs(coronal_dir, exist_ok=True)
        # os.makedirs(sagittal_dir, exist_ok=True)

        # write new dicom series for coronal view
        for x in range(img_3d.shape[1]):
            data_downsampling = img_3d[::-1, x, :]
            # edit header info
            tbs.PixelSpacing = [z_spacing, y_spacing]
            tbs.InstanceNumber = x
            tbs.ImagePositionPatient = [origin[1], origin[2], x * x_spacing + origin[0]]
            tbs.SliceLocation = '{:.2f}'.format(x * x_spacing + origin[0])  # Round to 2 decimal places
            tbs.ImageOrientationPatient = [0, 0, -1, 0, -1, 0]  # Update for coronal view
            tbs.SliceThickness = x_spacing
            tbs.SpacingBetweenSlices = x_spacing
            tbs.SeriesDescription = SeriesDescription + ' coronal view'

            tbs.SeriesInstanceUID = new_series_uid1
            tbs.StudyInstanceUID = StudyInstanceUID

            tbs.PixelData = data_downsampling.tobytes()
            tbs.Rows, tbs.Columns = data_downsampling.shape
            save_name = imgs[0].replace('.dcm', f'.x-{x}.dcm')
            
            print(save_name)

            tbs.save_as(save_name)
            
        for y in range(img_3d.shape[2]):
            data_downsampling = img_3d[::-1, :, y]
            # edit header info
            tbs.PixelSpacing = [z_spacing, x_spacing]
            tbs.InstanceNumber = y
            tbs.ImagePositionPatient = [origin[0], origin[2], y * y_spacing + origin[1]]
            tbs.SliceLocation = '{:.2f}'.format(y * y_spacing + origin[1])
            tbs.ImageOrientationPatient = [0, -1, 0, 0, 0, -1]  # Update for sagittal view
            tbs.SliceThickness = y_spacing
            tbs.SpacingBetweenSlices = y_spacing
            tbs.SeriesDescription = SeriesDescription + ' sagittal view'
    
            tbs.SeriesInstanceUID = new_series_uid2
            tbs.StudyInstanceUID = StudyInstanceUID
    
            tbs.PixelData = data_downsampling.tobytes()
            tbs.Rows, tbs.Columns = data_downsampling.shape
    
            save_name = imgs[0].replace('.dcm', f'.y-{y}.dcm')
    
            tbs.save_as(save_name)