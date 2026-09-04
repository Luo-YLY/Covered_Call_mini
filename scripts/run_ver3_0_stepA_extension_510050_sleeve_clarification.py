from __future__ import annotations

import runpy
import sys
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "ver3" / "scripts" / "python" / "run_ver3_0_stepA_extension_510050_sleeve_clarification.py"


if __name__ == "__main__":
    sys.argv[0] = str(TARGET)
    runpy.run_path(str(TARGET), run_name="__main__")
