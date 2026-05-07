# UI Cinematic Modernization Research

## 1. Current State

The app uses plain tkinter with a hand-crafted dark theme. Key characteristics:

- **Color palette** (`C` dict, launcher.py:102–149): deep navy backgrounds (`#06090f`, `#0c1422`), warm gold accents (`#c8a86a`, `#f3e6c4`), teal wins (`#5fb89a`), red losses (`#c84b31`). A League-of-Legends-adjacent palette already.
- **Font**: Segoe UI, 9–22pt, normal/bold/italic.
- **Window**: 1150×860, min 1000×700.
- **Existing animations** (all via `.after()` loops):
  - Podium cascade: center card at 60ms, side cards at 360ms + 220ms×i stagger.
  - Row stagger: rankings rows appear 45ms apart.
- **Widgets**: `tk.Canvas` + `tk.Frame` + `tk.Label` for all layout; `ttk.Notebook` for tabs; `ScrolledText` for console.
- **Visual ceiling**: rectangular widgets, no shadows, no rounded corners, no GPU compositing, no transitions between states.

---

## 2. Effects We Want

| Effect | Description |
|--------|-------------|
| Card slide-in | Ranked player cards animate in from below or fade in from 0 opacity |
| Glow on #1 | Top-ranked player entry pulses or glows gold |
| Loading shimmer | While background threads fetch data, a shimmer sweeps across placeholder bars |
| Tab transitions | Switching tabs crossfades or slides content instead of instant swap |
| Rank badge sparkle | On tier reveal (e.g. Diamond), a brief particle/sparkle burst |
| Podium entrance | More dramatic podium build: 3rd drops in, then 2nd, then 1st with fanfare delay |

---

## 3. Tkinter + Canvas Capabilities

### What's achievable today (no new libraries)

**Canvas alpha layering:** tkinter `Canvas` items support `stipple` patterns and `fill` colors but NOT true alpha blending. Simulating glow requires drawing multiple overlapping ovals with progressively lighter colors — workable but ugly at >4 rings.

**Image blending with PIL:** `from PIL import Image, ImageFilter, ImageTk` opens real alpha compositing. A Gaussian-blurred gold oval behind a label gives a genuine glow. This is the best native-tkinter approach for glow effects.

```python
# Glow halo behind top player
img = Image.new("RGBA", (300, 80), (0,0,0,0))
draw = ImageDraw.Draw(img)
draw.ellipse([10,10,290,70], fill=(200,168,106,80))
blurred = img.filter(ImageFilter.GaussianBlur(radius=12))
photo = ImageTk.PhotoImage(blurred)
canvas.create_image(150, 40, image=photo)
```

**Slide/fade via `.after()` loops:** Pure tkinter can animate `place()` geometry (x, y) or `Canvas.move()` on every frame. At 16ms intervals (≈60 FPS) this is smooth for simple translations. Fade requires PIL alpha blending since tkinter labels don't have opacity.

**Shimmer:** A Canvas rectangle with a moving gradient (simulated by updating `fill` color across N rectangles per frame) is the native approach. Works but CPU-heavy if the shimmer is wide.

**Tab transitions:** `ttk.Notebook` doesn't support transition hooks. Workaround: hide the Notebook, show a Canvas overlay, animate it, then show the new tab. Complex to implement cleanly.

### Hard limits of tkinter

- No GPU rendering — every pixel is CPU-drawn via GDI/Xlib. Complex animations (>50 moving elements) will stutter.
- No compositing or layer opacity without PIL.
- No CSS-style transitions or keyframe animations.
- No vector graphics (SVG/Canvas paths) without third-party libs.
- `ttk.Notebook` tab switching is instant with no hook to intercept.

**Bottom line:** tkinter with PIL can achieve glow effects and slide animations well. Shimmers and tab transitions are possible but require significant custom code and will show CPU strain on lower-end machines.

---

## 4. Framework Options

### A. CustomTkinter

**What it adds over tkinter:**
- Rounded corners on buttons, frames, entry fields, progress bars — natively, no hacks.
- Built-in dark/light theme system with `set_appearance_mode("dark")`.
- Modern widget set: `CTkButton`, `CTkFrame`, `CTkScrollableFrame`, `CTkProgressBar`, `CTkSlider`, `CTkSwitch`.
- Consistent cross-platform rendering (draws its own widgets, not OS-native).
- Still uses `.after()` for animations — no animation system built in.

**What it does NOT add:**
- No animation framework (still need PIL + `.after()` loops for movement).
- No hardware acceleration.
- Rounded corners only on CTk* widgets; tk.Label/tk.Canvas still rectangular.

**Migration effort from this 6062-line app:**
- Replace `tk.Button` → `ctk.CTkButton`, `tk.Frame` → `ctk.CTkFrame`, `tk.Entry` → `ctk.CTkEntry`, `tk.Label` → `ctk.CTkLabel` throughout.
- Remap color references: the existing `C` dict maps to CTk's theme system, or just pass `fg_color`, `text_color` kwargs directly.
- `ttk.Notebook` → `ctk.CTkTabview` (different API — tabs are added with `.add(name)`, not `.add(frame)`).
- Estimated effort: **30–50 hours** for a thorough swap. Risk: low (CTk wraps tkinter, can be incremental).
- Visual improvement: **high** — rounded corners + consistent dark theme alone make it look like a modern app.

**Verdict:** Best first move. Incremental, low risk, high visual payoff.

---

### B. ttkbootstrap

**What it adds:**
- Bootstrap-style CSS themes applied to all ttk widgets (Darkly, Cyborg, Solar, etc.) — 20+ built-in themes.
- No new widget classes; existing `ttk.*` widgets just look better.
- `ttk.Progressbar` gets animated striped variants.
- Very easy to adopt: `import ttkbootstrap as ttk` replaces `from tkinter import ttk`.

**Limitations:**
- Themes apply only to `ttk.*` widgets. The app uses heavy `tk.*` (Label, Frame, Canvas) — those stay unstyled.
- No rounded corners (OS-dependent).
- No animation system beyond ttk's built-in progressbar animation.

**Verdict:** Quickest one-line improvement but shallow impact on this app's custom widget-heavy layout. Not recommended as the primary modernization path.

---

### C. PyQt6

**What it adds:**
- `QPropertyAnimation` + `QSequentialAnimationGroup` + `QParallelAnimationGroup`: declarative, easing-curve animations on any widget property (geometry, opacity, color).
- Qt StyleSheets (QSS): CSS-like syntax, `border-radius`, `background-color` gradients, `box-shadow` analogs via layered widgets.
- Hardware-accelerated compositing via Qt 6's RHI (Vulkan/Metal/D3D12 backend).
- `QGraphicsView` + `QGraphicsScene`: scene graph for GPU-composited effects (glow via `QGraphicsBlurEffect`, drop shadows, opacity groups).
- `QTabWidget` can be styled with custom tab transitions via `QStackedWidget` + `QPropertyAnimation`.

**What the migration looks like:**
- Full rewrite required — Qt's signal/slot event model, layout managers (`QVBoxLayout`, `QHBoxLayout`), and widget hierarchy are entirely different from tkinter.
- Every method that touches `tk.*` widgets needs to be rewritten.
- Estimated effort: **250–400 hours** for this codebase.
- Licensing: PyQt6 is GPL v3. For private use with trusted friends, fine. For distribution/commercialization, requires a Qt commercial license ($~500/yr).

**Verdict:** The highest visual ceiling by far. Every cinematic effect in this list is trivial in PyQt6. But the effort is 5–10x CustomTkinter. Only worth it if a full rewrite is planned.

---

### D. Dear PyGui

**What it adds:**
- GPU immediate-mode rendering (ImGui-based) — draws at 60+ FPS regardless of UI complexity.
- Built-in animation system: `dpg.bind_item_theme()` with animated themes, `mvLineSeries`/`mvAreaSeries` for live charts.
- `add_loading_indicator()` built-in spinner widget.
- Very fast and lightweight (~3MB Python extension).

**What it means for this app:**
- Immediate-mode paradigm: the entire UI is redrawn every frame. Widgets don't persist — you describe the layout each frame. Very different from tkinter's retained-mode model.
- Theming: gold/dark themes are straightforward with `dpg.create_theme()`.
- Animations: any value interpolation (position, color, size) can be driven per-frame without `.after()` overhead.
- Estimated effort: **150–250 hours** for a rewrite. Shorter than PyQt6 because Dear PyGui's Python API is simpler, but the paradigm shift is steep.

**Verdict:** Best choice if a full cinematic rewrite is the goal and PyQt6's licensing complexity is a concern. Dear PyGui is MIT-licensed. The result would look and feel like a game tool, not a desktop app.

---

## 5. Specific Effect Recipes

| Effect | Best Framework | Approach | Tkinter-only Fallback |
|--------|---------------|----------|-----------------------|
| **Card slide-in** | CustomTkinter | `.place()` + `.after()` loop changing `y` from +80 to 0 over 200ms with ease-out | Same — already possible, just add the loop |
| **Glow on #1 player** | CustomTkinter + PIL | PIL GaussianBlur halo behind player frame, `CTkFrame` rounded border in gold | PIL-only: Canvas image behind the Label |
| **Loading shimmer** | CustomTkinter | Canvas with `place()` overlay, move a lighter-colored rect from left to right via `.after()`, clip to frame bounds | Same implementation works in plain tkinter |
| **Tab crossfade** | PyQt6 | `QStackedWidget` + `QPropertyAnimation` on opacity | Hard in tkinter — requires Canvas overlay trick; choppy |
| **Rank badge sparkle** | Dear PyGui | Per-frame particle system (small dots expanding outward from badge) | Canvas: animate N small ovals expanding then fading — workable |
| **Podium entrance** | Any | Already partially done; add `Canvas.move()` for y-drop + PIL fade | Enhance existing `.after()` cascade with y-offset animation |

---

## 6. Recommended Roadmap

### Phase 1 — Now, in the existing tkinter codebase (1–2 weeks, ~15h)

These require no framework change:

1. **Add PIL/Pillow dependency** — enables every alpha effect.
2. **Glow halo on #1 ranked player** — PIL Gaussian blur behind the hero card.
3. **Enhance podium entrance** — add a y-drop (cards start 60px below and rise) to the existing `.after()` cascade.
4. **Loading shimmer on rankings placeholder** — Canvas shimmer overlay while `_load_initial_rankings_bg` runs.
5. **Card fade-in** — on row reveal, start each Label at alpha=0 (PIL composite) and animate to full opacity over 150ms.

### Phase 2 — Migrate to CustomTkinter (1–2 months, ~40h)

1. Replace all `tk.Button`, `tk.Frame`, `tk.Entry` with CTk equivalents.
2. Replace `ttk.Notebook` with `ctk.CTkTabview`.
3. Update color bindings to CTk theme system.
4. Add `CTkScrollableFrame` to rankings and scouting tabs.

Result: rounded corners everywhere, consistent dark theme, modern widget set. The app looks like a polished tool.

### Phase 3 — Full Cinematic Rewrite (3–6 months, ~200h)

If the goal is a League client aesthetic with smooth 60 FPS transitions:

- **Dear PyGui** for a game-tool aesthetic (MIT license, GPU rendering, built-in animations).
- **PyQt6** for a more traditional desktop aesthetic with CSS-level styling and Qt's animation system (GPL v3, larger ecosystem).

Either path requires rewriting all UI methods from scratch. Dear PyGui has the lower learning curve for someone already comfortable with Python. PyQt6 has more community resources and better documentation.

---

## Sources

- [CustomTkinter GitHub](https://github.com/TomSchimansky/CustomTkinter)
- [ttkbootstrap docs](https://ttkbootstrap.readthedocs.io)
- [PyQt6 QPropertyAnimation docs](https://doc.qt.io/qt-6/qpropertyanimation.html)
- [Dear PyGui documentation](https://dearpygui.readthedocs.io)
- [Pillow ImageFilter docs](https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html)
