# Data Dictionary

## KHOA Weather

Path: `processed/khoa/khoa_mokpo_weather_hourly.csv`

| column | meaning |
| --- | --- |
| `timestamp` | Observation time, hourly |
| `air_temperature_c` | Air temperature in Celsius |
| `air_pressure_hpa` | Air pressure in hPa |
| `wind_direction_16pt` | Korean 16-point wind direction |
| `wind_direction_deg` | Wind direction converted to degrees, north = 0 |
| `wind_speed_mps` | Wind speed in m/s |
| `station_name` | KHOA station name |
| `source_file` | Original monthly CSV filename |

Note: the source KHOA files include `유향/유속` columns, but the provided files currently have empty values there. Those empty columns are removed from the processed file. Use CMEMS `uo/vo` as the primary current input.

## CMEMS Current

Path: `processed/cmems/cmems_surface_current_hourly.csv`

| column | meaning |
| --- | --- |
| `time` | Current field timestamp |
| `depth` | Depth in meters |
| `latitude` | Grid latitude |
| `longitude` | Grid longitude |
| `uo` | Eastward sea water velocity in m/s |
| `vo` | Northward sea water velocity in m/s |
| `current_u_mps` | Modeling input eastward velocity |
| `current_v_mps` | Modeling input northward velocity |
| `current_speed_mps` | Current speed magnitude in m/s |
| `current_direction_deg` | Direction the current flows toward, degrees clockwise from north |

## Leeway

Path: `processed/leeway/leeway_coefficients.csv`

| column | meaning |
| --- | --- |
| `object_key` | Drift object category key |
| `object_type_ko` | Korean object type description |
| `leeway_rate` | Wind speed multiplier |
| `rate_min` | Minimum plausible leeway rate |
| `rate_max` | Maximum plausible leeway rate |
| `sigma` | Random drift noise scale |
| `divergence_deg` | Divergence angle for Monte Carlo spread |
| `jibe_prob_per_hr` | Jibe probability per hour |
| `source` | Source note |

## L3 Synthetic Accidents

Path: `processed/accidents/l3_synthetic_accidents.csv`

| column | meaning |
| --- | --- |
| `case_id` | Synthetic case id |
| `incident_time` | Incident timestamp |
| `incident_lat`, `incident_lon` | Incident location |
| `l1_pred_lat`, `l1_pred_lon` | L1 predicted location |
| `synthetic_found_lat`, `synthetic_found_lon` | Virtual found location |
| `delta_lat`, `delta_lon` | Synthetic correction target |
| `l1_error_km` | Distance error between L1 prediction and synthetic found location |
| `is_synthetic` | Always true for this dataset |

These are not real accident records. Use this file for L3 correction model experiments, model pipeline testing, visualization demos, and API integration tests.
