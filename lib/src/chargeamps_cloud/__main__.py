"""Allow running the CLI with ``python -m chargeamps_cloud``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
