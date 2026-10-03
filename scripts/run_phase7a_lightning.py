#!/usr/bin/env python3
"""Compatibility launcher; use an installed/editable crypto_ai environment."""

from crypto_ai.phase7.lightning import REQUIRED_RUNTIME_VARIABLES as REQUIRED_RUNTIME_VARIABLES
from crypto_ai.phase7.lightning import main

if __name__ == "__main__":
    raise SystemExit(main())
