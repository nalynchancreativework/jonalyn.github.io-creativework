#!/usr/bin/env python3
"""Word-level transcript of a talking-head clip -> words.json

    python transcribe.py RAW.mp4 words.json [--script script.txt] [--engine auto|whisper|sphinx]

Output: [{"i": 0, "w": "Okay", "s": 0.52, "e": 0.81}, ...]  (seconds, source timeline)

Engines
  whisper  faster-whisper (accurate, needs huggingface.co to download the model once)
  sphinx   pocketsphinx (model ships inside the pip package, works offline).
           With --script it force-aligns the known script (accurate timing as long
           as the speaker sticks to the script). Without a script it free-decodes,
           which gets timings right but many words wrong - fix the text by hand.
  auto     whisper, falling back to sphinx if the model can't be downloaded.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


def extract_wav(src, wav):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
                    "-ar", "16000", "-sample_fmt", "s16", wav], check=True)


def run_whisper(wav, model, script):
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    prompt = " ".join(script.split()[:150]) if script else None
    segs, _ = m.transcribe(wav, language="en", word_timestamps=True,
                           initial_prompt=prompt, condition_on_previous_text=False)
    out = []
    for seg in segs:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                out.append({"w": t, "s": round(w.start, 3), "e": round(w.end, 3)})
    return out


def _norm(tok):
    return re.sub(r"[^a-z']", "", tok.lower().replace("’", "'"))


def run_sphinx(wav, script):
    from pocketsphinx import Decoder
    with wave.open(wav, "rb") as f:
        audio = f.readframes(f.getnframes())
    fps = 100.0  # pocketsphinx frame rate

    if not script:
        d = Decoder(samprate=16000)
        d.start_utt()
        d.process_raw(audio, full_utt=True)
        d.end_utt()
        out = []
        for s in d.seg():
            w = re.sub(r"\(\d+\)$", "", s.word)
            if w.startswith("<") or w.startswith("[") or w in ("<sil>",):
                continue
            out.append({"w": w, "s": round(s.start_frame / fps, 3), "e": round((s.end_frame + 1) / fps, 3)})
        return out

    # Forced alignment of the known script.
    display = script.split()
    d = Decoder(samprate=16000, bestpath=False)
    keys, idx = [], []
    for i, tok in enumerate(display):
        k = _norm(tok)
        if k and d.lookup_word(k) is not None:
            keys.append(k)
            idx.append(i)
    if not keys:
        sys.exit("None of the script words are in the pocketsphinx dictionary.")
    d.set_align_text(" ".join(keys))
    d.start_utt(); d.process_raw(audio, full_utt=True); d.end_utt()
    d.set_alignment()
    d.start_utt(); d.process_raw(audio, full_utt=True); d.end_utt()
    aligned = [w for w in d.get_alignment()
               if not w.name.startswith("<") and w.name != "sil"]
    times = {}
    for j, w in enumerate(aligned[:len(idx)]):
        times[idx[j]] = (w.start / fps, (w.start + w.duration) / fps)

    # Words the dictionary doesn't know ($700k, SAHM, names) get squeezed into
    # the gap between their aligned neighbours.
    out = []
    i = 0
    n = len(display)
    while i < n:
        if i in times:
            s, e = times[i]
            out.append({"w": display[i], "s": round(s, 3), "e": round(e, 3)})
            i += 1
            continue
        j = i
        while j < n and j not in times:
            j += 1
        prev_e = out[-1]["e"] if out else 0.0
        next_s = times[j][0] if j < n else prev_e + 0.4 * (j - i)
        span = max(next_s - prev_e, 0.05 * (j - i))
        step = span / (j - i)
        for k in range(i, j):
            s = prev_e + (k - i) * step
            out.append({"w": display[k], "s": round(s, 3), "e": round(s + step, 3), "guess": True})
        i = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--script", help="text file with what was said (improves accuracy)")
    ap.add_argument("--engine", default="auto", choices=["auto", "whisper", "sphinx"])
    ap.add_argument("--model", default="small.en")
    a = ap.parse_args()

    script = Path(a.script).read_text() if a.script else None
    with tempfile.TemporaryDirectory() as td:
        wav = str(Path(td) / "a.wav")
        extract_wav(a.video, wav)
        words, engine = None, None
        if a.engine in ("auto", "whisper"):
            try:
                words, engine = run_whisper(wav, a.model, script), "whisper"
            except Exception as ex:  # usually: model download blocked
                if a.engine == "whisper":
                    raise
                print(f"whisper unavailable ({type(ex).__name__}: {str(ex)[:120]}), using pocketsphinx",
                      file=sys.stderr)
        if words is None:
            words = run_sphinx(wav, script)
            engine = "sphinx-align" if script else "sphinx-free"

    for i, w in enumerate(words):
        w["i"] = i
    words = [{"i": w["i"], **{k: v for k, v in w.items() if k != "i"}} for w in words]
    Path(a.out).write_text(json.dumps(words, indent=0, ensure_ascii=False))
    print(f"{len(words)} words via {engine} -> {a.out}")
    # Compact readable view for planning: index:word, with pause markers.
    line, last_e = [], None
    for w in words:
        if last_e is not None and w["s"] - last_e > 0.6:
            line.append(f"‖{w['s'] - last_e:.1f}s‖")
        line.append(f"{w['i']}:{w['w']}{'?' if w.get('guess') else ''}")
        last_e = w["e"]
    print(" ".join(line))


if __name__ == "__main__":
    main()
