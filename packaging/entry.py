"""PyInstaller entry point for the Stress & Aero desktop application."""

import sys

from stressaero.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
