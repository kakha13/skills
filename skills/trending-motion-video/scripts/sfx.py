"""Original synthesized sound effects (no samples, no copyright), stereo.

build(total, starts, names, word_times, cuts) layers:
  - a soft pop on every caption word, a swish on every scene start (kicker slide-in)
  - a whoosh into every cut
  - one named themed effect per scene (see LIBRARY), and a final boom+ding on the last word
"""
import numpy as np
from scipy.signal import butter, lfilter

SR = 44100
RNG = np.random.default_rng(42)


def _f(x, kind, fc, order=2):
    wn = np.atleast_1d(np.array(fc, float)) / (SR / 2)
    b, a = butter(order, wn if len(wn) > 1 else wn[0], kind)
    return lfilter(b, a, x)


def _t(sec):
    return np.arange(int(sec * SR)) / SR


def _noise(sec):
    return RNG.standard_normal(int(sec * SR))


def _sweep(f0, f1, sec, curve=1.0):
    t = _t(sec)
    return np.sin(2 * np.pi * np.cumsum(f0 + (f1 - f0) * (t / sec) ** curve) / SR)


def _st(mono, pan=0.0):
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    return np.stack([mono * l, mono * r], 1) * np.sqrt(2)


def _place(buf, sig, t0, pan=0.0, gain=1.0):
    a = int(t0 * SR)
    if a >= len(buf) or a < 0:
        return
    sig = _st(sig, pan) if sig.ndim == 1 else sig
    b = min(len(buf), a + len(sig))
    buf[a:b] += sig[:b - a] * gain


def _beep(freq, sec):
    t = _t(sec)
    return np.sin(2 * np.pi * freq * t) * np.clip(t / 0.005, 0, 1) * np.clip((sec - t) / 0.01, 0, 1)


def _canvas(sec):
    return np.zeros((int(sec * SR), 2))


# ---------- UI layer ----------
def pop(pitch=1.0):
    t = _t(0.07)
    return _sweep(1400 * pitch, 700 * pitch, 0.07) * np.exp(-t * 70) + _f(_noise(0.07), "high", 4000) * np.exp(-t * 200) * 0.3


def swish():
    t = _t(0.35)
    return _f(_noise(0.35), "band", [1500, 6000]) * np.sin(np.pi * t / 0.35) ** 3 * 0.5


def whoosh():
    """Moving band of noise, swelling into the cut (chunked time-varying lowpass)."""
    sec = 0.9
    L = int(sec * SR)
    noise = _noise(sec)
    cut = np.r_[np.linspace(400, 5000, L // 2), np.linspace(5000, 1200, L - L // 2)]
    out = np.concatenate([_f(noise[i:i + 2205], "low", cut[i]) for i in range(0, L, 2205)])[:L]
    return out * np.sin(np.pi * np.arange(L) / L) ** 2 * 0.6


# ---------- themed scene effects ----------
def telemetry():
    """Satellite/radio: chirps + static."""
    out = _canvas(2.2)
    for k, (f, d, p) in enumerate([(1800, .08, -.5), (2400, .05, .5), (1800, .08, -.5), (3000, .04, .3),
                                   (2200, .06, -.2), (2800, .05, .6)]):
        _place(out, _beep(f, d) * 0.5, 0.12 + k * 0.17, p)
    t = _t(2.2)
    _place(out, _f(_noise(2.2), "band", [2000, 5000]) * 0.06 * np.sin(np.pi * t / 2.2), 0)
    return out


def compute():
    """Chips/computers/AI: electric hum + digital bleeps."""
    sec = 3.2
    t = _t(sec)
    hum = np.sin(2 * np.pi * 60 * t) + 0.5 * np.sin(2 * np.pi * 120 * t) + 0.3 * np.sign(np.sin(2 * np.pi * 180 * t))
    out = _canvas(sec)
    _place(out, _f(hum, "low", 900) * np.clip(t / 0.6, 0, 1) * np.clip((sec - t) / 0.8, 0, 1) * 0.18, 0)
    for k in range(10):
        _place(out, _beep(RNG.choice([880, 1320, 1760, 2640, 3520]), 0.03) * 0.25,
               0.4 + k * 0.21 + RNG.random() * 0.05, RNG.uniform(-.8, .8))
    return out


def rocket():
    """Launch/engines/explosions: crackle + deep roar."""
    sec = 4.0
    t = _t(sec)
    env = np.clip(t / 1.2, 0, 1) ** 1.5 * np.clip((sec - t) / 1.5, 0, 1)
    rumble = np.sin(2 * np.pi * np.cumsum(28 + 6 * np.sin(2 * np.pi * 0.7 * t)) / SR) * 0.5
    crackle = _f(_noise(sec), "high", 2500) * (RNG.random(len(t)) > 0.996) * 2.0
    side = lambda: _f(_noise(sec), "low", 220, 4) * 3.0 + _f(_noise(sec), "band", [200, 900]) * 0.6
    return np.stack([(side() + crackle * 0.4 + rumble) * env, (side() + crackle * 0.2 + rumble) * env], 1) * 0.45


def sparkle():
    """Light/magic/reveal/success: rising bell chimes."""
    out = _canvas(2.6)
    for k, m in enumerate([72, 76, 79, 84, 88, 91]):
        f = 440 * 2 ** ((m + 12 - 69) / 12)
        t = _t(1.4)
        _place(out, (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t)) * np.exp(-t * 4) * 0.12,
               0.15 + k * 0.11, -0.6 + k * 0.24)
    return out


def alarm():
    """Danger/problem/heat/warning: sizzle + warning beeps."""
    sec = 3.0
    t = _t(sec)
    out = _canvas(sec)
    _place(out, _f(_noise(sec), "high", 3500) * (0.6 + 0.4 * RNG.random(len(t)))
           * np.clip(t / 0.8, 0, 1) * np.clip((sec - t) / 0.6, 0, 1) * 0.10, 0)
    for k in range(3):
        _place(out, (_beep(880, 0.16) + 0.5 * _beep(1760, 0.16)) * 0.22, 0.6 + k * 0.45)
    return out


def lasers():
    """Sci-fi/networks/connections: laser zaps bouncing L/R."""
    out = _canvas(2.4)
    for k in range(5):
        t = _t(0.22)
        z = _sweep(3200, 500, 0.22, 0.5) * np.exp(-t * 14)
        _place(out, (z + 0.4 * np.sign(z) * np.exp(-t * 30)) * 0.16, 0.25 + k * 0.33, -0.7 if k % 2 == 0 else 0.7)
    return out


def flyby():
    """Competition/speed/cars/race: doppler pass-bys panning across."""
    out = _canvas(3.0)
    for start, direction in [(0.2, 1), (1.0, -1), (1.7, 1)]:
        t = _t(1.0)
        x = t * 2 - 1
        mono = (np.sin(2 * np.pi * np.cumsum(420 - 160 * x) / SR) * 0.5 + _f(_noise(1.0), "band", [600, 4000])) \
            * np.exp(-(x * 2.2) ** 2) * 0.35
        pan = x * direction
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        _place(out, np.stack([mono * l, mono * r], 1) * np.sqrt(2), start)
    return out


def impact():
    """Big statement/stat/shock: sub boom + crash."""
    t = _t(2.2)
    boom = np.sin(2 * np.pi * np.cumsum(35 + 80 * np.exp(-t * 8)) / SR) * np.exp(-t * 2.4) * 0.7
    return _st(boom + _f(_noise(2.2), "high", 3500) * np.exp(-t * 3) * 0.15)


def glitch():
    """Hacks/bugs/deepfakes/errors: stuttering digital noise bursts."""
    out = _canvas(1.6)
    for k in range(7):
        sec = RNG.uniform(0.03, 0.09)
        burst = np.sign(np.sin(2 * np.pi * RNG.uniform(200, 1800) * _t(sec))) * 0.3 + _noise(sec) * 0.2
        _place(out, _f(burst, "band", [300, 6000]) * 0.4, 0.1 + k * 0.17 + RNG.random() * 0.05, RNG.uniform(-.7, .7))
    return out


def typing():
    """Messages/coding/news writing: keyboard clicks."""
    out = _canvas(2.4)
    tm = 0.1
    while tm < 2.2:
        t = _t(0.03)
        _place(out, _f(_noise(0.03), "band", [1500, 6000]) * np.exp(-t * 250) * 0.4, tm, RNG.uniform(-.3, .3))
        tm += RNG.uniform(0.06, 0.16)
    return out


def heartbeat():
    """Health/tension/suspense: low double thump."""
    out = _canvas(3.0)
    for k in range(3):
        for off, g in ((0, 1.0), (0.22, 0.7)):
            t = _t(0.25)
            _place(out, np.sin(2 * np.pi * 55 * t) * np.exp(-t * 18) * 0.6 * g, 0.2 + k * 0.9 + off)
    return out


def final_hit():
    t = _t(3.0)
    boom = np.sin(2 * np.pi * np.cumsum(32 + 70 * np.exp(-t * 7)) / SR) * np.exp(-t * 1.8) * 0.6
    tail = _f(_noise(3.0), "high", 5000) * np.exp(-t * 2.5) * 0.12
    ding = (np.sin(2 * np.pi * 1318.5 * t) + 0.3 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 2.2) * 0.18
    return np.stack([boom + tail + ding, boom + tail * 0.8 + ding], 1)


LIBRARY = {  # name -> (builder, offset into scene in seconds)
    "telemetry": (telemetry, 0.05), "compute": (compute, 0.0), "rocket": (rocket, 0.0),
    "sparkle": (sparkle, 0.35), "alarm": (alarm, 0.2), "lasers": (lasers, 0.3), "flyby": (flyby, 0.1),
    "impact": (impact, 0.0), "glitch": (glitch, 0.1), "typing": (typing, 0.1), "heartbeat": (heartbeat, 0.0),
}


def build(total, starts, names, word_times, cuts):
    out = np.zeros((int(total * SR), 2))
    for i, tm in enumerate(word_times):
        _place(out, pop(1.0 + 0.06 * (i % 3)), tm, pan=RNG.uniform(-0.25, 0.25), gain=0.22)
    for tm in starts:
        _place(out, swish(), tm, gain=0.35)
    for c in cuts:
        _place(out, whoosh(), c - 0.55, gain=0.5)
    for name, st in zip(names, starts):
        if name in LIBRARY:
            fn, off = LIBRARY[name]
            _place(out, fn(), st + off)
    if word_times:
        _place(out, final_hit(), word_times[-1])
    return out
