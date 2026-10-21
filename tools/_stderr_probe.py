"""Probe: does piping stderr of a run.ps1-launched script kill the child?

Prints to both streams and exits 0. Used to pick a safe launch method for the
long pipeline run.
"""

import sys
import time

print("stdout: line 1", flush=True)
print("stderr: line 1", file=sys.stderr, flush=True)
time.sleep(0.5)
print("stdout: line 2", flush=True)
print("stderr: line 2", file=sys.stderr, flush=True)
time.sleep(0.5)
print("stdout: FINAL LINE (must be visible)", flush=True)
sys.exit(0)
