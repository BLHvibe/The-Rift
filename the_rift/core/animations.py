"""
Animation engine for The Rift.
Call animations.tick() once per DPG frame from the render loop.
"""
import math, random, time

# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------
def ease_linear(t):      return t
def ease_out_cubic(t):   return 1 - (1 - t) ** 3
def ease_in_out(t):      return 3*t*t - 2*t*t*t
def ease_elastic_out(t):
    if t == 0: return 0
    if t == 1: return 1
    c4 = (2 * math.pi) / 3
    return pow(2, -10*t) * math.sin((t*10 - 0.75) * c4) + 1
def ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

EASINGS = {
    "linear":      ease_linear,
    "out_cubic":   ease_out_cubic,
    "in_out":      ease_in_out,
    "elastic_out": ease_elastic_out,
    "out_back":    ease_out_back,
}

# ---------------------------------------------------------------------------
# Tween
# ---------------------------------------------------------------------------
class Tween:
    """
    Interpolate a single float value over time.
    on_update(value) called every tick.
    on_done() called once when finished.
    """
    def __init__(self, from_val, to_val, duration_ms, easing="out_cubic",
                 on_update=None, on_done=None, delay_ms=0):
        self.from_val    = from_val
        self.to_val      = to_val
        self.duration_ms = max(duration_ms, 1)
        self.easing      = EASINGS.get(easing, ease_out_cubic)
        self.on_update   = on_update
        self.on_done     = on_done
        self.delay_ms    = delay_ms
        self._start      = None
        self.done        = False

    def tick(self, now_ms):
        if self.done:
            return
        if self._start is None:
            self._start = now_ms
        elapsed = now_ms - self._start - self.delay_ms
        if elapsed < 0:
            return
        t = min(elapsed / self.duration_ms, 1.0)
        val = self.from_val + (self.to_val - self.from_val) * self.easing(t)
        if self.on_update:
            self.on_update(val)
        if t >= 1.0:
            self.done = True
            if self.on_done:
                self.on_done()

# ---------------------------------------------------------------------------
# Particle
# ---------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, vx, vy, color, lifetime_ms, size=4):
        self.x, self.y   = x, y
        self.vx, self.vy = vx, vy
        self.color       = color   # (r, g, b)
        self.lifetime_ms = lifetime_ms
        self.size        = size
        self._born       = None
        self.alive       = True

    def tick(self, now_ms, dt_ms):
        if self._born is None:
            self._born = now_ms
        age = now_ms - self._born
        if age >= self.lifetime_ms:
            self.alive = False
            return
        self.x  += self.vx * dt_ms / 1000
        self.y  += self.vy * dt_ms / 1000
        self.vy += 120 * dt_ms / 1000   # gravity

    @property
    def alpha(self):
        if self._born is None:
            return 255
        age = (time.monotonic() * 1000 - self._born)
        return max(0, int(255 * (1 - age / self.lifetime_ms)))

    @property
    def current_size(self):
        if self._born is None:
            return self.size
        age = time.monotonic() * 1000 - self._born
        t = min(age / self.lifetime_ms, 1.0)
        return max(1, self.size * (1 - t * 0.5))


class ParticleSystem:
    """
    Burst of particles from a point.
    color: (r, g, b) tuple
    """
    def __init__(self, x, y, color, count=30, spread=120, lifetime_ms=800, size=5):
        self.particles = []
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(30, spread)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed - random.uniform(20, 80)  # bias upward
            lt = random.uniform(lifetime_ms * 0.6, lifetime_ms)
            sz = random.uniform(size * 0.5, size * 1.4)
            delay = random.uniform(0, 80)
            p = Particle(x, y, vx, vy, color, lt, sz)
            p._delay = delay
            self.particles.append(p)
        self._start = None

    def tick(self, now_ms, dt_ms):
        if self._start is None:
            self._start = now_ms
        for p in self.particles:
            if not hasattr(p, '_delay_done'):
                if now_ms - self._start >= p._delay:
                    p._delay_done = True
                    p._born = now_ms
                else:
                    continue
            p.tick(now_ms, dt_ms)
        self.particles = [p for p in self.particles if p.alive]

    @property
    def finished(self):
        return len(self.particles) == 0

# ---------------------------------------------------------------------------
# Ripple
# ---------------------------------------------------------------------------
class Ripple:
    """Single expanding ring."""
    def __init__(self, x, y, color, max_radius=200, duration_ms=500, thickness=2):
        self.x, self.y     = x, y
        self.color         = color   # (r, g, b)
        self.max_radius    = max_radius
        self.duration_ms   = duration_ms
        self.thickness     = thickness
        self._start        = None
        self.done          = False

    @property
    def radius(self):
        return self._t * self.max_radius

    @property
    def alpha(self):
        return max(0, int(255 * (1 - self._t)))

    @property
    def _t(self):
        if self._start is None:
            return 0
        return min((time.monotonic() * 1000 - self._start) / self.duration_ms, 1.0)

    def begin(self, now_ms):
        self._start = now_ms

    def tick(self, now_ms):
        if self._start is None:
            self._start = now_ms
        if self._t >= 1.0:
            self.done = True

# ---------------------------------------------------------------------------
# Central animation manager
# ---------------------------------------------------------------------------
class AnimationManager:
    def __init__(self):
        self._tweens    = []
        self._particles = []
        self._ripples   = []
        self._last_tick = None
        # Phase 0a — global animation-intensity multiplier (0..1) and the
        # stateful store backing smooth() (hover lifts, count-ups, etc.).
        self.intensity  = 1.0
        self._smooth    = {}

    def add_tween(self, tween: Tween):
        self._tweens.append(tween)
        return tween

    def tween(self, from_val, to_val, duration_ms, easing="out_cubic",
              on_update=None, on_done=None, delay_ms=0):
        t = Tween(from_val, to_val, duration_ms, easing, on_update, on_done, delay_ms)
        return self.add_tween(t)

    def burst(self, x, y, color, count=30, spread=120, lifetime_ms=800, size=5):
        ps = ParticleSystem(x, y, color, count, spread, lifetime_ms, size)
        self._particles.append(ps)
        return ps

    def ripple(self, x, y, color, max_radius=200, duration_ms=500, thickness=2):
        r = Ripple(x, y, color, max_radius, duration_ms, thickness)
        self._ripples.append(r)
        return r

    # ----------------------------------------------------------- intensity
    def set_intensity(self, value):
        """Set the global animation-intensity multiplier (0.0-1.0). Ambient and
        persistent effects scale by this; at 0 the app reads as calm/static."""
        self.intensity = max(0.0, min(1.0, float(value)))

    def smooth(self, key, target, rate=0.2, snap=0.01, start=None):
        """Stateful exponential approach. Returns the value stored under `key`,
        eased a fraction `rate` toward `target` each call — the backbone for
        hover lifts, count-ups and sliding indicators. On first sight a key
        seeds to `start` (or to `target` when start is None)."""
        cur = self._smooth.get(key)
        if cur is None:
            cur = float(start) if start is not None else float(target)
        cur += (float(target) - cur) * rate
        if abs(float(target) - cur) <= snap:
            cur = float(target)
        self._smooth[key] = cur
        return cur

    def clear_smooth(self, prefix=None):
        """Drop stored smooth() state — all of it, or just keys starting with
        `prefix`. Use when a surface is torn down so values don't 'jump' the
        next time it appears."""
        if prefix is None:
            self._smooth.clear()
        else:
            for k in [k for k in self._smooth if str(k).startswith(prefix)]:
                self._smooth.pop(k, None)

    def tick(self):
        now_ms = time.monotonic() * 1000
        dt_ms  = (now_ms - self._last_tick) if self._last_tick else 16
        self._last_tick = now_ms

        for t in self._tweens:
            t.tick(now_ms)
        self._tweens = [t for t in self._tweens if not t.done]

        for ps in self._particles:
            ps.tick(now_ms, dt_ms)
        self._particles = [ps for ps in self._particles if not ps.finished]

        for r in self._ripples:
            r.tick(now_ms)
        self._ripples = [r for r in self._ripples if not r.done]

    @property
    def active_particles(self):
        return self._particles

    @property
    def active_ripples(self):
        return self._ripples

    @property
    def has_activity(self):
        return bool(self._tweens or self._particles or self._ripples)


# Singleton — import and use directly
anim = AnimationManager()
