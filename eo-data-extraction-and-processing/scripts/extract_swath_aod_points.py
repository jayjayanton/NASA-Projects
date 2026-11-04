"""Extract quality-controlled MODIS04 or VIIRS aerosol swaths to one CSV.

The source products store geolocation, aerosol retrievals, quality flags, and
land/ocean flags as separate arrays. This script validates that the arrays have
the same shape, applies the product scale factor, filters observations, and
writes analysis-ready point records.

Examples
--------
MODIS Terra/Aqua Level-2 aerosol files::

    python extract_swath_aod_points.py \
      --sensor modis04 --input-dir data/modis04 \
      --output-csv outputs/modis04_aod.csv \
      --bbox -92 10 -86 16

VIIRS AERDB Level-2 files::

    python extract_swath_aod_points.py \
      --sensor viirs --input-dir data/viirs \
      --output-csv outputs/viirs_aod.csv \
      --bbox -92 10 -86 16

Requires GDAL with HDF4/HDF5 support and NumPy. It does not download data.
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from osgeo import gdal

LOG = logging.getLogger("extract-swath-aod")


@dataclass(frozen=True)
class SensorConfig:
    patterns: tuple[str, ...]
    date_time_regex: re.Pattern[str]
    aod_keyword: str
    latitude_keyword: str
    longitude_keyword: str
    quality_keyword: str
    land_keyword: str
    fallback_scale: float


SENSORS = {
    "modis04": SensorConfig(
        patterns=("*.hdf", "*.HDF"),
        date_time_regex=re.compile(r"\.A(?P<year_doy>\d{7})\.(?P<time>\d{4})"),
        aod_keyword="Optical_Depth_Land_And_Ocean",
        latitude_keyword="Latitude",
        longitude_keyword="Longitude",
        quality_keyword="Land_Ocean_Quality_Flag",
        land_keyword="Land_sea_Flag",
        fallback_scale=0.001,
    ),
    "viirs": SensorConfig(
        patterns=("*.nc", "*.NC"),
        date_time_regex=re.compile(r"\.A(?P<year_doy>\d{7})\.(?P<time>\d{4})"),
        aod_keyword="Aerosol_Optical_Thickness_550_Land_Ocean",
        latitude_keyword="Latitude",
        longitude_keyword="Longitude",
        quality_keyword="Aerosol_Optical_Thickness_QA_Flag_Land",
        land_keyword="Algorithm_Flag_Land",
        fallback_scale=1.0,
    ),
}


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


def read_array(container: gdal.Dataset, keyword: str) -> tuple[np.ndarray, gdal.Band]:
    dataset = gdal.Open(find_subdataset(container, keyword), gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError(f"Could not open subdataset matching {keyword!r}")
    band = dataset.GetRasterBand(1)
    array = band.ReadAsArray()
    if array is None:
        raise RuntimeError(f"Could not read subdataset matching {keyword!r}")
    return np.asarray(array), band


def scaled_aod(raw: np.ndarray, band: gdal.Band, fallback_scale: float) -> np.ndarray:
    scale = band.GetScale()
    offset = band.GetOffset()
    scale = fallback_scale if scale in (None, 1.0) and fallback_scale != 1.0 else (scale or 1.0)
    return raw.astype("float64") * scale + (offset or 0.0)


def collect_inputs(input_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
    return sorted({path for pattern in patterns for path in input_dir.glob(pattern)})


def parse_acquisition(path: Path, pattern: re.Pattern[str]) -> tuple[str, str]:
    match = pattern.search(path.name)
    if not match:
        raise ValueError(
            f"Cannot parse YYYYDDD and HHMM from {path.name}. "
            "Expected a NASA filename containing '.AYYYYDDD.HHMM'."
        )
    return match.group("year_doy"), match.group("time")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensor", choices=sorted(SENSORS), required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument(
        "--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        required=True, help="Bounding box in decimal degrees (EPSG:4326).",
    )
    parser.add_argument("--minimum-quality", type=int, default=3)
    parser.add_argument("--include-ocean", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not args.input_dir.is_dir():
        parser.error(f"Input directory does not exist: {args.input_dir}")
    west, south, east, north = args.bbox
    if not (west < east and south < north):
        parser.error("Invalid bounding box; expected WEST SOUTH EAST NORTH")

    config = SENSORS[args.sensor]
    inputs = collect_inputs(args.input_dir, config.patterns)
    if not inputs:
        parser.error(f"No supported source files found in {args.input_dir}")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sensor", "source_file", "year_doy", "time_utc", "latitude",
        "longitude", "aod", "quality_flag", "land_flag",
    ]
    written = 0
    failed = 0
    with args.output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for path in inputs:
            try:
                year_doy, time_utc = parse_acquisition(path, config.date_time_regex)
                container = gdal.Open(str(path), gdal.GA_ReadOnly)
                if container is None:
                    raise RuntimeError("GDAL could not open the source file")
                raw_aod, aod_band = read_array(container, config.aod_keyword)
                latitude, _ = read_array(container, config.latitude_keyword)
                longitude, _ = read_array(container, config.longitude_keyword)
                quality, _ = read_array(container, config.quality_keyword)
                land, _ = read_array(container, config.land_keyword)
                shapes = {array.shape for array in (raw_aod, latitude, longitude, quality, land)}
                if len(shapes) != 1:
                    raise ValueError(f"Subdataset shapes do not match: {sorted(shapes)}")

                aod = scaled_aod(raw_aod, aod_band, config.fallback_scale)
                nodata = aod_band.GetNoDataValue()
                valid = (
                    np.isfinite(aod) & np.isfinite(latitude) & np.isfinite(longitude)
                    & (longitude >= west) & (longitude <= east)
                    & (latitude >= south) & (latitude <= north)
                    & (quality >= args.minimum_quality) & (aod > 0)
                )
                if nodata is not None:
                    valid &= raw_aod != nodata
                if not args.include_ocean:
                    valid &= land == 1

                indices = np.flatnonzero(valid.ravel())
                flat = [array.ravel() for array in (latitude, longitude, aod, quality, land)]
                for index in indices:
                    writer.writerow({
                        "sensor": args.sensor,
                        "source_file": path.name,
                        "year_doy": year_doy,
                        "time_utc": time_utc,
                        "latitude": f"{float(flat[0][index]):.6f}",
                        "longitude": f"{float(flat[1][index]):.6f}",
                        "aod": f"{float(flat[2][index]):.6f}",
                        "quality_flag": int(flat[3][index]),
                        "land_flag": int(flat[4][index]),
                    })
                written += len(indices)
                LOG.info("%s: wrote %d observations", path.name, len(indices))
            except (RuntimeError, ValueError) as exc:
                failed += 1
                LOG.error("%s: %s", path.name, exc)

    LOG.info("Wrote %d observations to %s; %d files failed", written, args.output_csv, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
