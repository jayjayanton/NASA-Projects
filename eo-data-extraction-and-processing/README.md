# EO Data Extraction and Processing

This folder documents one example of the raster preparation work I carried out during NASA DEVELOP. I worked with Earth-observation datasets and helped automate processing so the outputs could be used in ArcGIS Pro.

## Original script

[`original/NDVI_Tif.py`](original/NDVI_Tif.py) is the original MODIS NDVI extraction example. It searches for local `.hdf` files, opens the `MOD_Grid_monthly_1km_VI` / `1 km monthly NDVI` HDF4-EOS subdataset, reads its raster band, and writes a georeferenced output using the source geotransform and projection. It uses older GDAL Python imports and writes an output without an explicit `.tif` extension.

## Reusable version

[`scripts/extract_hdf_to_geotiff.py`](scripts/extract_hdf_to_geotiff.py) is an updated version with configurable input and output directories, a configurable subdataset search string, GeoTIFF output, compression, logging, and checks for missing or ambiguous subdatasets.

Example:

```bash
python eo-data-extraction-and-processing/scripts/extract_hdf_to_geotiff.py \
  --input-dir data/hdf \
  --output-dir outputs/ndvi \
  --subdataset "1 km monthly NDVI"
```

Requires Python 3 and GDAL (`osgeo.gdal`) with HDF support. Supply your own local source HDF files. The script does **not** download imagery from NASA, derive NDVI from raw spectral bands, reproject rasters, or implement the complete historical workflow.

The updated script has been syntax-checked, but has not been tested end to end against original HDF files.
