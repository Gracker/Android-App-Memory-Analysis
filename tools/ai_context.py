#!/usr/bin/env python3
"""Repository wrapper for the provider-neutral Android memory AI context CLI."""

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from android_memory_ai.cli import main


if __name__ == "__main__":
    sys.exit(main())
