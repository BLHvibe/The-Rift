"""
audio.py — Phase 5: minimal pygame.mixer wrapper for Draft Tool UI cues.

Six short cues fire as the draft progresses:

    play_lock()          champion pick locked        ~120ms thunk
    play_ban()           champion ban locked         ~120ms muted thud
    play_turn()          your-side action begins     ~250ms rising chime
    play_archetype()     archetype confirmed         ~600ms stinger
    play_pivot()         pivot-alert banner appears  ~400ms warning sting
    play_draft_end()     final action lands          ~1500ms outro flourish

All cues are non-blocking. Calls degrade to no-ops when:

  * pygame is not installed (so headless engine tests don't crash)
  * the sound file isn't present in the bundle (so we can ship without
    audio in early builds and add it later)
  * config.audio_enabled is False (mute toggle, default True)
  * the mixer failed to initialise (no audio device, etc.)

Sound files live in `the_rift/assets/sounds/` as 16-bit WAV / OGG. The
loader works against `sys._MEIPASS` when frozen by PyInstaller; in dev
mode it resolves the path relative to the package directory. Format:

    the_rift/assets/sounds/lock.wav
    the_rift/assets/sounds/ban.wav
    the_rift/assets/sounds/turn_chime.wav
    the_rift/assets/sounds/archetype_stinger.wav
    the_rift/assets/sounds/pivot_alert.wav
    the_rift/assets/sounds/draft_complete.wav

Royalty-free source: Freesound (CC0). Replaceable at any time without
touching this module — the loader picks up whatever's on disk on the
next app launch.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Dict, Optional

try:
    import pygame  # type: ignore
    _PYGAME_OK = True
except Exception:                                              # pragma: no cover
    pygame = None  # type: ignore[assignment]
    _PYGAME_OK = False


# ---------------------------------------------------------------------------
# State (all module-level; read-mostly after init)
# ---------------------------------------------------------------------------

_FILES = {
    "lock":            "lock.wav",
    "ban":             "ban.wav",
    "turn":            "turn_chime.wav",
    "archetype":       "archetype_stinger.wav",
    "pivot":           "pivot_alert.wav",
    "draft_end":       "draft_complete.wav",
}

_sounds: Dict[str, "pygame.mixer.Sound"] = {}     # key -> loaded Sound (or absent)
_mixer_ready: bool = False
_init_lock = threading.Lock()
_enabled: bool = True


# ---------------------------------------------------------------------------
# Init / config
# ---------------------------------------------------------------------------

def _sounds_dir() -> str:
    """Resolve the on-disk path to the bundled sounds directory.
    Works in dev (path relative to this module) and frozen PyInstaller
    builds (under sys._MEIPASS/the_rift/assets/sounds, falling back to
    the binary's directory)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidate = os.path.join(meipass, "assets", "sounds")
            if os.path.isdir(candidate):
                return candidate
            candidate = os.path.join(meipass, "the_rift", "assets", "sounds")
            if os.path.isdir(candidate):
                return candidate
        return os.path.join(os.path.dirname(sys.executable),
                            "assets", "sounds")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "assets", "sounds"))


def init() -> None:
    """Initialise pygame.mixer + preload sound files. Idempotent and
    no-op if pygame isn't importable. Safe to call from any thread; the
    first caller does the work, others fast-path out."""
    global _mixer_ready
    if not _PYGAME_OK:
        return
    with _init_lock:
        if _mixer_ready:
            return
        try:
            # Conservative defaults: 44.1 kHz / 16-bit / stereo / 512-sample
            # buffer. The 512 buffer keeps cue latency under ~12 ms; large
            # enough to avoid underruns on modest hardware.
            pygame.mixer.pre_init(frequency=44100, size=-16,
                                  channels=2, buffer=512)
            pygame.mixer.init()
        except Exception:
            # No audio device, or already-initialised by another part of
            # the app — either way we can't play sounds.
            return
        try:
            pygame.mixer.set_num_channels(8)
        except Exception:
            pass
        _mixer_ready = True
        _preload_all()


def _preload_all() -> None:
    """Try to load every sound file in _FILES. Missing files are silently
    skipped — playback functions for the missing key will be no-ops."""
    if not _mixer_ready:
        return
    folder = _sounds_dir()
    for key, fname in _FILES.items():
        path = os.path.join(folder, fname)
        if not os.path.isfile(path):
            continue
        try:
            _sounds[key] = pygame.mixer.Sound(path)
        except Exception:
            pass


def set_enabled(enabled: bool) -> None:
    """Mute toggle. Called by Settings when the user flips the audio
    checkbox, and by the config loader at app launch."""
    global _enabled
    _enabled = bool(enabled)


def is_enabled() -> bool:
    return _enabled


def is_ready() -> bool:
    """True only when pygame.mixer is initialised AND at least one sound
    file loaded. Useful for "audio: missing" diagnostics in Settings."""
    return _mixer_ready and bool(_sounds)


def loaded_keys() -> list:
    return list(_sounds.keys())


# ---------------------------------------------------------------------------
# Playback (each is fire-and-forget, non-blocking, swallow-all-errors)
# ---------------------------------------------------------------------------

def _play(key: str, volume: Optional[float] = None) -> None:
    if not _enabled or not _mixer_ready:
        return
    snd = _sounds.get(key)
    if snd is None:
        return
    try:
        if volume is not None:
            snd.set_volume(max(0.0, min(1.0, volume)))
        snd.play()
    except Exception:
        pass


def play_lock() -> None:
    _play("lock", 0.85)


def play_ban() -> None:
    _play("ban", 0.75)


def play_turn() -> None:
    _play("turn", 0.80)


def play_archetype() -> None:
    _play("archetype", 0.85)


def play_pivot() -> None:
    _play("pivot", 0.90)


def play_draft_end() -> None:
    _play("draft_end", 0.95)


# ---------------------------------------------------------------------------
# Soft auto-init — try to bring the mixer up the first time anything
# imports this module. Config-driven enable state is applied by the app
# bootstrap (which calls set_enabled(cfg["audio_enabled"]) explicitly).
# ---------------------------------------------------------------------------

try:
    init()
except Exception:                                       # pragma: no cover
    pass
