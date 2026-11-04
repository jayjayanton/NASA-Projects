"""Extract CALIPSO tropospheric AOD profiles and uncertainty to one CSV.

The script selects subdatasets by descriptive name rather than fixed numeric
positions. For geolocation arrays with several footprint columns, the center
column is used, matching the intent of the historical workflow.

Example::

    python extract_calipso_aod_points.py \
      --input-dir data/calipso \
      --output-csv outputs/calipso_aod.csv \
      --bbox -93.92 6.04 -67.49 20.94
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import numpy as np
from osgeo import gdal

LOG = logging.getLogger("extract-calipso")


KEYWORDS = {
    "profile_id": "Profile_ID",
    "utc": "Profile_UTC_Time",
    "day_night": "Day_Night_Flag",
    "longitude": "Longitude",
    "latitude": "Latitude",
    "aod": "Column_Optical_Depth_Tropospheric_Aerosols_532",
    "uncertainty": "Column_Optical_Depth_Tropospheric_Aerosols_Uncertainty_532",
}


def find_subdataset(container: gdal.Dataset, keyword: str) -> str:
    matches = [name for name, description in container.GetSubDatasets()
               if keyword.lower() in f"{name} {description}".lower()]
    if len(matches) != 1:
        raise ValueError(f"Expected one CALIPSO subdataset matching {keyword!r}; found {len(matches)}")
    return matches[0]


def read_profile(container: gdal.Dataset, keyword: str) -> np.ndarray:
    dataset = gdal.Open(find_subdataset(container, keyword), gdal.GA_ReadOnly)
    if dataset is None:
        raise RuntimeError(f"Could not open CALIPSO subdataset {keyword!r}")
    array = np.asarray(dataset.GetRasterBand(1).ReadAsArray())
    if array.ndim == 1:
        return array
    if array.ndim == 2:
        return array[:, array.shape[1] // 2]
    raise ValueError(f"Unexpected shape for {keyword!r}: {array.shape}")


def decode_profile_utc(value: float) -> tuple[str, str]:
    # CALIPSO Profile_UTC_Time is commonly YYMMDD.fraction_of_day.
    whole = int(value)
    year = 2000 + whole // 10000
    month = (whole % 10000) // 100
    day = whole % 100
    fraction = value - whole
    total_seconds = max(0, min(86399, round(fraction * 86400)))
    hour, remainder = divmod(total_seconds, 3600)
    minute, second = divmod(remainder, 60)
    from datetime import datetime, timezone
    timestamp = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    return timestamp.strftime("%Y%j"), timestamp.strftime("%H%M%S")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument(
        "--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        required=True,
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    west, south, east, north = args.bbox
    inputs = sorted(set(args.input_dir.glob("*.hdf")) | set(args.input_dir.glob("*.HDF")))
    if not inputs:
        parser.error(f"No HDF files found in {args.input_dir}")

    fields = [
        "source_file", "profile_id", "year_doy", "time_utc", "day_night_flag",
        "latitude", "longitude", "tropospheric_aod_532", "aod_uncertainty_532",
    ]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    written = 0
    with args.output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for path in inputs:
            try:
                container = gdal.Open(str(path), gdal.GA_ReadOnly)
                if container is None:
                    raise RuntimeError("GDAL could not open the CALIPSO HDF")
                values = {name: read_profile(container, keyword) for name, keyword in KEYWORDS.items()}
                lengths = {len(array) for array in values.values()}
                if len(lengths) != 1:
                    raise ValueError(f"CALIPSO profile lengths do not match: {sorted(lengths)}")
                count = 0
                for index in range(lengths.pop()):
                    lat = float(values["latitude"][index])
                    lon = float(values["longitude"][index])
                    aod = float(values["aod"][index])
                    uncertainty = float(values["uncertainty"][index])
                    if not (west <= lon <= east and south <= lat <= north):
                        continue
                    if not (np.isfinite(aod) and np.isfinite(uncertainty)):
                        continue
                    if aod <= -999 or uncertainty <= -999:
                        continue
                    year_doy, time_utc = decode_profile_utc(float(values["utc"][index]))
                    writer.writerow({
                        "source_file": path.name,
                        "profile_id": int(values["profile_id"][index]),
                        "year_doy": year_doy,
                        "time_utc": time_utc,
                        "day_night_flag": int(values["day_night"][index]),
                        "latitude": f"{lat:.6f}",
                        "longitude": f"{lon:.6f}",
                        "tropospheric_aod_532": f"{aod:.8f}",
                        "aod_uncertainty_532": f"{uncertainty:.8f}",
                    })
                    count += 1
                written += count
                LOG.info("%s: wrote %d profiles", path.name, count)
            except (RuntimeError, ValueError) as exc:
                failures += 1
                LOG.error("%s: %s", path.name, exc)
    LOG.info("Wrote %d profiles to %s; %d files failed", written, args.output_csv, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
