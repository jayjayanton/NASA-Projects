import gdal
import glob
import os
import numpy as np
import osr
#import rasterio

nc_prefix = 'HDF4_EOS:EOS_GRID:"'
soil_suffix = '":MOD_Grid_monthly_1km_VI:1 km monthly NDVI'

NCfilenames = sorted(glob.glob("*.hdf"))
#print(NCfilenames)
count = 0

for ncfile in NCfilenames:
    #print(ncfile)
    basencfilename = os.path.basename(ncfile)
    #print(basencfilename)

    deepsoil_name = nc_prefix + basencfilename + soil_suffix
    CleanBaseStr = os.path.splitext(basencfilename)[0]
    OutFileName = CleanBaseStr + "_NDVI"

    deepsoil_ds = gdal.Open(deepsoil_name, gdal.GA_ReadOnly)
    width = deepsoil_ds.RasterXSize
    height = deepsoil_ds.RasterYSize
    deepsoil_band = deepsoil_ds.GetRasterBand(1)
    deepsoil_arr = deepsoil_band.ReadAsArray()

    gt = deepsoil_ds.GetGeoTransform()

    #gt2 = (-82.266, geotransform[1], geotransform[2], -2.596, geotransform[4], 1)

    wkt = deepsoil_ds.GetProjection()
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(OutFileName, deepsoil_band.XSize, deepsoil_band.YSize, 1, gdal.GDT_Int16)
    #writing output raster
    out_ds.GetRasterBand(1).WriteArray(deepsoil_arr)
    out_ds.GetRasterBand(1).SetNoDataValue(-3000)
    # setting extent of output raster
    # top left x, w-e pixel resolution, rotation, top left y, rotation, n-s pixel resolution
    out_ds.SetGeoTransform(gt)
    # setting spatial reference of output raster
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    out_ds.SetProjection(srs.ExportToWkt())

print('Processing Done')
