"""Enables `python -m vidbyte_cli`. The only job here is turning a status into SystemExit."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
