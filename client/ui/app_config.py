from __future__ import annotations

from pathlib import Path

# Application branding
APP_NAME = "PramaanHR"
TAGLINE = "PKI-secured HRMS • Tkinter + MongoDB"

# Logo path (relative to project root)

def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        if (parent / "client").exists() and (parent / "server").exists():
            return parent
    return here.parents[3]

LOGO_PATH = project_root() / "client" / "assets" / "logo.png"
