"""Coursework implementation; synthetic evidence is not a production certification."""

import os
from pathlib import Path

# Keep the directory handle alive. Linux/container users use libgomp, not these DLLs.
_runtime = Path(__file__).resolve().parents[1] / "tools" / "runtime"
_dll_handle = os.add_dll_directory(str(_runtime)) if os.name == "nt" and _runtime.exists() else None
