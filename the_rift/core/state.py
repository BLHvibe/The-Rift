"""
Global app state. All tabs read from and write to this object.
Background threads populate it; the UI reads it on each frame.
"""
import threading

class AppState:
    def __init__(self):
        self._lock = threading.Lock()

        # Config / identity
        self.config          = {}
        self.player_list     = []       # list of player name strings
        self.riot_to_display = {}       # riot_id -> display name

        # Rankings
        self.rankings_data   = None     # list of dicts once loaded
        self.rankings_ready  = False
        self.rankings_loading = False

        # Draft
        self.draft_result    = None
        self.draft_loading   = False
        self.draft_teams     = {"blue": [], "red": []}

        # Scout
        self.scout_data      = None
        self.scout_loading   = False

        # Inhouse
        self.inhouse_data    = None
        self.inhouse_loading = False
        self.last_logged_game = None    # set briefly after a game is logged

        # Tier list
        self.tierlist_state  = {}

        # UI navigation
        self.active_tab      = "rankings"   # "rankings"|"draft"|"scout"|"inhouse"|"tierlist"|"settings"|"commands"
        self.prev_tab        = None
        self.nav_to_scout    = None         # set to a player name to navigate → scout tab

        # Splash
        self.splash_done     = False
        self.fun_fact        = ""

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def get(self, key, default=None):
        with self._lock:
            return getattr(self, key, default)


state = AppState()
