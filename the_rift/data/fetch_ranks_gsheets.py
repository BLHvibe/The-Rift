"""Backwards-compat shim.

The real implementation now lives in `data.fetch_ranks/` — split out of this
3.7k-line monolith into focused submodules (constants / sheets / scoring /
riot / tier_analytics / rankings / scouting / inhouse / activity / draft /
cli) during the Phase 1 modularize pass.

External callers can keep using either path:

    import data.fetch_ranks_gsheets as fg
    fg.main()

or the cleaner package import:

    from data.fetch_ranks import main, fetch_ranked, ...
"""
from __future__ import annotations

# When invoked as a script (subprocess from the launcher) rather than
# imported, `data/` isn't necessarily on sys.path. Walk up to the project
# root and add it so `from data.fetch_ranks import *` resolves.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _here = _os.path.dirname(_os.path.abspath(__file__))
    _root = _os.path.dirname(_here)            # the_rift/
    if _root not in _sys.path:
        _sys.path.insert(0, _root)

# Re-export the full public API for legacy callers.
from data.fetch_ranks import *           # noqa: F401,F403,E402
from data.fetch_ranks.cli import main    # noqa: F401,E402


if __name__ == "__main__":
    main()
