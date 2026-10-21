# === tc_did_synth.py ===
# DID-oriented synthetic typhoon ensemble generator.
# Extends CLIMADA's track perturbation with intensity and size randomization
# to enable treatment/control group assignment for DID analysis.
#
# Architecture: 4-layer randomization on a historical base track
#   L1: Track geometry (global translation + rotation + per-segment perturbation)
#   L2: Intensity (wind speed with autocorrelated noise, pressure linked via Holland physics)
#   L3: Size (RMW with autocorrelated noise, ROCI linked)
#   L4: Post-hoc quantile-based exposure group assignment
#
# Physical constraints at each step ensure Holland wind field consistency.

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from climada.hazard import Centroids
from climada.hazard.tc_tracks_synth import (
    _get_bearing_angle,
    _get_destination_points,
    _random_uniform_ac,
)
from climada.hazard.trop_cyclone.trop_cyclone_windfields import (
    compute_windfields_sparse,
    get_close_centroids,
    tctrack_to_si,
)
from climada.util import coordinates as u_coord

LOGGER = logging.getLogger(__name__)

# ── Physical bounds ────────────────────────────────────────────────────
V_MAX_BOUND = 85.0        # m/s, maximum observed TC wind speed
V_MIN_BOUND = 17.5        # m/s, tropical depression threshold
P_MIN_BOUND = 870.0       # hPa, lowest observed central pressure
RMW_MIN_KM = 10.0         # km
RMW_MAX_KM = 150.0        # km
NM_TO_KM = 1.852
KT_TO_MS = 0.514444       # knots to m/s


# ═══════════════════════════════════════════════════════════════════════════
# DIDEnsemble — result container
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DIDEnsemble:
    """Container for DID typhoon ensemble results.

    Attributes
    ----------
    realization_ids : list of int
    district_winds_max : np.ndarray, shape (n_realizations, n_districts)
        Maximum wind speed (m/s) in each district per realization.
    district_winds_avg : np.ndarray, shape (n_realizations, n_districts)
        Mean wind speed (m/s) in each district per realization.
    synth_tracks : list of xr.Dataset
        Synthetic typhoon tracks (full xarray Datasets).
    district_names : list of str
    metadata : dict
        Generation parameters, seed, acceptance rate, etc.
    """

    realization_ids: List[int]
    district_winds_max: np.ndarray
    district_winds_avg: np.ndarray
    synth_tracks: List[xr.Dataset]
    district_names: List[str]
    metadata: dict = field(default_factory=dict)

    @property
    def n_realizations(self) -> int:
        return len(self.realization_ids)

    @property
    def n_districts(self) -> int:
        return len(self.district_names)

    def classify_by_quantile(
        self, n_groups: int = 3, use_wind: str = "max"
    ) -> np.ndarray:
        """Within each realization, classify districts into exposure groups by
        wind speed quantile.

        Parameters
        ----------
        n_groups : int
            Number of groups (default 3: low, medium, high).
        use_wind : str
            "max" or "avg" — which wind field to use for classification.

        Returns
        -------
        np.ndarray, shape (n_realizations, n_districts), dtype int
            0 = lowest exposure, n_groups-1 = highest exposure.
        """
        winds = (
            self.district_winds_max if use_wind == "max" else self.district_winds_avg
        )
        groups = np.zeros_like(winds, dtype=int)
        for i in range(self.n_realizations):
            w = winds[i, :]
            if w.max() <= V_MIN_BOUND:
                continue  # all zeros — no meaningful classification
            # Equal-frequency bin edges
            edges = np.percentile(w, np.linspace(0, 100, n_groups + 1))
            # Assign: edges[g] <= w < edges[g+1], with last group closed on right
            for g in range(n_groups):
                if g < n_groups - 1:
                    mask = (w >= edges[g]) & (w < edges[g + 1])
                else:
                    mask = (w >= edges[g]) & (w <= edges[g + 1])
                groups[i, mask] = g
        return groups

    def to_panel_dataframe(self, n_groups: int = 3) -> pd.DataFrame:
        """Convert to long-format panel DataFrame compatible with DID pipeline.

        Returns a DataFrame with columns:
        realization_id, district, max_wind, avg_wind, exposure_group
        """
        groups = self.classify_by_quantile(n_groups=n_groups)
        records = []
        for i in range(self.n_realizations):
            for j, dname in enumerate(self.district_names):
                records.append(
                    {
                        "realization_id": self.realization_ids[i],
                        "district": dname,
                        "max_wind": self.district_winds_max[i, j],
                        "avg_wind": self.district_winds_avg[i, j],
                        "exposure_group": groups[i, j],
                    }
                )
        return pd.DataFrame(records)

    def balance_report(self, n_groups: int = 3) -> pd.DataFrame:
        """How often each district falls into the high-exposure group."""
        groups = self.classify_by_quantile(n_groups=n_groups)
        high_mask = groups == (n_groups - 1)
        return pd.DataFrame(
            {
                "district": self.district_names,
                "high_exposure_freq": high_mask.mean(axis=0),
                "high_exposure_count": high_mask.sum(axis=0),
                "total_realizations": self.n_realizations,
            }
        )


# ═══════════════════════════════════════════════════════════════════════════
# TCDIDSynthesizer — core engine
# ═══════════════════════════════════════════════════════════════════════════

class TCDIDSynthesizer:
    """Generate physically plausible typhoon ensembles for DID analysis.

    Takes a historical typhoon track as baseline and applies 3-layer
    randomization (geometry, intensity, size) to produce an ensemble
    where treatment/control variation across districts arises naturally
    from track position and wind field physics.

    Parameters
    ----------
    base_track : xr.Dataset
        A single historical typhoon track (from TCTracks).
    spatial_spread_deg : float
        Max global translation in degrees (±). Default 2.0 (~220 km).
    rotation_range_deg : float
        Max track rotation angle in degrees (±). Default 30.0.
    intensity_spread : float
        Relative wind speed perturbation. Default 0.20 (±20%).
    size_spread : float
        Relative RMW perturbation. Default 0.30 (±30%).
    autocorr_intensity : float
        Hourly autocorrelation for intensity noise. Default 0.85.
    autocorr_size : float
        Hourly autocorrelation for size noise. Default 0.85.
    """

    def __init__(
        self,
        base_track: xr.Dataset,
        spatial_spread_deg: float = 2.0,
        rotation_range_deg: float = 30.0,
        intensity_spread: float = 0.20,
        size_spread: float = 0.30,
        autocorr_intensity: float = 0.85,
        autocorr_size: float = 0.85,
    ):
        self.base_track = base_track
        self.spatial_spread_deg = spatial_spread_deg
        self.rotation_range_deg = rotation_range_deg
        self.intensity_spread = intensity_spread
        self.size_spread = size_spread
        self.autocorr_intensity = autocorr_intensity
        self.autocorr_size = autocorr_size

        # Cache base track properties
        self.n_nodes = base_track["time"].size
        self.n_seg = max(self.n_nodes - 1, 0)
        time_steps = np.unique(base_track["time_step"])
        self.time_step_h = float(time_steps[0]) if len(time_steps) > 0 else 1.0

    # ── Public API ──────────────────────────────────────────────────────

    def generate_ensemble(
        self,
        n_realizations: int,
        centroids: Centroids,
        district_mapping: Dict[str, np.ndarray],
        seed: int = None,
        shanghai_center: Tuple[float, float] = (121.47, 31.23),
        max_dist_eye_km: float = 300.0,
        max_attempts_per_track: int = 10,
    ) -> DIDEnsemble:
        """Generate an ensemble of synthetic typhoon scenarios.

        Parameters
        ----------
        n_realizations : int
            Target number of valid ensemble members.
        centroids : Centroids
            CLIMADA Centroids covering the study area.
        district_mapping : dict
            district_name -> boolean index array (into centroids).
        seed : int, optional
            Random seed for reproducibility.
        shanghai_center : tuple
            (lon, lat) of Shanghai center for relevance filter.
        max_dist_eye_km : float
            Max distance (km) from centroids to track for wind computation.
        max_attempts_per_track : int
            Max attempts per accepted realization (accept/reject sampling).

        Returns
        -------
        DIDEnsemble
        """
        rng = np.random.default_rng(seed)
        district_names = list(district_mapping.keys())
        n_districts = len(district_names)

        ids_list: List[int] = []
        max_winds_list: List[np.ndarray] = []
        avg_winds_list: List[np.ndarray] = []
        tracks_list: List[xr.Dataset] = []

        n_generated = 0
        total_attempts = 0

        while n_generated < n_realizations:
            total_attempts += 1

            # Guard against infinite loop
            if total_attempts > n_realizations * max_attempts_per_track:
                LOGGER.warning(
                    "Reached max total attempts (%d). Generated %d/%d.",
                    total_attempts, n_generated, n_realizations,
                )
                break

            # Generate candidate
            synth = self._generate_one(rng)

            # Physical plausibility check
            if not self._verify_physical_plausibility(synth):
                LOGGER.debug("Attempt %d: physical plausibility failed.", total_attempts)
                continue

            # Relevance to Shanghai check
            if not self._is_near_shanghai(synth, shanghai_center):
                LOGGER.debug("Attempt %d: not near Shanghai.", total_attempts)
                continue

            # Compute district-level winds
            try:
                max_w, avg_w = self._compute_district_winds(
                    synth, centroids, district_mapping, district_names,
                    max_dist_eye_km=max_dist_eye_km,
                )
            except Exception as exc:
                LOGGER.debug("Attempt %d: wind computation failed (%s).",
                             total_attempts, exc)
                continue

            # Must have meaningful wind in at least one district
            if max_w.max() < V_MIN_BOUND:
                LOGGER.debug("Attempt %d: no district above threshold.", total_attempts)
                continue

            ids_list.append(n_generated)
            max_winds_list.append(max_w)
            avg_winds_list.append(avg_w)
            tracks_list.append(synth)
            n_generated += 1

            if n_generated % 100 == 0:
                LOGGER.info("Generated %d/%d realizations.", n_generated, n_realizations)

        acceptance = n_generated / total_attempts if total_attempts > 0 else 0.0
        LOGGER.info(
            "Ensemble complete: %d realizations from %d attempts (%.1f%% accepted).",
            n_generated, total_attempts, acceptance * 100,
        )

        return DIDEnsemble(
            realization_ids=ids_list,
            district_winds_max=np.array(max_winds_list),
            district_winds_avg=np.array(avg_winds_list),
            synth_tracks=tracks_list,
            district_names=district_names,
            metadata={
                "n_attempted": total_attempts,
                "n_generated": n_generated,
                "acceptance_rate": acceptance,
                "seed": seed,
                "spatial_spread_deg": self.spatial_spread_deg,
                "rotation_range_deg": self.rotation_range_deg,
                "intensity_spread": self.intensity_spread,
                "size_spread": self.size_spread,
                "base_track_name": self.base_track.attrs.get("name", "unknown"),
            },
        )

    # ── Single realization generator ────────────────────────────────────

    def _generate_one(self, rng: np.random.Generator) -> xr.Dataset:
        """Generate one synthetic track through L1→L2→L3 randomization."""
        track = self.base_track.copy(deep=True)
        track = self._randomize_track_geometry(track, rng)
        track = self._randomize_intensity(track, rng)
        track = self._randomize_size(track, rng)
        track.attrs["orig_event_flag"] = False
        track.attrs["name"] = track.attrs.get("name", "synth") + "_did"
        return track

    # ── L1: Track geometry ──────────────────────────────────────────────

    def _randomize_track_geometry(
        self, track: xr.Dataset, rng: np.random.Generator
    ) -> xr.Dataset:
        """Global translation + rotation + per-segment perturbation."""
        n_nodes = self.n_nodes
        n_seg = max(n_nodes - 1, 0)

        # (a) Global translation
        dx = rng.uniform(-self.spatial_spread_deg, self.spatial_spread_deg)
        dy = rng.uniform(-self.spatial_spread_deg, self.spatial_spread_deg)

        # (b) Global rotation around track centroid
        center_lon = track["lon"].values.mean()
        center_lat = track["lat"].values.mean()
        rot_deg = rng.uniform(-self.rotation_range_deg, self.rotation_range_deg)
        rot_rad = np.radians(rot_deg)
        cos_a, sin_a = np.cos(rot_rad), np.sin(rot_rad)

        # Apply translation + rotation
        lons_rel = track["lon"].values - center_lon
        lats_rel = track["lat"].values - center_lat
        new_lons = cos_a * lons_rel - sin_a * lats_rel + center_lon + dx
        new_lats = sin_a * lons_rel + cos_a * lats_rel + center_lat + dy

        if n_seg == 0:
            track["lon"].values = new_lons
            track["lat"].values = new_lats
            return track

        # (c) Per-segment direction perturbation (autocorrelated, ±1°/hour)
        ang_pert = _random_uniform_ac(
            n_seg + 10, autocorr=0.5, time_step_h=self.time_step_h
        )[:n_seg + 1]
        ang_pert = np.degrees(np.pi / 180) * (2 * ang_pert - 1)  # ±1° per hour
        ang_pert_cum = np.cumsum(ang_pert * self.time_step_h)

        # (d) Per-segment speed perturbation (autocorrelated, ±50%)
        spd_pert = _random_uniform_ac(
            n_seg + 10, autocorr=0.85, time_step_h=self.time_step_h
        )[:n_seg + 1]
        spd_pert = 1 + 0.5 * (2 * spd_pert - 1)  # scale factor [0.5, 1.5]

        # Recompute track point-by-point
        bearings = _get_bearing_angle(new_lons, new_lats)
        angular_dist = u_coord.dist_approx(
            new_lats[:-1, None],
            new_lons[:-1, None],
            new_lats[1:, None],
            new_lons[1:, None],
            method="geosphere",
            units="degree",
        )[:, 0, 0]

        final_lons = np.zeros(n_nodes)
        final_lats = np.zeros(n_nodes)
        final_lons[0] = new_lons[0]
        final_lats[0] = new_lats[0]

        for i in range(n_seg):
            final_lons[i + 1], final_lats[i + 1] = _get_destination_points(
                final_lons[i],
                final_lats[i],
                bearings[i] + ang_pert_cum[min(i, len(ang_pert_cum) - 1)],
                spd_pert[min(i, len(spd_pert) - 1)] * angular_dist[i],
            )

        u_coord.lon_normalize(final_lons, center=0.0)

        track["lon"].values = final_lons
        track["lat"].values = final_lats
        return track

    # ── L2: Intensity (wind speed + pressure) ───────────────────────────

    def _randomize_intensity(
        self, track: xr.Dataset, rng: np.random.Generator
    ) -> xr.Dataset:
        """Perturb max_sustained_wind with autocorrelated noise, adjust
        central_pressure via Holland wind-pressure relationship."""
        n_nodes = self.n_nodes

        # Autocorrelated relative perturbation
        eps = _random_uniform_ac(
            n_nodes + 10, autocorr=self.autocorr_intensity, time_step_h=self.time_step_h
        )[:n_nodes]
        scale = 1.0 + self.intensity_spread * (2.0 * eps - 1.0)  # [1-δ, 1+δ]

        v_orig = track["max_sustained_wind"].values.copy()

        # Convert kt → m/s for physical perturbation
        v_orig_ms = v_orig * KT_TO_MS
        v_new_ms = v_orig_ms * scale
        v_new_ms = np.clip(v_new_ms, 0.0, V_MAX_BOUND)

        # Convert back to original unit (kt)
        v_new = v_new_ms / KT_TO_MS

        # Adjust central pressure:
        #   Δp = p_env - p_cen  ∝  v²  (Holland 1980 gradient wind)
        #   Δp_new / Δp_old = (v_new / v_orig)²
        p_env = track["environmental_pressure"].values.copy()
        p_cen_old = track["central_pressure"].values.copy()
        p_delta_old = np.maximum(p_env - p_cen_old, 0.1)

        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(v_orig_ms > 1.0, (v_new_ms / v_orig_ms) ** 2, 1.0)
        p_delta_new = p_delta_old * ratio
        p_cen_new = p_env - p_delta_new

        # Clip: not below P_MIN_BOUND, not above p_env (physically impossible)
        p_cen_new = np.clip(p_cen_new, P_MIN_BOUND, p_env - 0.1)

        # Weakened storms (v < V_MIN_BOUND everywhere) degrade to tropical depression
        # — keep pressure consistent with residual wind

        track["max_sustained_wind"].values = v_new
        track["central_pressure"].values = p_cen_new
        return track

    # ── L3: Size (RMW + ROCI) ───────────────────────────────────────────

    def _randomize_size(
        self, track: xr.Dataset, rng: np.random.Generator
    ) -> xr.Dataset:
        """Perturb radius_max_wind and radius_oci with autocorrelated noise."""
        n_nodes = self.n_nodes

        delta = _random_uniform_ac(
            n_nodes + 10, autocorr=self.autocorr_size, time_step_h=self.time_step_h
        )[:n_nodes]
        scale_rmw = 1.0 + self.size_spread * (2.0 * delta - 1.0)  # [1-δ, 1+δ]

        if "radius_max_wind" in track:
            rmw = track["radius_max_wind"].values.copy()
            rmw_new = rmw * scale_rmw
            # Clip to physical bounds (in original units: nautical miles)
            rmw_new = np.clip(rmw_new, RMW_MIN_KM / NM_TO_KM, RMW_MAX_KM / NM_TO_KM)
            track["radius_max_wind"].values = rmw_new

        if "radius_oci" in track:
            roci = track["radius_oci"].values.copy()
            roci_new = roci * scale_rmw  # same scaling factor for outer radius
            track["radius_oci"].values = roci_new

        return track

    # ── Wind field computation ──────────────────────────────────────────

    def _compute_district_winds(
        self,
        track: xr.Dataset,
        centroids: Centroids,
        district_mapping: Dict[str, np.ndarray],
        district_names: List[str],
        max_dist_eye_km: float = 300.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute max and mean wind speed per district.

        Uses CLIMADA's compute_windfields_sparse (Holland 2010 model).
        Pre-filters centroids with get_close_centroids for efficiency.
        """
        # Pre-filter: find centroids within range using SI track.
        # get_close_centroids returns (coords_array, boolean_mask, alongtrack_mask).
        si_track = tctrack_to_si(track.copy(deep=True), metric="equirect")
        _, close_mask, _ = get_close_centroids(
            si_track, centroids.coord, buffer_km=max_dist_eye_km, metric="equirect"
        )
        close_idx = np.where(close_mask)[0]

        if len(close_idx) == 0:
            raise ValueError("No centroids within range of typhoon track.")

        # compute_windfields_sparse takes ORIGINAL track (it calls
        # tctrack_to_si internally) and idx_centr_filter for pre-filtering
        intensity_sparse, _ = compute_windfields_sparse(
            track,
            centroids,
            close_idx,
            model="H10",
            max_dist_eye_km=max_dist_eye_km,
            metric="equirect",
        )

        # intensity_sparse has shape (1, centroids.size) — toarray gives full array
        wind_full = np.zeros(len(centroids.lat), dtype=np.float64)
        if intensity_sparse.nnz > 0:
            wind_full = intensity_sparse.toarray()[0]

        # Aggregate to districts
        n_districts = len(district_names)
        max_winds = np.zeros(n_districts, dtype=np.float64)
        avg_winds = np.zeros(n_districts, dtype=np.float64)

        for j, dname in enumerate(district_names):
            mask = district_mapping[dname]
            d_winds = wind_full[mask]
            if len(d_winds) > 0:
                max_winds[j] = np.max(d_winds)
                avg_winds[j] = np.mean(d_winds)

        return max_winds, avg_winds

    # ── Validation helpers ──────────────────────────────────────────────

    def _verify_physical_plausibility(self, track: xr.Dataset) -> bool:
        """Fast sanity checks on physical parameters."""
        v = track["max_sustained_wind"].values * KT_TO_MS  # kt → m/s
        p_cen = track["central_pressure"].values
        p_env = track["environmental_pressure"].values

        # Wind must be non-negative and not exceed extreme bound
        if np.any(v < 0) or np.any(v > V_MAX_BOUND * 1.05):
            return False

        # Central pressure lower bound
        if np.any(p_cen < P_MIN_BOUND):
            return False

        # p_cen must be strictly less than p_env
        if np.any(p_cen >= p_env):
            return False

        # RMW bounds (if present)
        if "radius_max_wind" in track:
            rmw = track["radius_max_wind"].values
            rmw_km = rmw * NM_TO_KM
            if np.any(rmw_km < RMW_MIN_KM * 0.5) or np.any(rmw_km > RMW_MAX_KM * 1.5):
                return False

        return True

    @staticmethod
    def _is_near_shanghai(
        track: xr.Dataset,
        shanghai_center: Tuple[float, float],
        margin_deg: float = 5.0,
    ) -> bool:
        """Check if the track passes anywhere near Shanghai.

        Uses a fast bounding-box check before distance computation.
        """
        lons = track["lon"].values
        lats = track["lat"].values
        sh_lon, sh_lat = shanghai_center

        # Bounding box check
        if sh_lon + margin_deg < lons.min() or sh_lon - margin_deg > lons.max():
            return False
        if sh_lat + margin_deg < lats.min() or sh_lat - margin_deg > lats.max():
            return False

        # Approximate minimum distance (equirectangular, sufficient for filter)
        dlon = (lons - sh_lon) * np.cos(np.radians(sh_lat))
        dlat = lats - sh_lat
        dist_deg = np.sqrt(dlon**2 + dlat**2).min()
        return dist_deg < margin_deg


# ═══════════════════════════════════════════════════════════════════════════
# Utility: build district mapping from building skeleton
# ═══════════════════════════════════════════════════════════════════════════

def build_district_mapping_from_skeleton(
    building_parquet_path: str,
    centroids: Centroids,
    district_col: str = "district",
    lon_col: str = "centroid_lon",
    lat_col: str = "centroid_lat",
    tolerance_km: float = 0.5,
) -> Dict[str, np.ndarray]:
    """Map each centroid to a district using the building skeleton.

    The building skeleton contains unique (centroid_lon, centroid_lat) pairs
    already assigned to districts.  This function matches CLIMADA centroids
    to those coordinates and returns a ``district_name → boolean index array``
    mapping.

    Parameters
    ----------
    building_parquet_path : str
        Path to building_skeleton.parquet.
    centroids : Centroids
        CLIMADA Centroids covering the study area.
    district_col, lon_col, lat_col : str
        Column names in the parquet file.
    tolerance_km : float
        Max distance (km) to consider a centroid "matched" to a building.

    Returns
    -------
    dict : district_name → np.ndarray (boolean, length = n_centroids)
    """
    import os
    import tempfile
    import shutil

    # Handle non-ASCII paths by copying to temp (netCDF4/Windows issue)
    parquet_path = str(building_parquet_path)
    if not parquet_path.isascii():
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(parquet_path, tmp_path)
        bldg = pd.read_parquet(tmp_path)
        os.unlink(tmp_path)
    else:
        bldg = pd.read_parquet(parquet_path)

    # Deduplicate to unique centroid positions (the skeleton may repeat)
    coords = bldg[[lon_col, lat_col, district_col]].drop_duplicates(
        subset=[lon_col, lat_col]
    )

    # Build KD-tree for fast nearest-neighbour matching
    from scipy.spatial import cKDTree

    # Convert centroid lat/lon to approximate km for KD-tree
    mid_lat = np.median(coords[lat_col])
    cos_lat = np.cos(np.radians(mid_lat))

    src_xy = np.column_stack([
        coords[lon_col].values * cos_lat * 111.32,  # km (approx)
        coords[lat_col].values * 111.32,
    ])

    tgt_xy = np.column_stack([
        centroids.lon * cos_lat * 111.32,
        centroids.lat * 111.32,
    ])

    tree = cKDTree(src_xy)
    distances, indices = tree.query(tgt_xy, distance_upper_bound=tolerance_km)

    # Build district mapping
    matched = distances < tolerance_km  # only those within tolerance
    district_names = sorted(bldg[district_col].dropna().unique().tolist())
    # Filter to actual Shanghai districts
    shanghai_districts = [
        "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
        "闵行区", "宝山区", "嘉定区", "浦东新区", "金山区", "松江区", "青浦区",
        "奉贤区", "崇明区",
    ]
    district_names = [d for d in shanghai_districts if d in district_names]

    n_centroids = len(centroids.lat)
    mapping = {}
    for dname in district_names:
        src_mask = coords[district_col].values == dname
        src_indices = np.where(src_mask)[0]
        # A centroid belongs to this district if its nearest building is in it
        tgt_mask = np.isin(indices, src_indices) & matched
        mapping[dname] = tgt_mask

    LOGGER.info(
        "District mapping: %d districts, %.1f%% centroid coverage.",
        len(mapping),
        np.mean([m.sum() for m in mapping.values()]) / n_centroids * 100,
    )
    return mapping
