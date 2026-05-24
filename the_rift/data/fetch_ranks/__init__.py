"""data.fetch_ranks — modular split of the legacy fetch_ranks_gsheets.py.

This package replaces the 3.7k-line monolith with focused submodules. All
public symbols are still re-exported here for backwards-compatibility with
existing callers that do `import data.fetch_ranks_gsheets as fg; fg.X()`.
"""
from __future__ import annotations

# Re-export everything from every submodule. Order matters — modules with
# fewer deps come first.
from .constants import *            # noqa: F401,F403
from .sheets import *               # noqa: F401,F403
from .scoring import *              # noqa: F401,F403
from .riot import *                 # noqa: F401,F403
from .tier_analytics import *       # noqa: F401,F403
from .rankings import *             # noqa: F401,F403
from .scouting import *             # noqa: F401,F403
from .inhouse import *              # noqa: F401,F403
from .activity import *             # noqa: F401,F403
from .draft import *                # noqa: F401,F403
from .cli import main               # noqa: F401
