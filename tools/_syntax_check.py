# -*- coding: utf-8 -*-
"""Syntax check for a Python file using the builtin compiler.

`py_compile.compile(..., cfile=os.devnull)` raises FileExistsError on Windows
("nul is a non-regular file"), so the builtin compiler is used directly and no
bytecode is written.
"""

import sys
from pathlib import Path

rc = 0
for arg in sys.argv[1:]:
    p = Path(arg)
    if not p.exists():
        print(f"MISSING {p}")
        rc = 1
        continue
    try:
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
        print(f"OK      {p.name}  ({len(p.read_text(encoding='utf-8').splitlines())} lines)")
    except SyntaxError as e:
        print(f"SYNTAX  {p.name}:{e.lineno}: {e.msg}")
        rc = 1
sys.exit(rc)
