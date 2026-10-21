"""
WP1 · Code collection into NEWROOT (plan section 3 tree + WP1.1 exclusions).

Copies the authoritative v8 modelling code from V8ROOT into NEWROOT while:
  * keeping the relative layout required by 00_config.py
    (PROJECT_ROOT = __file__.parent.parent; DATA_DIR = PROJECT_ROOT/"data")
  * dropping junk (__pycache__, .bak trees, ad-hoc run logs, PPT assets)
  * relocating non-pipeline scripts into tools\\_nonpipeline and tools\\_diagnostics
  * emitting docs\\_代码归集说明.md as the audit trail

Exclusion principle: V8ROOT is read-only and untouched, so every excluded file
is still recoverable there. Each exclusion is recorded with a reason.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

V8ROOT = Path(r"D:\桌面real\陈剑老师研究工作\Shanghai_Climate_Risk_Analysis\复现公报台风研究结果\model_房地产风险_v8")
NEWROOT = V8ROOT / "期刊投稿" / "Nature-JF投稿" / "Nature npj Natural Hazards"

# --- trees copied verbatim (minus exclusions) -----------------------------
COPY_TREES = ["Climate", "Finance", "Composite", "config"]
COPY_FILES = ["run_v8.py", "run_sensitivity.py"]

# --- exclusions -----------------------------------------------------------
# any path component (dir) named like this is skipped
SKIP_DIR_NAMES = {"__pycache__", "results.bak"}
# (relpath-prefix, reason) -- exact dirs or files to skip
SKIP_EXACT = {
    r"Climate\cmip6_test_download": "empty scratch dir (CMIP6 test download)",
    r"Climate\figures": "only holds did_synth_*.png (one-off DID synthetic test output)",
}
# files at Climate\ root that are ad-hoc run logs
CLIMATE_ROOT_LOG_GLOBS = ["*_err.log", "*_out.log", "_step*.log", "_stepfig*.log"]

# --- relocated out of the pipeline ---------------------------------------
RELOCATE = {
    # src (rel to V8ROOT) -> (dest subdir under tools\, reason)
    r"Climate\tc_did_synth.py": ("_nonpipeline", "difference-in-differences synthetic experiment; not in the 11-step pipeline"),
    r"Climate\_test_integration.py": ("_nonpipeline", "environment integration smoke test; hardcodes conda env path"),
    r"Climate\download_cmip6_test.py": ("_nonpipeline", "CMIP6 download probe; not in pipeline"),
    r"scripts\download_cmip6.py": ("_nonpipeline", "CMIP6 download utility; not in pipeline"),
    r"scripts\convert_manuscript_to_mdpi.ps1": ("_nonpipeline", "manuscript conversion helper"),
    r"Climate\_check_dip.py": ("_diagnostics", "one-off diagnostic"),
    r"Climate\_diagnose_dip.py": ("_diagnostics", "one-off diagnostic"),
    r"Climate\_diagnose_drop.py": ("_diagnostics", "one-off diagnostic"),
    r"Climate\_diagnose_projection.py": ("_diagnostics", "one-off diagnostic"),
    r"Climate\_rolling_analysis.py": ("_diagnostics", "one-off rolling-window analysis"),
    r"Finance\_analyze_price.py": ("_diagnostics", "one-off price analysis"),
    r"Finance\_cvar_stderr.log": ("_diagnostics", "stderr capture of a one-off run"),
    r"Finance\_cvar_full_stderr.log": ("_diagnostics", "stderr capture of a one-off run"),
    r"Composite\_diag_linearity.py": ("_diagnostics", "one-off linearity diagnostic"),
}
# --- excluded entirely (kept in V8ROOT only) ------------------------------
EXCLUDE_ONLY = {
    r"Finance\slide31_shape6.png": "PowerPoint asset, not modelling code",
    r"Finance\slide31_shape7.png": "PowerPoint asset, not modelling code",
}


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def walk_files(root: Path):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIR_NAMES]
        for n in fns:
            yield Path(dp) / n


def should_skip(rel: Path, v8root: Path) -> str | None:
    """Return a reason string if this relative path must not be copied."""
    partes = rel.parts
    if any(p in SKIP_DIR_NAMES for p in partes):
        return f"junk dir ({partes[0]})"
    rels = str(rel)
    if rels in SKIP_EXACT:
        return SKIP_EXACT[rels]
    if rels in RELOCATE:
        return "relocated to tools\\" + RELOCATE[rels][0]
    if rels in EXCLUDE_ONLY:
        return EXCLUDE_ONLY[rels]
    # Climate root ad-hoc logs
    if rel.parts[0] == "Climate" and len(rel.parts) == 2:
        name = rel.name
        if name.endswith("_err.log") or name.endswith("_out.log") or name.endswith(".log"):
            return "ad-hoc run log"
    return None


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    copied, skipped, relocated = [], [], []
    per_tree = {}

    print("=" * 72)
    print("WP1 · code collection")
    print(f"V8ROOT  = {V8ROOT}")
    print(f"NEWROOT = {NEWROOT}")
    print("=" * 72)

    # ---- trees ----------------------------------------------------------
    for tree in COPY_TREES:
        src_root = V8ROOT / tree
        if not src_root.exists():
            print(f"  [WARN] missing tree: {tree}")
            continue
        n = 0
        b = 0
        for f in walk_files(src_root):
            rel = f.relative_to(V8ROOT)
            reason = should_skip(rel, V8ROOT)
            if reason:
                skipped.append({"path": str(rel), "reason": reason})
                continue
            dst = NEWROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            copied.append(str(rel))
            n += 1
            b += f.stat().st_size
        per_tree[tree] = {"files": n, "bytes": b}
        print(f"  [{tree:<10}] copied {n:>5} files / {b:>12,} B")

    # ---- standalone files ----------------------------------------------
    for name in COPY_FILES:
        src = V8ROOT / name
        if src.exists():
            dst = NEWROOT / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(name)
            per_tree.setdefault("root", {"files": 0, "bytes": 0})
            per_tree["root"]["files"] += 1
            per_tree["root"]["bytes"] += src.stat().st_size
            print(f"  [root      ] copied {name}")
        else:
            print(f"  [WARN] missing file: {name}")

    # ---- relocated scripts ---------------------------------------------
    for rel, (sub, reason) in RELOCATE.items():
        src = V8ROOT / rel
        if not src.exists():
            print(f"  [WARN] relocate source missing: {rel}")
            continue
        dst = NEWROOT / "tools" / sub / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        relocated.append({"from": rel, "to": str(dst.relative_to(NEWROOT)), "reason": reason})
        print(f"  [tools\\{sub:<13}] {src.name}")
    for rel, reason in EXCLUDE_ONLY.items():
        skipped.append({"path": rel, "reason": reason})

    # ---- report ---------------------------------------------------------
    report = {
        "generated": ts,
        "v8root": str(V8ROOT),
        "newroot": str(NEWROOT),
        "per_tree": per_tree,
        "copied_count": len(copied),
        "skipped": sorted(skipped, key=lambda d: d["path"]),
        "relocated": relocated,
    }
    (NEWROOT / "docs").mkdir(parents=True, exist_ok=True)
    (NEWROOT / "docs" / "_wp1_collect_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md = ["# WP1 · 代码归集说明（自动生成）", "",
          f"> 生成时间：{ts}　来源：`{V8ROOT}`　目标：`{NEWROOT}`",
          "> 生成脚本：`tools\\_wp1_collect_code.py`（V8ROOT 只读，未改动任何既有文件）", "",
          "## 1. 复制统计", "",
          "| 目标树 | 文件数 | 字节 |", "|---|---:|---:|"]
    for k, v in per_tree.items():
        md.append(f"| `{k}\\` | {v['files']:,} | {v['bytes']:,} |")
    md.append(f"| **合计** | **{sum(v['files'] for v in per_tree.values()):,}** | "
              f"**{sum(v['bytes'] for v in per_tree.values()):,}** |")
    md += ["", "## 2. 移入 `tools\\` 的非流水线脚本", "",
           "| 原路径（V8ROOT） | 新路径（NEWROOT） | 理由 |", "|---|---|---|"]
    for r in relocated:
        md.append(f"| `{r['from']}` | `{r['to']}` | {r['reason']} |")
    md += ["", "## 3. 未复制的文件与理由", "", "| 原路径 | 理由 |", "|---|---|"]
    seen = set()
    for s in report["skipped"]:
        key = (s["path"], s["reason"])
        if key in seen:
            continue
        seen.add(key)
        md.append(f"| `{s['path']}` | {s['reason']} |")
    md += ["", "> 全部未复制项仍完整保留在 V8ROOT（只读），且已由 WP0 的 `_SHA256SUMS_before.csv` 记录。", ""]
    (NEWROOT / "docs" / "_代码归集说明.md").write_text("\n".join(md), encoding="utf-8")

    print("-" * 72)
    print(f"  copied   : {len(copied)}")
    print(f"  skipped  : {len(report['skipped'])}")
    print(f"  relocated: {len(relocated)}")
    print(f"  report   : {NEWROOT / 'docs' / '_代码归集说明.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
