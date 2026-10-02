"""Original synthesized soundtrack: 100% generated here, no samples, no copyright, no attribution.

compose(total, drop, breakdown, lift, outro, bpm, mood) -> stereo float array in [-1, 1].
Arrangement: soft intro + riser -> drop (full beat) -> optional breakdown (beat mostly out) ->
optional lift (riser, impact, lead melody) -> outro (beat out, last chord rings).
"""
import numpy as np
from scipy.signal import butter, lfilter, fftconvolve

SR = 44100

# (bass midi, chord midi) per bar, plus a 2-note-per-bar lead melody
MOODS = {
    "epic": dict(prog=[(45, [57, 60, 64]), (41, [53, 57, 60]), (48, [60, 64, 67]), (43, [55, 59, 62])],
                 melody=[[76, 72], [77, 72], [79, 76], [74, 71]]),          # Am F C G - cinematic
    "uplifting": dict(prog=[(48, [60, 64, 67]), (43, [55, 59, 62]), (45, [57, 60, 64]), (41, [53, 57, 60])],
                      melody=[[79, 76], [79, 74], [76, 72], [77, 72]]),     # C G Am F - positive
    "dark": dict(prog=[(45, [57, 60, 64]), (45, [57, 60, 65]), (41, [53, 57, 60]), (40, [52, 56, 59])],
                 melody=[[76, 72], [77, 76], [72, 69], [71, 68]]),          # Am Am(b6) F E - tense
}


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _filt(x, kind, fc, order=2):
    wn = np.atleast_1d(np.array(fc, float)) / (SR / 2)
    b, a = butter(order, np.clip(wn, 1e-4, 0.999) if len(wn) > 1 else min(wn[0], 0.999), kind)
    return lfilter(b, a, x)


def saw(f, t, phase=0.0):
    return 2 * ((f * t + phase) % 1.0) - 1


def env_points(n, points, ramp=0.25):
    """Piecewise-constant levels [(time, level), ...] with smooth ramps; None times are skipped."""
    t = np.arange(n) / SR
    pts = [p for p in points if p[0] is not None]
    env = np.full(n, pts[0][1], float)
    for tm, lvl in pts[1:]:
        k = np.clip((t - tm) / ramp, 0, 1)
        env = env * (1 - k) + lvl * k
    return env


def place(buf, sig, t0):
    a = int(t0 * SR)
    if a >= len(buf):
        return
    if a < 0:
        sig, a = sig[-a:], 0
    b = min(len(buf), a + len(sig))
    buf[a:b] += sig[:b - a]


def compose(total, drop=None, breakdown=None, lift=None, outro=None, bpm=100, mood="epic", seed=13):
    rng = np.random.default_rng(seed)
    cfg = MOODS.get(mood, MOODS["epic"])
    prog, melody = cfg["prog"], cfg["melody"]
    beat = 60 / bpm
    bar = beat * 4
    n = int(total * SR)
    t = np.arange(n) / SR
    drop = drop if drop is not None else min(bar, total * 0.1)
    outro = outro if outro is not None else total - bar

    chord_at = lambda tm: prog[int(tm // bar) % 4]

    # pads: detuned saws, dark/bright filter crossfade by section
    pad = np.zeros(n)
    for bi in range(int(total / bar) + 1):
        a, b = int(bi * bar * SR), min(n, int(((bi + 1) * bar + 0.4) * SR))
        if a >= n:
            break
        tt = t[a:b] - bi * bar
        env = np.clip(tt / 0.5, 0, 1) * np.clip((bar + 0.4 - tt) / 0.6, 0, 1)
        chord = prog[bi % 4][1]
        for m in chord + [chord[0] - 12]:
            for det in (-0.12, 0.0, 0.12):
                pad[a:b] += saw(hz(m + det), tt, rng.random()) * env * 0.05
    bright = env_points(n, [(0, 0.0), (drop, 1.0), (breakdown, 0.0), (lift, 1.0), (outro, 0.3)], ramp=1.2)
    pad = _filt(pad, "low", 700) * (1 - bright) + _filt(pad, "low", 2600) * bright

    # bass: pulsing 8ths
    bass = np.zeros(n)
    L = int(beat / 2 * SR * 0.9)
    lt = np.arange(L) / SR
    benv = np.exp(-lt * 6) * np.clip(lt / 0.005, 0, 1)
    for k in range(int(total / (beat / 2))):
        tm = k * beat / 2
        f = hz(chord_at(tm)[0])
        place(bass, (np.sin(2 * np.pi * f * lt) * 0.8 + _filt(saw(f, lt), "low", 900) * 0.35) * benv, tm)

    # arp: 16th plucks + stereo delay
    arp = np.zeros(n)
    six = beat / 4
    pattern = [0, 1, 2, 3, 2, 1, 0, 2]
    L = int(six * SR * 1.6)
    lt = np.arange(L) / SR
    for k in range(int(total / six)):
        tm = k * six
        c = chord_at(tm)[1]
        f = hz([c[0] + 12, c[1] + 12, c[2] + 12, c[0] + 24][pattern[k % 8]])
        s = np.sin(2 * np.pi * f * lt)
        place(arp, (np.sign(s) * 0.5 + s * 0.5) * np.exp(-lt * 16) * 0.14, tm)
    arp = _filt(arp, "low", 3200)
    arpL, arpR = arp.copy(), arp.copy()
    for d, g, ch in [(3 * six, 0.38, arpL), (4 * six, 0.32, arpR), (6 * six, 0.18, arpL), (8 * six, 0.14, arpR)]:
        k = int(d * SR)
        ch[k:] += arp[:-k] * g

    # lead melody from the lift (or the back half) until the outro
    lead = np.zeros(n)
    half = beat * 2
    L = int(half * SR)
    lt = np.arange(L) / SR
    lead_from = lift if lift is not None else max(drop, total * 0.55)
    for k in range(int(lead_from / half), int(outro / half)):
        tm = k * half
        m = melody[int(tm // bar) % 4][k % 2]
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * lt) * np.clip(lt / 0.3, 0, 1)
        ph = np.cumsum(hz(m) * vib) / SR
        tone = np.sin(2 * np.pi * ph) * 0.7 + (2 * np.abs(2 * (ph % 1) - 1) - 1) * 0.3
        place(lead, tone * np.clip(lt / 0.05, 0, 1) * np.clip((half - lt) / 0.15, 0, 1) * 0.13, tm)
    lead = _filt(lead, "low", 4000)

    # drums
    kick, snare, hat = np.zeros(n), np.zeros(n), np.zeros(n)
    kt = np.arange(int(0.4 * SR)) / SR
    kick_s = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-kt * 28)) / SR) * np.exp(-kt * 7) + np.exp(-kt * 300) * 0.3
    st = np.arange(int(0.25 * SR)) / SR
    snare_s = _filt(rng.standard_normal(len(st)), "band", [1200, 7000]) * np.exp(-st * 18) * 0.7 \
        + np.sin(2 * np.pi * 190 * st) * np.exp(-st * 30) * 0.5
    HL = int(0.06 * SR)
    hat_s = _filt(rng.standard_normal(HL), "high", 7500) * np.exp(-np.arange(HL) / SR * 70)
    for k in range(int(total / beat)):
        tm = k * beat
        place(kick, kick_s, tm)
        if k % 2:
            place(snare, snare_s, tm)
        place(hat, hat_s * 0.5, tm + beat / 2)
        place(hat, hat_s * 0.25, tm)
    full = env_points(n, [(0, 0.0), (drop, 1.0), (breakdown, 0.0), (lift, 1.0), (outro, 0.0)], ramp=0.08)
    kick_lvl = env_points(n, [(0, 0.0), (drop, 1.0), (breakdown, 0.55), (lift, 1.0), (outro, 0.0)], ramp=0.08)
    kick *= kick_lvl
    snare *= full
    hat *= full

    pump = 1 - 0.45 * np.exp(-(t % beat) / 0.11) * kick_lvl  # sidechain feel
    pad *= pump
    bass *= pump * env_points(n, [(0, 0.35), (drop, 1.0), (breakdown, 0.6), (lift, 1.0), (outro, 0.0)], ramp=0.3)

    # risers into drop/lift + impacts
    fx = np.zeros(n)
    for hit in (drop, lift):
        if hit is None:
            continue
        rl = min(2 * bar, hit)
        if rl > 0.5:
            L = int(rl * SR)
            noise = rng.standard_normal(L)
            rise = np.linspace(0, 1, L) ** 2.5
            sweep = np.concatenate([_filt(noise[i:i + 4410], "low", 300 + 7000 * rise[i]) for i in range(0, L, 4410)])
            place(fx, sweep[:L] * rise * 0.35, hit - rl)
        it = np.arange(int(2.5 * SR)) / SR
        boom = np.sin(2 * np.pi * np.cumsum(30 + 60 * np.exp(-it * 6)) / SR) * np.exp(-it * 2.2) * 0.8
        place(fx, boom + _filt(rng.standard_normal(len(it)), "high", 4000) * np.exp(-it * 2.8) * 0.18, hit)
    fx += _filt(pad, "low", 1200) * env_points(n, [(0, 0.0), (outro, 0.6)], ramp=1.5)

    # mix + reverb
    arp_lvl = env_points(n, [(0, 0.7), (drop, 1.0), (breakdown, 0.8), (lift, 1.0), (outro, 0.7)], ramp=0.5)
    mono = pad + bass * 0.55 + kick * 0.75 + snare * 0.35 + hat * 0.35 + lead + fx
    stereo = np.stack([mono + arpL * arp_lvl, mono + arpR * arp_lvl], 1)
    irn = int(1.8 * SR)
    ir = rng.standard_normal((irn, 2)) * np.exp(-np.arange(irn) / SR * 3.5)[:, None]
    ir = np.stack([_filt(ir[:, c], "low", 6000) for c in range(2)], 1)
    ir /= np.sqrt((ir ** 2).sum(0))
    for c, a in enumerate((arpL, arpR)):
        send = pad * 0.5 + lead + snare * 0.3 + a * 0.4
        stereo[:, c] += fftconvolve(send, ir[:, c])[:n] * 0.5
    stereo *= (np.clip(t / 0.8, 0, 1) * np.clip((total - t) / 1.6, 0, 1))[:, None]
    stereo = np.tanh(stereo / np.max(np.abs(stereo)) * 1.6)
    return stereo / np.max(np.abs(stereo))


if __name__ == "__main__":  # quick listen: python3 music.py [mood]
    import sys, wave
    m = compose(30.0, drop=3.6, breakdown=15.0, lift=20.0, outro=26.0, mood=(sys.argv[1] if len(sys.argv) > 1 else "epic"))
    with wave.open("music_preview.wav", "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((m * 0.9 * 32767).astype(np.int16).tobytes())
    print("wrote music_preview.wav")
