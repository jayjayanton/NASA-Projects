"""Extract a named raster subdataset from local HDF files into GeoTIFFs.

Example:
    python eo-data-extraction-and-processing/scripts/extract_hdf_to_geotiff.py \
      --input-dir data/hdf --output-dir outputs/ndvi \
      --subdataset '1 km monthly NDVI'

Requires GDAL with support for the source HDF product. This script does not
acquire satellite files, resample, reproject, or calculate NDVI from bands.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from osgeo import gdal

LOG = logging.getLogger("eo-extraction")


def extract_file(source: Path, output_dir: Path, subdataset_keyword: str, overwrite: bool = False) -> Path:
    container = gdal.Open(str(source), gdal.GA_ReadOnly)
    if container is None:
        raise RuntimeError(f"Cannot open {source}; check the HDF driver in your GDAL build")
    candidates = [(name, desc) for name, desc in container.GetSubDatasets()
                  if subdataset_keyword.lower() in (name + " " + desc).lower()]
    if len(candidates) != 1:
        details = "\n".join(f"  {name}: {desc}" for name, desc in container.GetSubDatasets())
        raise ValueError(f"Expected one match for {subdataset_keyword!r} in {source.name}; "
                         f"found {len(candidates)}. Available subdatasets:\n{details}")
    name, _ = candidates[0]
    dataset = gdal.Open(name, gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError(f"Could not open matched subdataset: {name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{source.stem}_NDVI.tif"
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output}. Pass --overwrite to replace it")
    result = gdal.Translate(str(output), dataset, format="GTiff", creationOptions=["COMPRESS=LZW", "TILED=YES"])
    if result is None:
        raise RuntimeError(f"GDAL translation failed for {source}")
    result = None
    dataset = None
    container = None
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subdataset", default="1 km monthly NDVI", help="Unique substring in HDF subdataset name/description")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not args.input_dir.is_dir():
        parser.error(f"Input directory does not exist: {args.input_dir}")
    inputs = sorted(args.input_dir.glob("*.hdf"))
    if not inputs:
        parser.error(f"No .hdf files in {args.input_dir}")
    errors = 0
    for path in inputs:
        try:
            LOG.info("Wrote %s", extract_file(path, args.output_dir, args.subdataset, args.overwrite))
        except (RuntimeError, ValueError, FileExistsError) as exc:
            LOG.error("%s", exc)
            errors += 1
    LOG.info("Processed %d files; %d errors", len(inputs), errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
