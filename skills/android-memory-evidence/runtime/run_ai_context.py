#!/usr/bin/env python3
"""Run the bundled Android memory AI context CLI without repository dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from android_memory_ai.cli import main


if __name__ == "__main__":
    sys.exit(main())
