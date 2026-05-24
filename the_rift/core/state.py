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
        self.active_tab      = "home"       # "home"|"rankings"|"draft"|"scout"|"inhouse"|"tierlist"|"settings"|"commands"|"feed"
        self.prev_tab        = None
        self.nav_to_scout    = None         # set to a player name to navigate → scout tab
        self.nav_to_profile  = None         # set to a player name to open the Player Profile panel

        # Splash
        self.splash_done     = False
        self.fun_fact        = ""

        # Per-frame input gates (Phase 6). main.py resets these every frame
        # before draw, and overlay code sets click_consumed / esc_consumed
        # when it handles those inputs. Tabs underneath check these gates so
        # a single click doesn't trigger both an overlay action AND a tab
        # action, and Esc only closes the topmost overlay.
        self.click_consumed  = False
        self.esc_pressed     = False   # edge-detected, single-frame True
        self.esc_consumed    = False

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def get(self, key, default=None):
        with self._lock:
            return getattr(self, key, default)


state = AppState()
