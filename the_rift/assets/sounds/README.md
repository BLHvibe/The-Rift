# Draft Tool audio cues

The Draft Tool's `ui/audio.py` wrapper looks for the six cue files below
in this directory. The wrapper degrades to silent no-ops if any file is
missing — the app still runs, just without that cue. So you can land
sounds incrementally.

Naming + intended length / vibe:

| File                       | When                              | Suggested length / character |
|----------------------------|-----------------------------------|------------------------------|
| `lock.wav`                 | A champion pick is locked         | ~120 ms thunk                |
| `ban.wav`                  | A champion ban is locked          | ~120 ms muted thud           |
| `turn_chime.wav`           | Action becomes the local side's   | ~250 ms rising chime         |
| `archetype_stinger.wav`    | User confirms their archetype     | ~600 ms stinger              |
| `pivot_alert.wav`          | Pivot-alert banner first appears  | ~400 ms warning sting        |
| `draft_complete.wav`       | Final action of the draft lands   | ~1500 ms outro flourish      |

Format guidance: 16-bit WAV (or OGG Vorbis) at 44.1 kHz. Stereo or mono
both work. Keep each file under ~80 KB so the total bundle stays around
~300 KB.

Sourcing: Freesound (CC0) is the user-blessed source per the rewrite
plan. Bake CC0 attribution into the project's NOTICE / LICENSE if any
file uses a less-permissive license.

This README is bundled by PyInstaller along with the sound files; it is
harmless at runtime.
