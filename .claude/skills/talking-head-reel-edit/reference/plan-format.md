# plan.json format

Paths are relative to the plan file. **Word references** (`from`, `to`, `at`,
`highlight`, `drop`, `emphasis`) are indices from `words.json`, as printed
by `transcribe.py`. They refer to the raw footage, and the renderer works
out where each word lands after cutting. If a referenced word was dropped,
the nearest kept word is used. `"start"` and `"end"` are also accepted for
`from`/`to`/`at`.

```json
{
  "source": "raw.mp4",
  "words": "words.json",
  "output": "out/reel.mp4",

  "cut":      {"max_gap": 0.30, "pad": 0.07},
  "drop":     [[12, 18], 40],
  "punch_in": {"zooms": [1.0, 1.12], "focus_y": 0.35, "emphasis": [33]},
  "captions": {"highlight": [10, 19, 33], "x": 0.24, "y": 0.455, "size": 100, "on": true},

  "headers": [
    {"style": "title",   "text": "Spilling the tea on my $700k launch", "from": "start", "to": 15},
    {"style": "sub",     "text": "my first real digital product launch", "from": "start", "to": 15},
    {"style": "note",    "text": "(as a SAHM to 3 boys)", "x": 0.22, "from": 2, "to": 15},
    {"style": "script",  "text": "Hindsight is 20/20 and I have a LOT to share!", "from": 16, "to": 25},
    {"style": "section", "text": "1. Live workshop", "from": 29, "to": 60},
    {"style": "sub",     "text": "Let's unpack this thing chronologically", "y": 0.21, "from": 29, "to": 60}
  ],

  "overlays": [
    {"type": "image", "file": "revenue.png", "at": 12, "to": 15, "w": 0.6, "y": 0.62},
    {"type": "emoji", "emoji": "🧽", "count": 3, "at": 19, "dur": 1.2, "y": 0.155, "size": 0.09},
    {"type": "emoji", "emoji": "💸", "at": 33, "dur": 1.0, "x": 0.78, "y": 0.42, "size": 0.14},
    {"type": "video", "file": "letsgo.mp4", "at": 34, "to": 36, "w": 0.7, "y": 0.6, "audio": false},
    {"type": "image", "file": "collage.png", "full": true, "at": 41, "dur": 2.0}
  ],

  "music": {"file": "bed.mp3", "volume": 0.08}
}
```

## Fields

| Field | Meaning |
|---|---|
| `cut.max_gap` | A pause longer than this (in seconds) between kept words becomes a jump cut. Use 0.30 for punchy pacing and 0.45 for calmer pacing. |
| `cut.pad` | Breathing room kept before and after each run of words. |
| `drop` | Word ranges to remove (inclusive), such as flubs, retakes, "um"s or weak lines. A single int drops one word. |
| `punch_in.zooms` | A zoom cycle applied per cut, so consecutive clips differ in framing. |
| `punch_in.focus_y` | 0 keeps the top of the frame when zooming and 1 keeps the bottom. 0.35 keeps the face in shot. |
| `punch_in.emphasis` | A cut containing one of these words gets a tight 1.22× zoom. |
| `captions.highlight` | Words shown in cream instead of white, about 1 per sentence. |
| `captions.x/y` | Centre of the caption, as a fraction of the frame. |
| `headers[].style` | `title` = big serif hook · `section` = numbered serif heading · `script` = handwritten context line · `sub` = handwritten subtitle under a title or section · `note` = cream, tilted side note. |
| `headers[]` options | `x`, `y` (centre, as a fraction), `size` (px), `rotate` (deg), `color: "cream"`, `fade_in`/`fade_out` (ms). |
| `overlays[].type` | `image` = PNG/JPG screenshot (pops in with a card shadow; `"card": false` turns the shadow off) · `emoji` = colour emoji sticker (`count` repeats it in a row; `size` is the width fraction per emoji) · `video` = meme/B-roll clip (`audio: true` mixes in its sound at `volume`). |
| `overlays[]` timing | Starts at word `at`. Ends at the end of word `to`, or after `dur` seconds (default 1.3). |
| `overlays[]` position | `x`, `y` = centre of the overlay as a fraction of the frame; `w` = width fraction (image/video). `full: true` fills the whole frame (cutaway). |
| `music` | Looped under the voice. Keep `volume` between 0.05 and 0.10. |

Output: 1080×1920, 30 fps, H.264 + AAC, loudness normalised to -14 LUFS.
That's ready to upload to Instagram or TikTok.
