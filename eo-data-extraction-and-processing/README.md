# Earth Observation Data Extraction and Processing

This folder documents reusable versions of Earth-observation processing methods used across two NASA DEVELOP applications: the Lambayeque Water Resources project and the Central America Health and Air Quality project.

The projects shared a general objective - converting repeated multidimensional NASA products into consistent, analysis-ready data - but the product structures and downstream analyses were substantially different.

## Processing differences

| Water resources | Air quality |
| --- | --- |
| Primarily gridded Level-3 environmental products | A mixture of Level-2 swaths, Level-3 grids, and CALIPSO lidar profiles |
| Variables included NDVI and other hydrologic or vegetation indicators | Variables included MODIS/VIIRS aerosol optical depth (AOD) and CALIPSO tropospheric AOD |
| Preserve raster grids for mapping, clipping, mosaicking, and regional summaries | Convert swath pixels and lidar profiles into quality-controlled point observations |
| Compare spatial patterns and regional time series | Collocate satellite observations with monitoring stations or other sensors |
| Summarize values over protected-area polygons | Match observations by date, overpass time, and distance before regression or sensor comparison |

NDVI and AOD can both originate from passive optical satellite observations, but they represent different physical targets. NDVI characterizes surface vegetation. AOD measures light attenuation by aerosols through the atmospheric column. Ground PM2.5 monitors measure near-surface particle mass at individual locations, so AOD observations must be matched and calibrated against those measurements rather than treated as direct PM2.5 readings.

## Water-resources raster workflow

[`original/NDVI_Tif.py`](original/NDVI_Tif.py) is the original MODIS NDVI extraction example. It searches for local HDF files, opens the `MOD_Grid_monthly_1km_VI` / `1 km monthly NDVI` subdataset, and writes the selected grid as a georeferenced raster.

[`scripts/extract_hdf_to_geotiff.py`](scripts/extract_hdf_to_geotiff.py) is the reusable version. It adds configurable directories and subdataset selection, explicit GeoTIFF output, compression, logging, and checks for missing or ambiguous subdatasets.

```bash
python eo-data-extraction-and-processing/scripts/extract_hdf_to_geotiff.py \
  --input-dir data/hdf \
  --output-dir outputs/ndvi \
  --subdataset "1 km monthly NDVI"
```

The script preserves the selected raster's native grid. It does not download imagery, calculate NDVI from raw spectral bands, mosaic tiles, reproject the data, or apply product-specific scale factors.

## Air-quality workflow

### 1. Extract MODIS04 or VIIRS swaths

[`scripts/extract_swath_aod_points.py`](scripts/extract_swath_aod_points.py) reads the AOD/AOT, latitude, longitude, quality, and land/ocean arrays from each Level-2 source file. It applies the product scale factor, clips observations to a bounding box, retains quality-controlled positive retrievals, and writes one consolidated point CSV.

```bash
python eo-data-extraction-and-processing/scripts/extract_swath_aod_points.py \
  --sensor modis04 \
  --input-dir data/modis04 \
  --output-csv outputs/modis04_aod.csv \
  --bbox -92 10 -86 16
```

Change `--sensor modis04` to `--sensor viirs` for AERDB VIIRS files.

### 2. Match satellite observations to monitoring stations

[`scripts/select_nearest_aod_to_stations.py`](scripts/select_nearest_aod_to_stations.py) uses haversine distance to retain the closest observation to every station for each sensor and date.

```bash
python eo-data-extraction-and-processing/scripts/select_nearest_aod_to_stations.py \
  --aod-csv outputs/modis04_aod.csv \
  --stations-csv stations.csv \
  --output-csv outputs/modis04_nearest_station_daily.csv \
  --max-distance-km 25
```

The stations file must contain:

```csv
station_id,latitude,longitude
CGOB,13.7063417,-89.2000806
```

This output can be aggregated to the temporal resolution of the available ground PM2.5 measurements before regression. The script deliberately stops before regression so the aggregation rules remain explicit.

### 3. Export gridded MODIS08 AOD

[`scripts/extract_modis08_aod_geotiff.py`](scripts/extract_modis08_aod_geotiff.py) preserves MODIS08 as a regular raster, applies its scale factor, and writes compressed floating-point GeoTIFFs. This workflow is structurally closer to NDVI processing than the MODIS04 swath workflow.

### 4. Extract and compare CALIPSO observations

[`scripts/extract_calipso_aod_points.py`](scripts/extract_calipso_aod_points.py) extracts CALIPSO profile location, UTC time, day/night flag, tropospheric AOD, and uncertainty. [`scripts/collocate_modis_calipso.py`](scripts/collocate_modis_calipso.py) then matches MODIS and CALIPSO observations using explicit distance and time thresholds.

## Environment

The recommended installation uses conda-forge because GDAL must include the HDF4 and HDF5 drivers required by these products.

```bash
conda create -n nasa-eo -c conda-forge python=3.11 gdal numpy
conda activate nasa-eo
python -c "from osgeo import gdal; print(gdal.VersionInfo())"
```

Confirm that the required drivers are present:

```bash
python -c "from osgeo import gdal; print([gdal.GetDriver(i).ShortName for i in range(gdal.GetDriverCount()) if 'HDF' in gdal.GetDriver(i).ShortName])"
```

## Reproducibility notes

- Source satellite files are not included. Obtain the appropriate NASA products and preserve their original filenames because acquisition dates and times are parsed from those names.
- Product collections can change subdataset descriptions, metadata, scale factors, and quality-flag definitions. Verify them against the product user guide for the collection being processed.
- The scripts fail on missing or ambiguous subdatasets rather than silently selecting the wrong variable.
- MODIS04 and VIIRS outputs retain the source filename, observation time, quality flag, and land flag for traceability.
- Station matching uses great-circle distance in kilometers. The historical prototype used Euclidean distance in geographic degrees and processed one station at a time.
- CALIPSO collocation applies both spatial and temporal limits. The historical prototype contained undocumented intermediate column assumptions that prevented direct reproduction from its extraction output.
- Syntax and synthetic CSV tests can verify the software structure, but an end-to-end run still requires representative source files from each NASA product.

## Historical attribution

The 2019 MODIS04, VIIRS, and CALIPSO extraction prototypes credited Kenton Ross and were used or adapted within the Central America Health and Air Quality team. The scripts in this folder are cleaned, reproducible adaptations that preserve the documented processing intent while correcting schema assumptions, station-distance calculations, and file-handling issues. They should not be interpreted as byte-for-byte copies of the historical code.
