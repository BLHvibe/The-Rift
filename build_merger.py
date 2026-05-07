"""Merge launcher.py + fetch_ranks_gsheets.py + inhouse_tracker.py into app.py.

Strategy:
- Each command-line script's source becomes a function `_run_X(argv)` that
  takes a list of args, monkey-patches sys.argv, and calls its main().
- All three modules have their `if __name__ == "__main__":` blocks removed.
- An entry-point dispatcher at the bottom looks at sys.argv[1] to decide
  whether to launch the GUI, run the analytics script, or run the in-house
  tracker.
- Credentials and Riot API key are embedded as constants at the top.
- Resource paths (credentials, config) use a portable lookup that works
  both from source AND from a PyInstaller-frozen .exe.
"""
import re
import textwrap
from pathlib import Path
from secrets import EMBEDDED_API_KEY, CREDENTIALS_PATH

LAUNCHER = Path("launcher.py").read_text(encoding="utf-8")
MAIN     = Path("fetch_ranks_gsheets.py").read_text(encoding="utf-8")
INHOUSE  = Path("inhouse_tracker.py").read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# 1. Extract bodies of the two CLI scripts (everything except `if __name__`)
# ─────────────────────────────────────────────────────────────────────

def strip_main_block(src):
    """Remove the `if __name__ == "__main__":` block at the bottom."""
    m = re.search(r'\nif __name__ == ["\']__main__["\']:\s*\n.*?\Z',
                  src, re.DOTALL)
    if m:
        src = src[:m.start()]
    return src.rstrip() + "\n"


def strip_imports(src):
    """Remove top-level `import` and `from ... import` statements.
    They'll be deduplicated and put at the top of the merged file.
    Preserves any non-import code that's between the imports and the rest.
    """
    lines = src.split("\n")
    keep_lines = []
    in_imports_section = True

    for ln in lines:
        s = ln.strip()
        if in_imports_section:
            # In the early section, drop imports and blank lines
            if s.startswith("import ") or s.startswith("from "):
                continue
            if s.startswith("#") or s == "":
                # Comments and blanks at the top get dropped (we'll add our own)
                continue
            # First non-import non-comment line: we're past the imports section
            in_imports_section = False
            keep_lines.append(ln)
        else:
            # In the body, only drop module-level imports of the same form
            # to avoid duplicate `import argparse` etc.
            if s.startswith("import ") or s.startswith("from "):
                # Only drop if it's at module level (no indent)
                if not ln.startswith(" ") and not ln.startswith("\t"):
                    continue
            keep_lines.append(ln)

    return "\n".join(keep_lines)


def collect_imports(src):
    """Return a sorted list of unique top-level import statements from src."""
    out = set()
    for ln in src.split("\n"):
        s = ln.strip()
        if (s.startswith("import ") or s.startswith("from ")) and \
                not ln.startswith(" ") and not ln.startswith("\t"):
            out.add(s)
    return out


# ─────────────────────────────────────────────────────────────────────
# 2. Read each script's source after stripping
# ─────────────────────────────────────────────────────────────────────

launcher_clean = strip_main_block(LAUNCHER)
main_clean     = strip_main_block(MAIN)
inhouse_clean  = strip_main_block(INHOUSE)

# Collect & dedupe imports from all 3 scripts
all_imports = (collect_imports(launcher_clean)
               | collect_imports(main_clean)
               | collect_imports(inhouse_clean))

# Strip top-level imports from each (we'll put them all at the top)
launcher_body = strip_imports(launcher_clean)
main_body     = strip_imports(main_clean)
inhouse_body  = strip_imports(inhouse_clean)


# ─────────────────────────────────────────────────────────────────────
# 3. Wrap the two CLI scripts' bodies in functions for namespace isolation
# ─────────────────────────────────────────────────────────────────────

# Indent the body by 4 spaces, then we'll wrap it in a function that
# calls main() at the end. This isolates each module's globals from
# the launcher's globals — name collisions like load_champion_map()
# don't conflict because they live in different function scopes.

def indent_body(body, by=4):
    return "\n".join((" " * by + ln) if ln.strip() else ln
                     for ln in body.split("\n"))


main_indented    = indent_body(main_body)
inhouse_indented = indent_body(inhouse_body)


# ─────────────────────────────────────────────────────────────────────
# 4. Embed credentials and API key
# ─────────────────────────────────────────────────────────────────────

CREDS_JSON = Path(CREDENTIALS_PATH).read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────
# Auto-update configuration
# ─────────────────────────────────────────────────────────────────────
# The version that gets baked into the .exe. Bump this in version.txt
# whenever you publish a new release. The auto-update logic compares
# this to the latest GitHub release tag and prompts users to update.
VERSION = Path("version.txt").read_text(encoding="utf-8").strip() if Path("version.txt").exists() else "0.0.0"

# Your GitHub repo for hosting releases, in "owner/repo" format.
# When you publish a release with a tag like "v1.0.1" and attach the
# .exe as an asset, the app will detect it and prompt users to update.
# Leave empty ("") to disable auto-update entirely.
GITHUB_REPO = "BLHvibe/The-Rift"

# Use a triple-quoted r-string with a unique sentinel so backslashes/quotes
# in the JSON don't trip us up. We base64-encode to be safe.
import base64
CREDS_B64 = base64.b64encode(CREDS_JSON.encode("utf-8")).decode("ascii")


# ─────────────────────────────────────────────────────────────────────
# 5. Build the final app.py
# ─────────────────────────────────────────────────────────────────────

HEADER = '''# -*- coding: utf-8 -*-
"""LoL Power Rankings — bundled distribution.

This is the merged single-file build of the launcher + analytics scripts
+ in-house tracker. Generated automatically by build.py — don't edit by hand.

Entry points (selected via --mode argument; default = launch GUI):
  (no args)            Launch the GUI launcher
  --mode=fetch_ranks   Run the rank/scout/draft analytics CLI
  --mode=inhouse       Run the in-house tracker CLI

When packaged as a one-file .exe via PyInstaller, the GUI invokes this
same .exe with --mode=... to run the analytics subprocesses.
"""
'''

IMPORTS = "\n".join(sorted(all_imports)) + "\n"

EMBED_BLOCK = f'''
# ─── Embedded credentials and API key ────────────────────────────────
# These are baked into the distribution build. DO NOT share this file
# publicly — it grants service-account access to the Google Sheet and
# contains a Riot API key.

import base64 as _b64

_EMBEDDED_CREDS_B64 = "{CREDS_B64}"
_EMBEDDED_API_KEY = "{EMBEDDED_API_KEY}"


def _resolve_resource_dir():
    """Return a directory next to the .exe (frozen) or the script (source).

    PyInstaller sets sys.frozen=True and stores extracted bundle resources
    under sys._MEIPASS; user-writable files should sit next to the .exe.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _user_data_dir():
    r"""Per-user app data directory. Created if missing.

    Windows: %LOCALAPPDATA%\\LoLPowerRankings\\
    Other:   ~/.lolpowerrankings/
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "LoLPowerRankings")
    else:
        d = os.path.join(os.path.expanduser("~"), ".lolpowerrankings")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        # Fall back to the .exe's directory if we can't write to user-data
        d = _resolve_resource_dir()
    return d


def _materialize_creds():
    """Ensure the embedded credentials JSON is on disk in a stable location.

    Returns the filesystem path. Writes the file if it's missing or the
    contents differ from the embedded version (so updates ship the latest
    creds). Re-callable at any time without churn.
    """
    target = os.path.join(_user_data_dir(), "credentials.json")
    creds_text = _b64.b64decode(_EMBEDDED_CREDS_B64).decode("utf-8")

    # Skip the write if the existing file is already correct
    try:
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as f:
                if f.read() == creds_text:
                    return target
    except Exception:
        pass  # fall through to rewrite

    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(creds_text)
    except Exception:
        # Last-ditch fallback: write to a temp file in the .exe's directory
        # (covers weird permission setups where %LOCALAPPDATA% isn't writable).
        target = os.path.join(_resolve_resource_dir(), "credentials.json")
        with open(target, "w", encoding="utf-8") as f:
            f.write(creds_text)

    return target

'''

# We need to patch a few things in the launcher body:
# 1. CONFIG_FILE should sit next to the .exe, not the cwd
# 2. DEFAULT_CONFIG.creds_path should default to _materialize_creds()
# 3. DEFAULT_CONFIG.api_key should default to _EMBEDDED_API_KEY
# 4. _build_cmd should reference sys.executable + --mode flags instead of separate scripts
# 5. _script_dir should return _resolve_resource_dir()

LAUNCHER_PATCHES = [
    # Inject version baked from version.txt
    ('__version__ = "0.0.0"',
     f'__version__ = "{VERSION}"'),
    # Inject GitHub repo for auto-update
    ('GITHUB_REPO = ""  # e.g. "blhei/lol-power-rankings" — set in build_merger.py',
     f'GITHUB_REPO = "{GITHUB_REPO}"'),
    # CONFIG_FILE next to executable
    ('CONFIG_FILE = "launcher_config.json"',
     'CONFIG_FILE = os.path.join(_resolve_resource_dir(), "launcher_config.json")'),
    # API key default = embedded
    ('"api_key": "",',
     '"api_key": _EMBEDDED_API_KEY,'),
    # creds_path default = materialized
    ('"creds_path": "credentials.json",',
     '"creds_path": _materialize_creds(),'),
    # load_config: always re-materialize creds and use embedded API key,
    # overriding whatever was saved on disk. Otherwise stale paths from
    # previous runs (e.g. old temp files that got cleaned) cause crashes.
    (
'''def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(json.load(f))
                return cfg
        except: pass
    return DEFAULT_CONFIG.copy()''',
'''def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(json.load(f))
                # Always override with current embedded values — stale temp
                # paths from previous runs would crash gspread otherwise.
                cfg["creds_path"] = _materialize_creds()
                if not cfg.get("api_key"):
                    cfg["api_key"] = _EMBEDDED_API_KEY
                return cfg
        except: pass
    # Fresh-install path: also re-materialize in case the file got cleaned
    # between module-load and now.
    cfg = DEFAULT_CONFIG.copy()
    cfg["creds_path"] = _materialize_creds()
    return cfg'''),
    # save_config: never persist creds_path to disk — _materialize_creds()
    # always re-resolves it on load. Persisting it just creates stale state.
    (
'''def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)''',
'''def save_config(cfg):
    # Don't persist creds_path; it's re-materialized on every load.
    cfg_to_save = {k: v for k, v in cfg.items() if k != "creds_path"}
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg_to_save, f, indent=2)'''),
    # _script_dir → resolve_resource_dir
    ('def _script_dir(self):\n        return os.path.dirname(os.path.abspath(__file__))',
     'def _script_dir(self):\n        return _resolve_resource_dir()'),
    # _py → sys.executable when frozen, python otherwise
    ('def _py(self):\n        return "python" if sys.platform == "win32" else "python3"',
     'def _py(self):\n        # When frozen (PyInstaller .exe), invoke this same .exe.\n'
     '        # In source mode, fall back to python interpreter.\n'
     '        if getattr(sys, "frozen", False):\n'
     '            return sys.executable\n'
     '        return "python" if sys.platform == "win32" else "python3"'),
    # _build_cmd: use --mode= flags and target this same exe instead of separate .py files
    (
'''    def _build_cmd(self, mode):
        py = self._py()
        sd = self._script_dir()
        key = self.api_var.get().strip()
        sheet = self.config["sheet_url"]
        creds = self.config["creds_path"]

        if mode == "inhouse":
            return [py, os.path.join(sd, "inhouse_tracker.py"),
                    "--sheet", sheet, "--creds", creds]

        base = [py, os.path.join(sd, "fetch_ranks_gsheets.py"),
                "--key", key, "--sheet", sheet, "--creds", creds,
                "--region", self.config["region"],
                "--routing", self.config["routing"]]

        flags = {
            "update": [], "update_fast": ["--skip-matches"],
            "scout": ["--scout"], "scout_only": ["--scout-only"],
            "scout_new": ["--scout-new"],
            "setup_draft": ["--setup-draft"], "draft": ["--draft"],
        }
        if mode == "scout_player":
            name = self.rescount_player_var.get().strip()
            return base + ["--scout-player", name]
        return base + flags.get(mode, [])''',
'''    def _build_cmd(self, mode):
        py = self._py()
        key = self.api_var.get().strip()
        sheet = self.config["sheet_url"]
        creds = self.config["creds_path"]
        # When frozen (.exe), we invoke ourselves with --mode=.... When running
        # from source, we re-invoke this same script via python with --mode=....
        if getattr(sys, "frozen", False):
            self_target = [sys.executable]
        else:
            self_target = [py, os.path.abspath(__file__)]

        if mode == "inhouse":
            return self_target + ["--mode=inhouse",
                                  "--sheet", sheet, "--creds", creds]

        base = self_target + ["--mode=fetch_ranks",
                              "--key", key, "--sheet", sheet, "--creds", creds,
                              "--region", self.config["region"],
                              "--routing", self.config["routing"]]

        flags = {
            "update": [], "update_fast": ["--skip-matches"],
            "scout": ["--scout"], "scout_only": ["--scout-only"],
            "scout_new": ["--scout-new"],
            "setup_draft": ["--setup-draft"], "draft": ["--draft"],
        }
        if mode == "scout_player":
            name = self.rescount_player_var.get().strip()
            return base + ["--scout-player", name]
        return base + flags.get(mode, [])'''),
]

launcher_patched = launcher_body
for old, new in LAUNCHER_PATCHES:
    if old not in launcher_patched:
        raise SystemExit(f"PATCH FAILED: missing pattern\n{old[:200]}")
    launcher_patched = launcher_patched.replace(old, new)


# ─────────────────────────────────────────────────────────────────────
# 6. Wrap CLI scripts in dispatcher functions
# ─────────────────────────────────────────────────────────────────────

# Each CLI script's body lives inside a function. The function:
#   - Receives argv (list of args, excluding the program name)
#   - Sets sys.argv to ["program-name"] + argv so argparse works
#   - Defines the script's globals locally (load_champion_map etc. are scoped here)
#   - Calls main() at the end
#
# Because the body is indented 4 spaces and contains its own `def main():`,
# python treats `main()` as a local variable in the dispatcher function. We
# call it at the end of the function body.

DISPATCHERS = '''
def _run_fetch_ranks(argv):
    """Run the rank/scout/draft analytics CLI in a subprocess context."""
    import sys as _sys
    _sys.argv = ["fetch_ranks_gsheets"] + list(argv)
{main_indented}
    main()


def _run_inhouse(argv):
    """Run the in-house tracker CLI in a subprocess context."""
    import sys as _sys
    _sys.argv = ["inhouse_tracker"] + list(argv)
{inhouse_indented}
    main()
'''.format(main_indented=main_indented, inhouse_indented=inhouse_indented)


# ─────────────────────────────────────────────────────────────────────
# 7. Final dispatcher and __main__ block
# ─────────────────────────────────────────────────────────────────────

ENTRY = '''
def _rewire_stdio():
    """Rewire sys.stdout/stderr to the real pipe fd when running headless.

    PyInstaller --windowed sets sys.stdout = None (no console attached).
    When the GUI spawns a child instance with --mode=fetch_ranks/inhouse,
    the parent opens a pipe on fd 1/2, but Python's print() still targets
    sys.stdout — which is None. Rewiring it to the OS fd makes all print()
    output flow through the pipe to the parent's console widget.
    """
    import io
    for fd, name in ((1, "stdout"), (2, "stderr")):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "write"):
            try:
                setattr(sys, name,
                        io.TextIOWrapper(io.FileIO(fd, closefd=False),
                                         encoding="utf-8", line_buffering=True))
            except Exception:
                pass


def _main_dispatch():
    """Decide whether to launch the GUI or run a CLI subcommand."""
    argv = sys.argv[1:]
    mode = None
    cli_args = []
    for a in argv:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
        else:
            cli_args.append(a)

    if mode in ("fetch_ranks", "inhouse"):
        _rewire_stdio()

    if mode == "fetch_ranks":
        _run_fetch_ranks(cli_args)
    elif mode == "inhouse":
        _run_inhouse(cli_args)
    else:
        app = App()
        app.mainloop()


if __name__ == "__main__":
    _main_dispatch()
'''


# ─────────────────────────────────────────────────────────────────────
# 8. Assemble
# ─────────────────────────────────────────────────────────────────────

PARTS = [
    HEADER,
    IMPORTS,
    EMBED_BLOCK,
    "# ─── Launcher (GUI) ─────────────────────────────────────────────────\n",
    launcher_patched,
    "\n# ─── CLI subcommand dispatchers ─────────────────────────────────────\n",
    DISPATCHERS,
    ENTRY,
]

OUT = "\n".join(PARTS)
Path("app.py").write_text(OUT, encoding="utf-8")
print(f"Wrote app.py: {len(OUT.splitlines())} lines, {len(OUT):,} bytes")
print(f"Imports collected: {len(all_imports)}")
print(f"Embedded credentials: {len(CREDS_JSON)} bytes")
print(f"Embedded API key: {EMBEDDED_API_KEY[:20]}...")
