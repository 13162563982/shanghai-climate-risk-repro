#!/usr/bin/env python3
"""
CMIP6 Batch Download Script - Shanghai Climate Risk Analysis (Typhoon Study)
=============================================================================
Downloads tos, ta, hus, ua, va, psl from ESGF nodes.
Optimised for access from within China.

Key findings from connectivity testing (2025-07-25):
  DKRZ search API (esgf-data.dkrz.de)     ACCESSIBLE
  DKRZ data node  (esgf3.dkrz.de)          ACCESSIBLE
  CEDA data node  (esgf.ceda.ac.uk)        BLOCKED
  CNRM data node  (esg1.umr-cnrm.fr)       BLOCKED

Usage:
  python download_cmip6.py --dry-run           # List files without downloading
  python download_cmip6.py --variable tos      # Download only tos
  python download_cmip6.py --tier 1 --skip-psl # Tier-1 only, no psl
  python download_cmip6.py --max-workers 3     # 3 parallel downloads
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from tqdm import tqdm

# Fix Windows GBK console encoding for tqdm
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ============================================================================
# CONFIGURATION
# ============================================================================

SEARCH_NODE = "https://esgf-data.dkrz.de/esg-search/search"

PREFERRED_DATA_NODES = [
    "esgf3.dkrz.de",
    "esgf-data.dkrz.de",
    "esgf-node.ipsl.upmc.fr",
    "esgf.ceda.ac.uk",
    "esg1.umr-cnrm.fr",
]

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "cmip6_raw"

# --- Model x Variable matrix ---

TOS_MODELS = {
    "tier1": ["CNRM-CM6-1-HR", "EC-Earth3P-HR", "HadGEM3-GC31-HM"],
    "tier2": ["MPI-ESM1-2-HR", "NorESM2-MM", "GFDL-CM4"],
    "tier3": ["CESM2-WACCM", "IPSL-CM6A-LR", "CanESM5"],
}

TA_MODELS = {
    "tier1": ["CNRM-CM6-1-HR", "EC-Earth3P-HR", "HadGEM3-GC31-HM", "MRI-AGCM3-2-S"],
}

ATMOS_TIER1_MODELS = {
    "tier1": ["CNRM-CM6-1-HR", "EC-Earth3P-HR", "HadGEM3-GC31-HM", "MRI-AGCM3-2-S"],
}

EXPERIMENT_ALIASES = {
    "historical": ["historical", "hist-1950"],
    "ssp245":     ["ssp245"],
    "ssp585":     ["ssp585", "highres-future"],
}

ALL_EXPERIMENTS = ["historical", "ssp245", "ssp585"]

VARIABLE_DEFS = {
    "tos": {"table_id": "Omon", "models": TOS_MODELS,       "desc": "Sea Surface Temperature"},
    "ta":  {"table_id": "Amon", "models": TA_MODELS,         "desc": "Atmospheric Temperature (4 levels)"},
    "hus": {"table_id": "Amon", "models": ATMOS_TIER1_MODELS,"desc": "Specific Humidity (2 levels)"},
    "ua":  {"table_id": "Amon", "models": ATMOS_TIER1_MODELS,"desc": "Eastward Wind (2 levels)"},
    "va":  {"table_id": "Amon", "models": ATMOS_TIER1_MODELS,"desc": "Northward Wind (2 levels)"},
    "psl": {"table_id": "Amon", "models": ATMOS_TIER1_MODELS,"desc": "Sea Level Pressure (optional)"},
}

# ============================================================================
# HELPERS
# ============================================================================

def _first(v):
    """ESGF Solr returns single values as lists; extract first element."""
    if isinstance(v, list):
        return v[0] if v else ""
    return v if v else ""


def fmt_size(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ============================================================================
# ESGF SEARCH
# ============================================================================

def search_files(
    variable: str,
    experiment_id: str,
    source_id: str,
    table_id: str,
    frequency: str = "mon",
    variant_label: Optional[str] = "r1i1p1f1",
) -> list[dict]:
    """Search ESGF at FILE level, returning direct download URLs.
    Defaults to variant_label=r1i1p1f1 (the most common CMIP6 realisation).
    """
    params: dict[str, str] = {
        "project": "CMIP6",
        "variable": variable,
        "experiment_id": experiment_id,
        "source_id": source_id,
        "table_id": table_id,
        "frequency": frequency,
        "type": "File",
        "format": "application/solr+json",
        "limit": "200",
        "distrib": "true",
    }
    if variant_label:
        params["variant_label"] = variant_label
    try:
        resp = requests.get(SEARCH_NODE, params=params, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", {}).get("docs", [])
        return []
    except requests.RequestException:
        return []


def extract_download_urls(files: list[dict]) -> list[dict]:
    """Extract HTTPServer download URLs, preferring DKRZ data node."""
    results: list[dict] = []

    for f in files:
        url_entries = f.get("url", [])
        if isinstance(url_entries, str):
            url_entries = [url_entries]

        download_url = None
        data_node = None

        for preferred in PREFERRED_DATA_NODES:
            for entry in url_entries:
                parts = entry.split("|")
                if len(parts) >= 3 and "HTTPServer" in parts[2]:
                    candidate_url = parts[0].strip()
                    if preferred in candidate_url:
                        download_url = candidate_url
                        data_node = preferred
                        break
            if download_url:
                break

        if not download_url:
            for entry in url_entries:
                parts = entry.split("|")
                if len(parts) >= 3 and "HTTPServer" in parts[2]:
                    download_url = parts[0].strip()
                    data_node = "other"
                    break

        if not download_url:
            continue

        filename = download_url.split("/")[-1]
        size_val = f.get("size", 0)
        if isinstance(size_val, list):
            size_val = int(size_val[0]) if size_val else 0
        else:
            size_val = int(size_val) if size_val else 0

        results.append({
            "url": download_url,
            "filename": filename,
            "size": size_val,
            "data_node": data_node,
        })

    return results


def deduplicate_prefer_dkrz(files: list[dict]) -> list[dict]:
    """Group files by filename, pick best replica (DKRZ > IPSL > LLNL > CEDA)."""
    by_filename: dict[str, list[dict]] = {}
    for f in files:
        fn = f.get("title", "")
        if isinstance(fn, list):
            fn = fn[0] if fn else ""
        if fn not in by_filename:
            by_filename[fn] = []
        by_filename[fn].append(f)

    result = []
    for fn, replicas in by_filename.items():
        def score(r):
            node = _first(r.get("data_node", "")).lower()
            if "dkrz" in node: return 0
            if "ipsl" in node: return 1
            if "llnl" in node: return 2
            if "ceda" in node: return 3
            return 4
        replicas.sort(key=score)
        best = replicas[0]
        best_node = _first(best.get("data_node", "")).lower()
        if "ceda" in best_node and len(replicas) > 1:
            for r in replicas[1:]:
                node = _first(r.get("data_node", "")).lower()
                if "ceda" not in node:
                    best = r
                    break
        result.append(best)
    return result


# ============================================================================
# DOWNLOAD
# ============================================================================

def download_file(
    url: str,
    local_path: Path,
    expected_size: int = 0,
    max_retries: int = 5,
    chunk_size: int = 8 * 1024 * 1024,
    position: int = 0,
) -> tuple[bool, str]:
    """
    Download a single file with resume support and retries.
    Returns (success, error_message).
    tqdm position is used to keep progress bars from overlapping.
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)
    short_name = local_path.name

    for attempt in range(1, max_retries + 1):
        try:
            existing_size = local_path.stat().st_size if local_path.exists() else 0
            headers = {"Range": f"bytes={existing_size}-"} if existing_size > 0 else {}

            resp = requests.get(url, headers=headers, stream=True, timeout=600)
            if resp.status_code not in (200, 206):
                if attempt < max_retries:
                    time.sleep(min(30, 3 * (2 ** (attempt - 1))))
                continue

            total_size = int(resp.headers.get("content-length", 0))
            mode = "ab" if resp.status_code == 206 else "wb"
            initial_pos = existing_size if mode == "ab" else 0

            pbar = tqdm(
                total=initial_pos + total_size if total_size else None,
                initial=initial_pos,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"  {short_name[:50]}",
                position=position,
                leave=False,
                ncols=100,
                ascii=False,
            )

            with open(local_path, mode) as f_obj:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f_obj.write(chunk)
                        pbar.update(len(chunk))
            pbar.close()

            if expected_size > 0:
                actual_size = local_path.stat().st_size
                if actual_size != expected_size and attempt < max_retries:
                    local_path.unlink()
                    time.sleep(min(30, 3 * (2 ** (attempt - 1))))
                    continue

            return True, ""

        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(min(60, 5 * (2 ** (attempt - 1))))

    return False, f"failed after {max_retries} attempts"


# ============================================================================
# ORCHESTRATION
# ============================================================================

def collect_download_tasks(
    variables: list[str],
    tiers: list[int],
    experiments: list[str],
    output_dir: Path,
) -> list[dict]:
    """Search ESGF and return a flat list of download task dicts."""
    tasks: list[dict] = []

    # Build the full search grid
    search_grid: list[tuple[str, str, str, str]] = []  # (var, source_id, user_exp, table_id)
    for var in variables:
        vdef = VARIABLE_DEFS[var]
        table_id = vdef["table_id"]
        source_ids = []
        for tn in tiers:
            key = f"tier{tn}"
            if key in vdef["models"]:
                source_ids.extend(vdef["models"][key])
        for sid in source_ids:
            for uexp in experiments:
                search_grid.append((var, sid, uexp, table_id))

    print(f"  Total search queries: {len(search_grid)}")
    print()

    # Track summary per variable
    var_stats: dict[str, dict] = {}
    for v in variables:
        var_stats[v] = {"found": 0, "blocked": 0, "skipped": 0, "files": 0, "bytes": 0}

    # Search with progress bar
    with tqdm(total=len(search_grid), desc="  Searching ESGF", unit="query",
              ncols=100, position=0, leave=True) as search_bar:
        for var, source_id, user_exp, table_id in search_grid:
            exp_aliases = EXPERIMENT_ALIASES.get(user_exp, [user_exp])

            files: list[dict] = []
            used_exp_id: Optional[str] = None

            for esgf_exp in exp_aliases:
                files = search_files(
                    variable=var, experiment_id=esgf_exp,
                    source_id=source_id, table_id=table_id,
                    variant_label="r1i1p1f1",
                )
                # Fallback: if r1i1p1f1 has no data, try any variant
                if not files:
                    files = search_files(
                        variable=var, experiment_id=esgf_exp,
                        source_id=source_id, table_id=table_id,
                        variant_label=None,
                    )
                if files:
                    used_exp_id = esgf_exp
                    break

            if not files:
                var_stats[var]["skipped"] += 1
                search_bar.set_postfix_str(
                    f"{var}/{source_id}/{user_exp}: SKIP (no data)"
                )
                search_bar.update(1)
                continue

            # Prefer GN grid
            gn_files = [f for f in files if _first(f.get("grid_label", "")) == "gn"]
            gr_files = [f for f in files if _first(f.get("grid_label", "")) == "gr"]
            chosen = gn_files if gn_files else (gr_files if gr_files else files)

            # Deduplicate preferring DKRZ
            chosen = deduplicate_prefer_dkrz(chosen)

            # Check accessibility
            blocked_count = sum(
                1 for f in chosen
                if "ceda" in _first(f.get("data_node", "")).lower()
            )
            dkrz_count = sum(
                1 for f in chosen
                if "dkrz" in _first(f.get("data_node", "")).lower()
            )

            if blocked_count == len(chosen):
                var_stats[var]["blocked"] += 1
                search_bar.set_postfix_str(
                    f"{var}/{source_id}/{user_exp}: BLOCKED (CEDA only, {len(chosen)} files)"
                )
                search_bar.update(1)
                continue

            var_stats[var]["found"] += 1
            search_bar.set_postfix_str(
                f"{var}/{source_id}/{user_exp}: {len(chosen)} files"
                + (f" (via {used_exp_id})" if used_exp_id != user_exp else "")
            )

            # Extract download URLs
            dl_urls = extract_download_urls(chosen)
            for dl in dl_urls:
                subdir = Path(var) / source_id / user_exp
                tasks.append({
                    "url": dl["url"],
                    "filename": dl["filename"],
                    "local_path": output_dir / subdir / dl["filename"],
                    "size": dl["size"],
                    "data_node": dl["data_node"],
                    "variable": var,
                    "source_id": source_id,
                    "experiment": user_exp,
                    "esgf_experiment": used_exp_id,
                })
                var_stats[var]["files"] += 1
                var_stats[var]["bytes"] += dl["size"]

            search_bar.update(1)

    # Print per-variable summary
    print()
    print(f"  {'Variable':6s} {'Found':>6s} {'Blocked':>8s} {'Skipped':>8s} {'Files':>6s} {'Size':>10s}")
    print(f"  {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*6} {'-'*10}")
    for v in variables:
        s = var_stats[v]
        found_str = f"{s['found']} ok" if s['found'] > 0 else "-"
        blocked_str = str(s['blocked']) if s['blocked'] > 0 else "-"
        skipped_str = str(s['skipped']) if s['skipped'] > 0 else "-"
        print(f"  {v:6s} {found_str:>6s} {blocked_str:>8s} {skipped_str:>8s} "
              f"{s['files']:>6d} {fmt_size(s['bytes']):>10s}")

    return tasks


def main():
    parser = argparse.ArgumentParser(
        description="CMIP6 Batch Download for Shanghai Climate Risk Analysis"
    )
    parser.add_argument("--variable", nargs="+", choices=list(VARIABLE_DEFS.keys()),
                        default=None, help="Variables to download (default: all)")
    parser.add_argument("--tier", type=int, nargs="+", choices=[1, 2, 3],
                        default=None, help="Model tiers (default: all)")
    parser.add_argument("--experiment", nargs="+", choices=ALL_EXPERIMENTS,
                        default=None, help="Experiments (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only search and list files, do not download")
    parser.add_argument("--max-workers", type=int, default=2,
                        help="Parallel downloads (default: 2)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f"Output directory")
    parser.add_argument("--skip-psl", action="store_true",
                        help="Skip psl (sea level pressure)")
    parser.add_argument("--list-only", action="store_true",
                        help="List file URLs only, no download, no progress bars")
    args = parser.parse_args()

    variables = args.variable if args.variable else list(VARIABLE_DEFS.keys())
    tiers = args.tier if args.tier else [1, 2, 3]
    experiments = args.experiment if args.experiment else ALL_EXPERIMENTS
    if args.skip_psl and "psl" in variables:
        variables.remove("psl")
    output_dir = Path(args.output_dir)

    print()
    print("=" * 72)
    print("  CMIP6 Batch Download - Shanghai Climate Risk (Typhoon Study)")
    print("=" * 72)
    print(f"  Search node:  {SEARCH_NODE}")
    print(f"  Variables:    {', '.join(variables)}")
    print(f"  Tiers:        {tiers}")
    print(f"  Experiments:  {', '.join(experiments)}")
    print(f"  Output:       {output_dir}")
    print(f"  Workers:      {args.max_workers}")
    if args.dry_run:
        print(f"  Mode:         DRY-RUN (search only)")
    print("=" * 72)
    print()
    print("Note: HighResMIP models use hist-1950/highres-future experiment IDs.")
    print("      EC-Earth3P-HR & HadGEM3-GC31-HM are often CEDA-only (=blocked).")
    print("      MRI-AGCM3-2-S has no ocean output (AGCM, no tos).")
    print()

    # Phase 1: Search
    print("[Phase 1] Searching ESGF for all files...")
    print("-" * 72)
    tasks = collect_download_tasks(variables, tiers, experiments, output_dir)
    print()

    if not tasks:
        print("  No downloadable files found for the requested combination.")
        print("  Try --variable tos --tier 2 3  (CMIP models are more accessible)")
        return

    total_size = sum(t["size"] for t in tasks)
    print(f"  TOTALS: {len(tasks)} files, {fmt_size(total_size)}")
    print()

    if args.dry_run or args.list_only:
        print("[File List]")
        print("-" * 72)
        for i, t in enumerate(tasks, 1):
            note = f" (via {t['esgf_experiment']})" if t.get("esgf_experiment") != t["experiment"] else ""
            print(f"  {i:3d}. [{t['variable']:4s}] {t['source_id']:20s} {t['experiment']:12s} "
                  f"{fmt_size(t['size']):>10s}  @{t['data_node']}{note}")
            if args.list_only:
                print(f"       {t['url']}")
        return

    # Phase 2: Download
    print("[Phase 2] Downloading files...")
    print(f"          {args.max_workers} parallel workers | Resume supported | Ctrl+C to stop")
    print("-" * 72)

    stats: dict[str, dict] = {}
    for v in variables:
        stats[v] = {"total": 0, "success": 0, "failed": 0, "bytes": 0}
    for t in tasks:
        stats[t["variable"]]["total"] += 1

    # Overall download progress
    overall_pbar = tqdm(
        total=total_size,
        desc="  Overall progress",
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        position=0,
        leave=True,
        ncols=100,
    )

    completed_bytes = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_task = {
            executor.submit(
                download_file, t["url"], t["local_path"], t["size"],
                position=idx + 1,
            ): (idx, t)
            for idx, t in enumerate(tasks)
        }

        for future in as_completed(future_to_task):
            idx, task = future_to_task[future]
            var = task["variable"]
            try:
                success, err = future.result()
            except Exception as e:
                success, err = False, str(e)

            if success:
                stats[var]["success"] += 1
                stats[var]["bytes"] += task["size"]
                completed_bytes += task["size"]
                overall_pbar.update(task["size"])
                overall_pbar.set_postfix_str(
                    f"OK: {task['filename'][:40]}"
                )
            else:
                stats[var]["failed"] += 1
                overall_pbar.set_postfix_str(
                    f"FAIL: {task['filename'][:40]} - {err[:30]}"
                )
                tqdm.write(f"  [FAIL] {task['filename']}: {err}")

    overall_pbar.close()

    # Summary
    print()
    print("=" * 72)
    print("  Download Summary")
    print("=" * 72)
    grand_success = 0
    grand_failed = 0
    grand_bytes = 0
    for v in variables:
        s = stats[v]
        grand_success += s["success"]
        grand_failed += s["failed"]
        grand_bytes += s["bytes"]
        status = "OK" if s["failed"] == 0 else f"{s['failed']} FAILED"
        bar_fill = int(20 * s["success"] / max(s["total"], 1))
        bar = "#" * bar_fill + "-" * (20 - bar_fill)
        print(f"  {v:4s} [{bar}] {s['success']:>3d}/{s['total']:<3d}  {status}")
    print("-" * 72)
    print(f"  TOTAL:  {grand_success}/{len(tasks)} files, {fmt_size(grand_bytes)}")
    if grand_failed > 0:
        print(f"  Re-run to retry {grand_failed} failed file(s) (resume supported).")
    print("=" * 72)


if __name__ == "__main__":
    main()
