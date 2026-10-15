#!/usr/bin/env python3
"""Render a finished reel from raw talking-head footage + an edit plan.

    python render.py plan.json            # full render
    python render.py plan.json --timeline # print kept words with output times, no render

The plan format is documented in ../reference/plan-format.md.
All word references in the plan are indices into words.json (source timeline);
this script works out where they land after the pauses/flubs are cut.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W, H, FPS = 1080, 1920, 30
SKILL = Path(__file__).resolve().parent.parent
FONTS = SKILL / "fonts"
CACHE = Path.home() / ".cache" / "reel-edit"

# --- Style constants (measured from the reference frames) --------------------
SERIF = "Instrument Serif"
HAND = "La Belle Aurore"
WHITE = "&H00FFFFFF"
CREAM = "&H00B4E6F3"         # #F3E6B4 in ASS BGR - highlight / side-note colour
SHADOW = "&H9E000000"        # soft, mostly transparent black

HEADER_STYLES = {
    #          font   size colour  default y   wrap width (fraction of frame)
    "title":   (SERIF, 158, WHITE, 0.150, 0.88),
    "section": (SERIF, 140, WHITE, 0.150, 0.88),
    "script":  (HAND,  100, WHITE, 0.175, 0.86),
    "sub":     (HAND,   90, WHITE, 0.268, 0.92),
    "note":    (HAND,   84, CREAM, 0.330, 0.36),
}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        sys.exit(f"command failed: {' '.join(map(str, cmd[:6]))} ...")
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type,width,height,color_transfer:format=duration",
               "-of", "json", str(path)])
    return json.loads(out)


# --- Cutting ------------------------------------------------------------------
def snap(t):
    return round(t * FPS) / FPS


def build_segments(words, drop, max_gap, pad, duration):
    dropped = set()
    for r in drop:
        a, b = (r, r) if isinstance(r, int) else (r[0], r[-1])
        dropped.update(range(a, b + 1))
    kept = [w for w in words if w["i"] not in dropped]
    if not kept:
        sys.exit("every word was dropped")
    segs, cur = [], [kept[0]]
    for prev, w in zip(kept, kept[1:]):
        contiguous = w["i"] == prev["i"] + 1
        if contiguous and w["s"] - prev["e"] <= max_gap:
            cur.append(w)
        else:
            segs.append(cur)
            cur = [w]
    segs.append(cur)

    out, t_out = [], 0.0
    for k, ws in enumerate(segs):
        a = max(0.0, ws[0]["s"] - pad)
        b = min(duration, ws[-1]["e"] + pad)
        if out and a < out[-1]["b"]:          # keep segments from overlapping
            a = out[-1]["b"]
        a, b = snap(a), snap(b)
        if b - a < 1.0 / FPS:
            b = a + 2.0 / FPS
        out.append({"a": a, "b": b, "o": t_out, "words": ws})
        t_out = round(t_out + (b - a), 6)
    return out, t_out


def word_times(segments):
    """word index -> (out_start, out_end, segment_end_out)"""
    m = {}
    for s in segments:
        seg_end = s["o"] + (s["b"] - s["a"])
        for w in s["words"]:
            st = s["o"] + max(0.0, w["s"] - s["a"])
            en = min(seg_end, s["o"] + (w["e"] - s["a"]))
            m[w["i"]] = (st, max(en, st + 0.05), seg_end)
    return m


def resolve(idx, times, side, total):
    """Map a word index from the plan to an output time, tolerating dropped words."""
    if idx == "end":
        return total
    if idx == "start":
        return 0.0
    keys = sorted(times)
    if idx in times:
        return times[idx][0] if side == "start" else times[idx][1]
    if side == "start":
        nxt = [k for k in keys if k > idx]
        return times[nxt[0]][0] if nxt else total
    prv = [k for k in keys if k < idx]
    return times[prv[-1]][1] if prv else 0.0


# --- Subtitles (ASS) ------------------------------------------------------------
def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def esc(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(plan, segments, times, total):
    cap = {"on": True, "x": 0.24, "y": 0.455, "size": 100, "highlight": [], **plan.get("captions", {})}
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{SERIF},{cap['size']},{WHITE},{WHITE},&H00000000,{SHADOW},0,0,0,0,100,100,0,0,1,0,2.2,5,0,0,0,1",
    ]
    for name, (font, size, col, _y, wrap) in HEADER_STYLES.items():
        margin = int(W * (1 - wrap) / 2)
        spacing = -1 if font == SERIF else 0
        lines.append(f"Style: {name},{font},{size},{col},{col},&H00000000,{SHADOW},0,0,0,0,100,100,"
                     f"{spacing},0,1,0,2.2,5,{margin},{margin},0,1")
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    # One word at a time, left of the face.
    if cap["on"]:
        hl = set(cap.get("highlight", []))
        cx, cy = int(W * cap["x"]), int(H * cap["y"])
        for s in segments:
            seg_end = s["o"] + (s["b"] - s["a"])
            # Group words so nothing flashes for less than ~0.15 s ("a sponge").
            groups, cur = [], []
            for w in s["words"]:
                if not w["w"].strip(" ,.!?;:\"“”"):
                    continue
                cur.append(w)
                if times[w["i"]][1] - times[cur[0]["i"]][0] >= 0.15:
                    groups.append(cur)
                    cur = []
            if cur:
                if groups and times[cur[-1]["i"]][1] - times[cur[0]["i"]][0] < 0.15:
                    groups[-1] += cur
                else:
                    groups.append(cur)
            for j, g in enumerate(groups):
                st = times[g[0]["i"]][0]
                end = times[groups[j + 1][0]["i"]][0] if j + 1 < len(groups) \
                    else min(seg_end, times[g[-1]["i"]][1] + 0.25)
                parts = []
                for w in g:
                    txt = esc(w["w"].strip(" ,.!?;:\"“”"))
                    parts.append(f"{{\\c{CREAM}}}{txt}{{\\c{WHITE}}}" if w["i"] in hl else txt)
                lines.append(f"Dialogue: 2,{ass_time(st)},{ass_time(end)},Cap,,0,0,0,,"
                             f"{{\\pos({cx},{cy})\\fad(40,0)}}{' '.join(parts)}")

    # Headers: titles, handwritten context lines, side notes.
    for h in plan.get("headers", []):
        style = h.get("style", "script")
        _f, size, col, dy, _w = HEADER_STYLES[style]
        st = resolve(h.get("from", "start"), times, "start", total)
        en = resolve(h.get("to", "end"), times, "end", total)
        if en <= st:
            continue
        x = int(W * h.get("x", 0.5))
        y = int(H * h.get("y", dy))
        tags = f"\\pos({x},{y})\\fad({h.get('fade_in', 120)},{h.get('fade_out', 0)})"
        if "size" in h:
            tags += f"\\fs{h['size']}"
        if "rotate" in h or style == "note":
            tags += f"\\frz{h.get('rotate', 8)}"
        if h.get("color") == "cream":
            tags += f"\\c{CREAM}"
        lines.append(f"Dialogue: 1,{ass_time(st)},{ass_time(en)},{style},,0,0,0,,{{{tags}}}{esc(h['text'])}")
    return "\n".join(lines) + "\n"


# --- Overlays -------------------------------------------------------------------
def emoji_png(chars, count, size_px, path):
    from PIL import Image, ImageDraw, ImageFont
    font_path = CACHE / "NotoColorEmoji.ttf"
    if not font_path.exists():
        sys.exit("emoji font missing - run scripts/setup.sh")
    f = ImageFont.truetype(str(font_path), 109, layout_engine=ImageFont.Layout.RAQM)
    one = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(one).text((10, 10), chars, font=f, embedded_color=True)
    one = one.crop(one.getbbox())
    scale = size_px / max(one.size)
    one = one.resize((max(1, int(one.width * scale)), max(1, int(one.height * scale))), Image.LANCZOS)
    gap = int(size_px * 0.12)
    img = Image.new("RGBA", (one.width * count + gap * (count - 1), one.height), (0, 0, 0, 0))
    for k in range(count):
        img.alpha_composite(one, (k * (one.width + gap), 0))
    img.save(path)


def pop_frames(src_png, width_px, out_dir, card):
    """Pre-render the pop-in: 7 frames scaling 0.6 -> 1.06 -> 1.0 on a fixed canvas."""
    from PIL import Image, ImageFilter
    im = Image.open(src_png).convert("RGBA")
    if width_px:
        im = im.resize((int(width_px), max(1, int(im.height * width_px / im.width))), Image.LANCZOS)
    if card:  # soft drop shadow behind screenshots, like a pasted card
        pad = 30
        sh = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
        block = Image.new("RGBA", im.size, (0, 0, 0, 90))
        sh.alpha_composite(block, (pad, pad + 8))
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        sh.alpha_composite(im, (pad, pad))
        im = sh
    cw, ch = int(im.width * 1.08) // 2 * 2 + 2, int(im.height * 1.08) // 2 * 2 + 2
    scales = [0.6, 0.78, 0.92, 1.03, 1.06, 1.02, 1.0]
    out_dir.mkdir(parents=True, exist_ok=True)
    for k, s in enumerate(scales):
        fr = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        r = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        if k < 2:
            r.putalpha(r.getchannel("A").point(lambda v, k=k: int(v * (0.5 + 0.25 * k))))
        fr.alpha_composite(r, ((cw - r.width) // 2, (ch - r.height) // 2))
        fr.save(out_dir / f"{k:02d}.png")
    return cw, ch


# --- Main -------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--timeline", action="store_true")
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    plan_path = Path(a.plan).resolve()
    base = plan_path.parent
    plan = json.loads(plan_path.read_text())
    P = lambda p: (base / p).resolve() if not Path(p).is_absolute() else Path(p)

    src = P(plan["source"])
    words = json.loads(P(plan["words"]).read_text())
    info = probe(src)
    duration = float(info["format"]["duration"])
    vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
    cut = {"max_gap": 0.30, "pad": 0.07, **plan.get("cut", {})}
    segments, total = build_segments(words, plan.get("drop", []), cut["max_gap"], cut["pad"], duration)
    times = word_times(segments)

    if a.timeline:
        print(f"source {duration:.1f}s -> output {total:.1f}s, {len(segments)} cuts")
        for n, s in enumerate(segments):
            ws = " ".join(f"{w['i']}:{w['w']}" for w in s["words"])
            print(f"[{n}] {s['o']:6.2f}s  {ws}")
        return

    out = P(plan.get("output", "reel.mp4"))
    tmp = Path(tempfile.mkdtemp(prefix="reel-"))
    try:
        # Pass 1: cut, reframe to 9:16, alternate punch-ins, hard cuts.
        pi = {"zooms": [1.0, 1.12], "focus_y": 0.35, "emphasis": [], **plan.get("punch_in", {})}
        emph = set(pi["emphasis"])
        hdr = vstream.get("color_transfer") in ("arib-std-b67", "smpte2084")
        pre = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
               "zscale=t=bt709:m=bt709:r=tv,format=yuv420p," if hdr else "")
        fc = [f"[0:v]{pre}fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},setsar=1,split={len(segments)}" + "".join(f"[s{k}]" for k in range(len(segments))),
              f"[0:a]aformat=sample_rates=48000:channel_layouts=mono,asplit={len(segments)}"
              + "".join(f"[r{k}]" for k in range(len(segments)))]
        for k, s in enumerate(segments):
            z = pi["zooms"][k % len(pi["zooms"])]
            if any(w["i"] in emph for w in s["words"]):
                z = max(z, 1.22)
            d = s["b"] - s["a"]
            zw, zh = int(W * z) // 2 * 2, int(H * z) // 2 * 2
            fc.append(f"[s{k}]trim=start={s['a']:.4f}:end={s['b']:.4f},setpts=PTS-STARTPTS,"
                      f"scale={zw}:{zh},crop={W}:{H}:(iw-{W})/2:(ih-{H})*{pi['focus_y']},setsar=1[v{k}]")
            fc.append(f"[r{k}]atrim=start={s['a']:.4f}:end={s['b']:.4f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.012):.4f}:d=0.012[a{k}]")
        fc.append("".join(f"[v{k}][a{k}]" for k in range(len(segments)))
                  + f"concat=n={len(segments)}:v=1:a=1[v][a]")
        cut_mp4 = tmp / "cut.mp4"
        (tmp / "cut.txt").write_text(";\n".join(fc))
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex_script", str(tmp / "cut.txt"),
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-c:a", "pcm_s16le", "-f", "mov", str(cut_mp4)])

        # Pass 2: overlays (cards, memes, emoji), text, audio polish.
        ass = tmp / "text.ass"
        ass.write_text(build_ass(plan, segments, times, total), encoding="utf-8")
        inputs = ["-i", str(cut_mp4)]
        fc = []
        last = "[0:v]"
        audio_mix = ["[0:a]"]
        n_in = 1
        for k, ov in enumerate(plan.get("overlays", [])):
            st = resolve(ov.get("at", "start"), times, "start", total) - 0.03
            st = max(0.0, st)
            en = resolve(ov["to"], times, "end", total) if "to" in ov else st + ov.get("dur", 1.3)
            en = min(en, total)
            dur = max(0.2, en - st)
            kind = ov.get("type", "image")
            cx, cy = W * ov.get("x", 0.5), H * ov.get("y", 0.62)
            if kind in ("image", "emoji"):
                if kind == "emoji":
                    png = tmp / f"emoji{k}.png"
                    emoji_png(ov["emoji"], ov.get("count", 1), int(W * ov.get("size", 0.11)), png)
                    width = None
                else:
                    png = P(ov["file"])
                    width = W * ov.get("w", 0.62)
                if ov.get("full"):
                    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
                    fc.append(f"[{n_in}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                              f"format=yuva420p,setpts=PTS-STARTPTS+{st:.3f}/TB[o{k}]")
                    x, y = "0", "0"
                else:
                    cw, ch = pop_frames(png, width, tmp / f"pop{k}", ov.get("card", kind == "image"))
                    hold = max(0.0, dur - 7 / FPS)
                    inputs += ["-framerate", str(FPS), "-i", str(tmp / f"pop{k}" / "%02d.png")]
                    fc.append(f"[{n_in}:v]format=rgba,tpad=stop_mode=clone:stop_duration={hold:.3f},"
                              f"fade=t=out:st={max(0, dur - 0.08):.3f}:d=0.08:alpha=1,"
                              f"setpts=PTS-STARTPTS+{st:.3f}/TB[o{k}]")
                    x, y = f"{int(cx - cw / 2)}", f"{int(cy - ch / 2)}"
            elif kind == "video":
                inputs += ["-t", f"{dur:.3f}", "-i", str(P(ov["file"]))]
                wpx = int(W * ov.get("w", 0.7)) // 2 * 2
                fc.append(f"[{n_in}:v]fps={FPS},scale={wpx}:-2,format=yuva420p,"
                          f"fade=t=in:d=0.06:alpha=1,setpts=PTS-STARTPTS+{st:.3f}/TB[o{k}]")
                x, y = f"{int(cx)}-w/2", f"{int(cy)}-h/2"
                if ov.get("audio"):
                    ms = int(st * 1000)
                    fc.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=mono,"
                              f"volume={ov.get('volume', 0.8)},adelay={ms}:all=1[oa{k}]")
                    audio_mix.append(f"[oa{k}]")
            else:
                sys.exit(f"unknown overlay type {kind}")
            fc.append(f"{last}[o{k}]overlay=x={x}:y={y}:eof_action=pass:"
                      f"enable='between(t,{st:.3f},{en:.3f})'[b{k}]")
            last = f"[b{k}]"
            n_in += 1

        fonts = str(FONTS).replace(":", "\\:")
        assp = str(ass).replace(":", "\\:")
        fc.append(f"{last}ass='{assp}':fontsdir='{fonts}',format=yuv420p[vout]")

        music = plan.get("music")
        if music:
            inputs += ["-stream_loop", "-1", "-i", str(P(music["file"]))]
            fc.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=mono,"
                      f"volume={music.get('volume', 0.08)},atrim=0:{total:.3f}[mus]")
            audio_mix.append("[mus]")
            n_in += 1
        if len(audio_mix) > 1:
            fc.append("".join(audio_mix) + f"amix=inputs={len(audio_mix)}:duration=first:normalize=0[mix]")
            amix = "[mix]"
        else:
            amix = "[0:a]"
        fc.append(f"{amix}highpass=f=70,loudnorm=I=-14:TP=-1.5:LRA=11,aformat=sample_rates=48000[aout]")

        (tmp / "final.txt").write_text(";\n".join(fc))
        out.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex_script", str(tmp / "final.txt"),
             "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out)])
        print(f"rendered {out}  ({total:.1f}s, {len(segments)} cuts, from {duration:.1f}s raw)")
    finally:
        if a.keep_temp:
            print(f"temp kept at {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
