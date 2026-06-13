# Local modeling data

The private demo modeling bundle is stored at `data/modeling_inputs/`.

Required runtime files:

```text
data/modeling_inputs/
  raw/cmems/mokpo_surface_current.nc
  processed/khoa/khoa_mokpo_weather_hourly.csv
  processed/leeway/leeway_coefficients.csv
  processed/geo/land_mask.geojson
```

The directory is mounted read-only at `/data/modeling_inputs` in Docker. Large CMEMS files
are managed with Git LFS; run `git lfs pull` after cloning when necessary.
