"""Select the nearest valid satellite AOD observation to each ground station.

The input AOD CSV should be produced by ``extract_swath_aod_points.py``. The
stations CSV must contain ``station_id``, ``latitude``, and ``longitude``.
One observation is retained for every station, sensor, and date. Distances use
the haversine formula instead of Euclidean distance in geographic degrees.

Example::

    python select_nearest_aod_to_stations.py \
      --aod-csv outputs/modis04_aod.csv \
      --stations-csv stations.csv \
      --output-csv outputs/modis04_nearest_station_daily.csv \
      --max-distance-km 25
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(value))


def read_rows(path: Path) -> list[dict[str, str]]:
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
    parser.add_argument("--aod-csv", type=Path, required=True)
    parser.add_argument("--stations-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--max-distance-km", type=float, default=None)
    args = parser.parse_args()

    aod_rows = read_rows(args.aod_csv)
    stations = read_rows(args.stations_csv)
    require_columns(
        aod_rows,
        {"sensor", "year_doy", "time_utc", "latitude", "longitude", "aod"},
        "AOD CSV",
    )
    require_columns(stations, {"station_id", "latitude", "longitude"}, "stations CSV")

    nearest: dict[tuple[str, str, str], dict[str, str]] = {}
    best_distances: dict[tuple[str, str, str], float] = {}
    for station in stations:
        station_lat = float(station["latitude"])
        station_lon = float(station["longitude"])
        for observation in aod_rows:
            distance = haversine_km(
                station_lat, station_lon,
                float(observation["latitude"]), float(observation["longitude"]),
            )
            if args.max_distance_km is not None and distance > args.max_distance_km:
                continue
            key = (station["station_id"], observation["sensor"], observation["year_doy"])
            candidate = {
                **observation,
                "station_id": station["station_id"],
                "station_latitude": station["latitude"],
                "station_longitude": station["longitude"],
                "distance_km": f"{distance:.3f}",
            }
            if key not in best_distances or distance < best_distances[key]:
                nearest[key] = candidate
                best_distances[key] = distance

    if not nearest:
        raise ValueError("No satellite observations matched the station criteria")
    rows = [nearest[key] for key in sorted(nearest)]
    preferred = [
        "station_id", "station_latitude", "station_longitude", "sensor",
        "year_doy", "time_utc", "latitude", "longitude", "distance_km", "aod",
        "quality_flag", "land_flag", "source_file",
    ]
    fieldnames = preferred + [name for name in rows[0] if name not in preferred]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} daily station matches to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
