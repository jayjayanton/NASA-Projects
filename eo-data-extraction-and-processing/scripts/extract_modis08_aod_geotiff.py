"""Extract the MODIS08 gridded mean AOD subdataset to scaled GeoTIFFs.

Unlike MODIS04 Level-2 swaths, MODIS08 is a Level-3 regular grid. The output
therefore remains a raster rather than becoming a point table.

Example::

    python extract_modis08_aod_geotiff.py \
      --input-dir data/modis08 --output-dir outputs/modis08

Requires GDAL with HDF4 support and NumPy. It does not download data,
reproject the grid, or aggregate it temporally.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

LOG = logging.getLogger("extract-modis08")
DEFAULT_SUBDATASET = "Aerosol_Optical_Depth_Land_Ocean_Mean"


def find_subdataset(container: gdal.Dataset, keyword: str) -> str:
    matches = [name for name, description in container.GetSubDatasets()
               if keyword.lower() in f"{name} {description}".lower()]
    if len(matches) != 1:
        available = "\n".join(f"  {name}: {description}"
                              for name, description in container.GetSubDatasets())
        raise ValueError(
            f"Expected one subdataset matching {keyword!r}; found {len(matches)}.\n"
            f"Available subdatasets:\n{available}"
        )
    return matches[0]


def export_file(source: Path, output: Path, keyword: str, fallback_scale: float, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output}; pass --overwrite to replace it")
    container = gdal.Open(str(source), gdal.GA_ReadOnly)
    if container is None:
        raise RuntimeError("GDAL could not open the source HDF")
    dataset = gdal.Open(find_subdataset(container, keyword), gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError("GDAL could not open the selected AOD subdataset")
    source_band = dataset.GetRasterBand(1)
    scale = source_band.GetScale()
    offset = source_band.GetOffset() or 0.0
    scale = fallback_scale if scale in (None, 1.0) and fallback_scale != 1.0 else (scale or 1.0)
    source_nodata = source_band.GetNoDataValue()

    geotransform = dataset.GetGeoTransform(can_return_null=True)
    if geotransform is None:
        # MODIS08 monthly 1-degree grids are global. Deriving the transform from
        # the raster dimensions avoids the hard-coded 1-degree pixel size in the
        # historical script and remains valid for other global resolutions.
        geotransform = (-180.0, 360.0 / dataset.RasterXSize, 0.0,
                        90.0, 0.0, -180.0 / dataset.RasterYSize)
        LOG.warning("%s has no geotransform; assuming a global regular grid", source.name)
    projection = dataset.GetProjection()
    if not projection:
        spatial_ref = osr.SpatialReference()
        spatial_ref.ImportFromEPSG(4326)
        projection = spatial_ref.ExportToWkt()
        LOG.warning("%s has no projection; assigning EPSG:4326", source.name)

    output.parent.mkdir(parents=True, exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    target = driver.Create(
        str(output), dataset.RasterXSize, dataset.RasterYSize, 1, gdal.GDT_Float32,
        options=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    if target is None:
        raise RuntimeError(f"Could not create {output}")
    target.SetGeoTransform(geotransform)
    target.SetProjection(projection)
    target_band = target.GetRasterBand(1)
    target_band.SetNoDataValue(-9999.0)

    block_rows = 512
    for row in range(0, dataset.RasterYSize, block_rows):
        height = min(block_rows, dataset.RasterYSize - row)
        raw = source_band.ReadAsArray(0, row, dataset.RasterXSize, height)
        values = raw.astype("float32") * scale + offset
        invalid = ~np.isfinite(values)
        if source_nodata is not None:
            invalid |= raw == source_nodata
        values[invalid] = -9999.0
        target_band.WriteArray(values, 0, row)
    target_band.FlushCache()
    target.FlushCache()
    target = None
    dataset = None
    container = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subdataset", default=DEFAULT_SUBDATASET)
    parser.add_argument("--fallback-scale", type=float, default=0.001)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    inputs = sorted(set(args.input_dir.glob("*.hdf")) | set(args.input_dir.glob("*.HDF")))
    if not inputs:
        parser.error(f"No HDF files found in {args.input_dir}")
    failures = 0
    for source in inputs:
        output = args.output_dir / f"{source.stem}_AOD.tif"
        try:
            export_file(source, output, args.subdataset, args.fallback_scale, args.overwrite)
            LOG.info("Wrote %s", output)
        except (RuntimeError, ValueError, FileExistsError) as exc:
            failures += 1
            LOG.error("%s: %s", source.name, exc)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
