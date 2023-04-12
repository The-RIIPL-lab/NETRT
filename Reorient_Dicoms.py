import pydicom
import glob
import numpy as np
import os
from pydicom.uid import generate_uid
from pydicom.pixel_data_handlers.numpy_handler import pack_bits
class Reorient_Dicoms:
    def __init__(self, directory):
        self.directory = directory
    def reorient_driver(self):
        imgs = glob.glob(os.path.join(self.directory, '*.dcm'))
        # save the pixel arr in an SL:array dict and then stack the array by ascending order of SL.
        st, arr, overlay_arr = {}, [], []
        for img_ in imgs:
            try:
                img = pydicom.read_file(img_)
                x, y, z = img.ImagePositionPatient
                st[(x, y, z)] = (img.pixel_array, img.overlay_array(0x6000))
            except:
                # Some dicom doesn't include pixel info. ignore them.
                print(img_)
        # find the origin of the coordinate
        origin = [float(x) for x in min(st.keys())]
        for i in sorted(st.keys(), key=lambda x: x[2]):
            arr.append(st[i][0])
            overlay_arr.append(st[i][1])
        img_3d = np.stack(arr)
        overlay_3d = np.stack(overlay_arr)
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
            overlay_downsampling = overlay_3d[::-1, x, :]
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
            try:
                tbs[0x6000, 0x0010].value = overlay_downsampling.shape[0]
                tbs[0x6000, 0x0011].value = overlay_downsampling.shape[1]
                tbs[0x6000, 0x3000].value = pack_bits(overlay_downsampling)
            except:
                tbs.add_new((0x6000, 0x0010), 'US', data_downsampling.shape[0])
                tbs.add_new((0x6000, 0x0011), 'US', data_downsampling.shape[1])
                tbs.add_new((0x6000, 0x3000), 'OW', pack_bits(overlay_downsampling))
            save_name = imgs[0].replace('.dcm', f'.x-{x}.dcm')
            tbs.save_as(save_name)
            test = pydicom.read_file(save_name).overlay_array(0x6000)
            if overlay_downsampling.max()==1:                
                print(save_name)
        for y in range(img_3d.shape[2]):
            data_downsampling = img_3d[::-1, :, y]
            overlay_downsampling = overlay_3d[::-1, :, y]
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
            try:
                tbs[0x6000, 0x0010].value = overlay_downsampling.shape[0]
                tbs[0x6000, 0x0011].value = overlay_downsampling.shape[1]
                tbs[0x6000, 0x3000].value = pack_bits(overlay_downsampling)
            except:
                tbs.add_new((0x6000, 0x0010), 'US', data_downsampling.shape[0])
                tbs.add_new((0x6000, 0x0011), 'US', data_downsampling.shape[1])
                tbs.add_new((0x6000, 0x3000), 'OW', pack_bits(overlay_downsampling))
            save_name = imgs[0].replace('.dcm', f'.y-{y}.dcm')
            tbs.save_as(save_name)