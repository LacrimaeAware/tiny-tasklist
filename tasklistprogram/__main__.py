"""`python -m tasklistprogram` starts the local web server (see webserver.py)."""
from .webserver import main

if __name__ == "__main__":
    raise SystemExit(main())
