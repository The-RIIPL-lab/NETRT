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
        SeriesInstanceUID = tbs.SeriesInstanceUID
        try:
            SeriesDescription = tbs.SeriesDescription
        except:
            SeriesDescription = ''
        
        # write new dicom series
        for x in range(img_3d.shape[1]):
            data_downsampling = img_3d[::-1, x, :]
            # edit header info
            tbs.PixelSpacing = [z_spacing, y_spacing]
            tbs.InstanceNumber = x
            tbs.ImagePositionPatient = [origin[1], origin[2], x * x_spacing + origin[0]]
            tbs.SliceLocation = str(x * x_spacing + origin[0])
            tbs.ImageOrientationPatient = [z_spacing, 0, 0, 0, y_spacing, 0]
            #     tbs.ImageType=['ORIGINAL', 'PRIMARY', 'OTHER']
            tbs.SliceThickness = x_spacing
            tbs.SpacingBetweenSlices = x_spacing
            tbs.SeriesDescription = SeriesDescription + ' coronal view'
        
            # to distinguish with the original series, modify the series id
            tbs.SeriesInstanceUID = SeriesInstanceUID + '.1'
            # copy the data back to the original data set
            tbs.PixelData = data_downsampling.tobytes()
            # update the information regarding the shape of the data array
            tbs.Rows, tbs.Columns = data_downsampling.shape
            #  the new series will be saved in the same directory as the original dicom with different suffix.
            
            save_name = imgs[0].replace('.dcm', f'.x-{x}.dcm')
            
            new_series_uid1 = generate_uid(prefix=None)
            tbs.SeriesInstanceUID = '1.' + new_series_uid1
            
            tbs.save_as(save_name)
        
        for y in range(img_3d.shape[2]):
            data_downsampling = img_3d[::-1, :, y]
            # edit header info
            tbs.PixelSpacing = [z_spacing, x_spacing]
            tbs.InstanceNumber = y
            tbs.ImagePositionPatient = [origin[0], origin[2], y * y_spacing + origin[1]]
            tbs.SliceLocation = str(y * y_spacing + origin[1])
            tbs.ImageOrientationPatient = [z_spacing, 0, 0, 0, x_spacing, 0]
            #     tbs.ImageType=['ORIGINAL', 'PRIMARY', 'OTHER']
            tbs.SliceThickness = y_spacing
            tbs.SpacingBetweenSlices = y_spacing
            tbs.SeriesDescription = SeriesDescription + ' sagittal view'
        
            # to distinguish with the original series, modify the series id
            tbs.SeriesInstanceUID = SeriesInstanceUID + '.2'
            # copy the data back to the original data set
            tbs.PixelData = data_downsampling.tobytes()
            # update the information regarding the shape of the data array
            tbs.Rows, tbs.Columns = data_downsampling.shape
            #  the new series will be saved in the same directory as the original dicom with different suffix.
            save_name = imgs[0].replace('.dcm', f'.y-{y}.dcm')
            
            new_series_uid2 = generate_uid(prefix=None)
            tbs.SeriesInstanceUID = '2.' + new_series_uid2
            
            tbs.save_as(save_name)
