#!/usr/bin/env python3
"""Join clips into one 9:16 source for render.py - for reels with little or no talking
(transformations, reveals, day-in-the-life, B-roll), or to join several takes.

    python assemble.py OUT.mp4 BEATS.json CLIP[:START-END][@SPEED] [CLIP ...] [--mute] [--beat 0.5]

  CLIP:3-12@2   use seconds 3-12 of CLIP, played at 2x speed
  --mute        replace the audio with silence (add a trending sound in Instagram instead)
  --beat        length of each timing marker in seconds

BEATS.json is written in the same format as transcribe.py's words.json, but every
"word" is an empty timing marker, so render.py can place headers/overlays by beat
index and `split_at` can force cuts at clip boundaries. Captions stay empty.
For talking clips, transcribe the assembled file instead of using the beats.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

W, H, FPS = 1080, 1920, 30


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def parse(spec):
    m = re.match(r"^(.*?)(?::([\d.]+)-([\d.]+))?(?:@([\d.]+))?$", spec)
    path, a, b, sp = m.groups()
    return Path(path), float(a) if a else None, float(b) if b else None, float(sp) if sp else 1.0


def atempo_chain(speed):
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("beats")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--mute", action="store_true")
    ap.add_argument("--beat", type=float, default=0.5)
    a = ap.parse_args()

    clips = [parse(c) for c in a.clips]
    tmp = Path(tempfile.mkdtemp(prefix="assemble-"))
    parts, lengths = [], []
    for n, (path, s, e, sp) in enumerate(clips):
        full = duration(path)
        s = s or 0.0
        e = min(e or full, full)
        out_len = (e - s) / sp
        part = tmp / f"p{n}.mov"
        vf = (f"trim=start={s}:end={e},setpts=(PTS-STARTPTS)/{sp},fps={FPS},"
              f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1")
        if a.mute:
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(path),
                   "-f", "lavfi", "-t", f"{out_len:.3f}", "-i", "anullsrc=r=48000:cl=mono",
                   "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
        else:
            af = (f"atrim=start={s}:end={e},asetpts=PTS-STARTPTS,{atempo_chain(sp)},"
                  "aformat=sample_rates=48000:channel_layouts=mono")
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(path),
                   "-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]", "-map", "[v]", "-map", "[a]"]
        cmd += ["-t", f"{out_len:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "15",
                "-c:a", "pcm_s16le", str(part)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stderr[-2000:])
        parts.append(part)
        lengths.append(duration(part))

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", a.out], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-2000:])

    beats, t0 = [], 0.0
    print(f"{a.out}: {sum(lengths):.1f}s")
    for n, L in enumerate(lengths):
        first = len(beats)
        k = 0
        while k * a.beat < L - 1e-6:
            s = t0 + k * a.beat
            e = min(t0 + (k + 1) * a.beat, t0 + L)
            beats.append({"i": len(beats), "w": "", "s": round(s, 3), "e": round(e, 3), "clip": n})
            k += 1
        print(f"  clip {n} {clips[n][0].name}: beats {first}-{len(beats) - 1}  "
              f"({t0:.1f}s-{t0 + L:.1f}s)")
        t0 += L
    Path(a.beats).write_text(json.dumps(beats, indent=0))
    print(f"split_at for clip boundaries: {[b['i'] for b in beats if b['i'] and b['clip'] != beats[b['i'] - 1]['clip']]}")


if __name__ == "__main__":
    main()
