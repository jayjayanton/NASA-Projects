"""Collocate MODIS04 AOD points with CALIPSO tropospheric AOD profiles.

Inputs should come from ``extract_swath_aod_points.py`` and
``extract_calipso_aod_points.py``. Candidates must occur on the same date and
fall within both the spatial and temporal thresholds. The closest spatial
match is retained for each CALIPSO profile.

Example::

    python collocate_modis_calipso.py \
      --modis-csv outputs/modis04_aod.csv \
      --calipso-csv outputs/calipso_aod.csv \
      --output-csv outputs/modis_calipso_matches.csv \
      --max-distance-km 12 --max-time-hours 3
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(value))


def time_seconds(value: str) -> int:
    digits = value.strip().split(".", maxsplit=1)[0]
    if not digits.isdigit() or len(digits) > 6:
        raise ValueError(f"Invalid UTC time: {value!r}")
    if len(digits) <= 4:
        digits = digits.zfill(4) + "00"
    else:
        digits = digits.zfill(6)
    hours, minutes, seconds = int(digits[:2]), int(digits[2:4]), int(digits[4:])
    if hours > 23 or minutes > 59 or seconds > 59:
        raise ValueError(f"Invalid UTC time: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def require_columns(rows: list[dict[str, str]], required: set[str], label: str) -> None:
    if not rows:
        raise ValueError(f"{label} is empty")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(sorted(missing))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modis-csv", type=Path, required=True)
    parser.add_argument("--calipso-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--max-distance-km", type=float, default=12.0)
    parser.add_argument("--max-time-hours", type=float, default=3.0)
    args = parser.parse_args()

    modis = read_csv(args.modis_csv)
    calipso = read_csv(args.calipso_csv)
    require_columns(modis, {"year_doy", "time_utc", "latitude", "longitude", "aod"}, "MODIS CSV")
    require_columns(
        calipso,
        {"profile_id", "year_doy", "time_utc", "latitude", "longitude",
         "tropospheric_aod_532", "aod_uncertainty_532"},
        "CALIPSO CSV",
    )

    by_date: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in modis:
        by_date[row["year_doy"]].append(row)

    matches: list[dict[str, str]] = []
    for profile in calipso:
        best = None
        best_distance = float("inf")
        profile_time = time_seconds(profile["time_utc"])
        for observation in by_date.get(profile["year_doy"], []):
            time_delta_hours = abs(time_seconds(observation["time_utc"]) - profile_time) / 3600
            if time_delta_hours > args.max_time_hours:
                continue
            distance = haversine_km(
                float(profile["latitude"]), float(profile["longitude"]),
                float(observation["latitude"]), float(observation["longitude"]),
            )
            if distance <= args.max_distance_km and distance < best_distance:
                best = observation
                best_distance = distance
                best_time_delta = time_delta_hours
        if best is not None:
            matches.append({
                "year_doy": profile["year_doy"],
                "calipso_profile_id": profile["profile_id"],
                "calipso_time_utc": profile["time_utc"],
                "calipso_latitude": profile["latitude"],
                "calipso_longitude": profile["longitude"],
                "calipso_tropospheric_aod_532": profile["tropospheric_aod_532"],
                "calipso_aod_uncertainty_532": profile["aod_uncertainty_532"],
                "modis_time_utc": best["time_utc"],
                "modis_latitude": best["latitude"],
                "modis_longitude": best["longitude"],
                "modis_aod": best["aod"],
                "distance_km": f"{best_distance:.3f}",
                "time_difference_hours": f"{best_time_delta:.3f}",
                "modis_source_file": best.get("source_file", ""),
                "calipso_source_file": profile.get("source_file", ""),
            })

    if not matches:
        raise ValueError("No MODIS-CALIPSO pairs met the spatial and temporal thresholds")
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(matches[0]))
        writer.writeheader()
        writer.writerows(matches)
    print(f"Wrote {len(matches)} collocated pairs to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
