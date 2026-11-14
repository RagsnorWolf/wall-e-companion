#!/usr/bin/env python3
"""Entry point for Wall-E Companion Desktop App"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from ui.desktop_app import main

if __name__ == "__main__":
    main()