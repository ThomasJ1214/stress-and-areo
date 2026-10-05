"""Allow ``python -m stressaero`` to launch the desktop application."""

import sys


def _run() -> int:
    from stressaero.ui.app import main

    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(_run())
