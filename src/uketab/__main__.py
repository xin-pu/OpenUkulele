"""``python -m uketab`` entry point used by the WPF desktop shell."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
