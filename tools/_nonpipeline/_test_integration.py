"""Integration test: full generate_ensemble with mock centroids."""
import os, sys, warnings
warnings.filterwarnings("ignore")

ENV_PATH = r"C:\Users\Jack\miniforge3\envs\climada_env"
_new_path = [p for p in os.environ["PATH"].split(os.pathsep) if "anaconda3" not in p.lower()]
os.environ["PATH"] = (
    rf"{ENV_PATH}\Library\bin;"
    rf"{ENV_PATH}\Library\usr\bin;"
    rf"{ENV_PATH}\Library\mingw-w64\bin;"
    rf"{ENV_PATH};"
    rf"{ENV_PATH}\Scripts;"
    + os.pathsep.join(_new_path)
)
if sys.platform == "win32":
    os.add_dll_directory(rf"{ENV_PATH}\Library\bin")
os.environ["GDAL_DATA"] = rf"{ENV_PATH}\Library\share\gdal"
os.environ["PROJ_LIB"] = rf"{ENV_PATH}\Library\share\proj"

import numpy as np
import xarray as xr
import pandas as pd
from climada.hazard import Centroids

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tc_did_synth import TCDIDSynthesizer, DIDEnsemble

print("=" * 60)
print("Integration Test: generate_ensemble")
print("=" * 60)

# 1. Create mock base track near Shanghai
times = pd.date_range("2019-08-08", periods=24, freq="1h")
n_nodes = len(times)
sh_lon, sh_lat = 121.47, 31.23

lons = np.linspace(123, 120, n_nodes)
lats = np.linspace(29, 33, n_nodes)
vmax = np.full(n_nodes, 55.0)  # kt (~28 m/s)
p_cen = np.full(n_nodes, 965.0)
p_env = np.full(n_nodes, 1010.0)
rmw = np.full(n_nodes, 30.0)
roci = np.full(n_nodes, 200.0)

track = xr.Dataset(
    data_vars={
        "time_step": ("time", np.full(n_nodes, 1.0)),
        "lat": ("time", lats),
        "lon": ("time", lons),
        "max_sustained_wind": ("time", vmax),
        "central_pressure": ("time", p_cen),
        "environmental_pressure": ("time", p_env),
        "radius_max_wind": ("time", rmw),
        "radius_oci": ("time", roci),
    },
    coords={"time": times},
    attrs={
        "name": "INTEG_TEST",
        "sid": "test001",
        "orig_event_flag": True,
        "max_sustained_wind_unit": "kn",
        "central_pressure_unit": "mb",
        "radius_max_wind_unit": "nm",
        "radius_oci_unit": "nm",
    },
)

# 2. Create mock centroids around Shanghai
grid_lon = np.linspace(120.8, 122.0, 20)
grid_lat = np.linspace(30.7, 31.7, 20)
lon_grid, lat_grid = np.meshgrid(grid_lon, grid_lat)
centroids = Centroids.from_lat_lon(
    lat_grid.ravel(), lon_grid.ravel()
)
print(f"\nCentroids: {centroids.size} points around Shanghai")

# 3. Create mock district mapping (4 quadrants)
n = centroids.size
district_mapping = {
    "NE": (centroids.lon >= 121.47) & (centroids.lat >= 31.23),
    "NW": (centroids.lon < 121.47) & (centroids.lat >= 31.23),
    "SE": (centroids.lon >= 121.47) & (centroids.lat < 31.23),
    "SW": (centroids.lon < 121.47) & (centroids.lat < 31.23),
}
for d, m in district_mapping.items():
    print(f"  {d}: {m.sum()} centroids")

# 4. Generate small ensemble
synth = TCDIDSynthesizer(
    base_track=track,
    spatial_spread_deg=2.0,
    rotation_range_deg=30.0,
    intensity_spread=0.15,
    size_spread=0.25,
)

print(f"\nGenerating 20 realizations...")
ensemble = synth.generate_ensemble(
    n_realizations=20,
    centroids=centroids,
    district_mapping=district_mapping,
    seed=123,
    shanghai_center=(121.47, 31.23),
    max_dist_eye_km=300.0,
    max_attempts_per_track=20,
)

print(f"\nResults:")
print(f"  Realizations: {ensemble.n_realizations}")
print(f"  Acceptance rate: {ensemble.metadata['acceptance_rate']:.1%}")
print(f"  Districts: {ensemble.n_districts}")

# 5. Verify output
assert ensemble.n_realizations > 0, "No realizations generated!"
assert ensemble.district_winds_max.shape == (ensemble.n_realizations, ensemble.n_districts)
assert len(ensemble.synth_tracks) == ensemble.n_realizations

# 6. Quantile classification
groups = ensemble.classify_by_quantile(n_groups=3)
print(f"  Group distribution:", {g: (groups == g).sum() for g in range(3)})

# 7. Panel export
df = ensemble.to_panel_dataframe()
print(f"  Panel: {len(df)} rows, columns={list(df.columns)}")
print(f"  Sample:\n{df.head(8).to_string(index=False)}")

# 8. Balance
print(f"\nBalance report:")
print(ensemble.balance_report().to_string(index=False))

print("\n" + "=" * 60)
print("INTEGRATION TEST PASSED")
print("=" * 60)
