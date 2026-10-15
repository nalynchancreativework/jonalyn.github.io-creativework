---
name: talking-head-reel-edit
description: Make finished Instagram Reels / TikToks from Jonalyn's raw talking-to-camera footage in the @the.jessicacarter editing style - one-word serif captions beside the face, big serif title + handwritten notes at the top, hard jump cuts with punch-ins, pop-in screenshot cards, emoji stickers and meme clips on key words, natural colour. Claude does the editing itself (ffmpeg pipeline in scripts/); also use it to write scripts for these reels or review a plan. Trigger on "make/edit my reel", "edit this video", "in my style", "like Jessica's", or an uploaded raw video.
---

# Talking-head reels in the Jessica Carter style

**Claude makes the video.** Jonalyn uploads raw footage (and optional
screenshots, meme clips or music). Claude writes an edit plan, renders the
reel with `scripts/render.py` and sends back the finished MP4. She doesn't
open any editing app.

## The look (taken from 10 reference frames of her "$700k launch" reel)

| Element | What she does | Pipeline default |
|---|---|---|
| **Footage** | Natural home setting with warm daylight. She talks to camera, framed from the head to the waist, holding a small wireless mic. No filter or colour grade. | Kept as shot (HDR is tone-mapped to SDR) |
| **Cuts** | Hard jump cuts with every pause removed. The framing changes between cuts (punch-ins). | Pauses over 0.30 s are cut. Zoom alternates 1.00× and 1.12× per cut, and emphasis words get 1.22×. |
| **Captions** | **One word at a time** in a high-contrast **serif**, white with a soft shadow. They sit **left of her face** at about mid-height, never at the bottom. Emphasis words are **cream/yellow** (e.g. "watching", "sponge", "successful"). | Instrument Serif 125 px, centred at x 24%, y 45.5%. Highlights are #F3E6B4. Words shorter than 0.15 s are paired with the next word. |
| **Hook title** | A big serif headline over 2 lines at the top ("Spilling the tea on my $700k launch 👀"), with a **handwritten subtitle** under it. A **handwritten side note** in cream, tilted, sits at the left ("(as a SAHM to 3 boys)"). | `title` Instrument Serif 198 px at y 19% · `sub` Patrick Hand 118 px at y 31% · `note` Kalam 100 px, cream, rotated 8°, at y 40% |
| **Context lines** | Handwritten white text over 2 lines at the top that sums up the current point ("Hindsight is 20/20 and I have a LOT to share!"). It changes every few sentences. | `script` Patrick Hand 130 px at y 19% |
| **Section headers** | Serif numbered heading plus a handwritten subtitle ("1. Live workshop / Let's unpack this thing chronologically"). | `section` 175 px at y 16.5% + `sub` below it |
| **Proof cards** | Screenshots of real results (revenue dashboard, sales table) pop in over her chest, about 60% of the frame width, while she talks about them. | `image` overlay with a pop animation and soft card shadow, w 0.6, y 0.62 |
| **Word stickers** | Literal visuals of what she says. For "sponge" she shows 3 sponges in a row at the top. | `emoji` overlay with a `count` option |
| **Reaction memes** | A short meme clip on hype moments ("LETS GOOOO"), about 70% width, centred low. | `video` overlay, muted by default |
| **Collage cutaway** | Her cut-out over a collage of screenshots. | Not supported yet (needs background removal). Use a full-screen `image` cutaway (`"full": true`) instead. |

Rhythm: the top text changes with each idea, and something new appears
every 2–4 seconds (a card, sticker, meme, new header or zoom). Captions
never stop.

## Workflow (Claude follows this)

1. **Setup (once per session, about 1 min):** `bash scripts/setup.sh`. It prints
   the Python path to use (`~/.cache/reel-edit/venv/bin/python`) and says which
   transcriber is available.
2. **Get the inputs.** Find the raw video among the uploaded files (Claude
   Code: the uploads folder; claude.ai chat: the attached files). If there are
   several clips, join them first:
   `ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -crf 16 -c:a aac raw.mp4`
   (or use `scripts/assemble.py`, which normalises them). Ask for the script she read,
   or use the one Claude wrote for her. Also ask for any screenshots, meme
   clips or music she wants included.
3. **Transcribe:** `python scripts/transcribe.py raw.mp4 words.json --script script.txt`.
   It prints `index:word` with `‖1.4s‖` pause markers. That index is what the
   plan refers to.
   - If huggingface.co is reachable, Whisper is used (most accurate).
     Otherwise pocketsphinx **force-aligns the script**, which gives accurate
     timing as long as she said roughly what's written. Words marked `?` were
     not in its dictionary and have estimated timing.
   - Without a script and without Whisper, the text is unreliable. Ask her to
     paste what she said.
4. **Write `plan.json`** next to the files. See `reference/plan-format.md` for
   the full format. Decide:
   - **drop:** retakes, flubs, "um"s, repeated sentences and dead lines.
     Keep only the best take of each line.
   - **captions.highlight:** 1 emphasis word per sentence.
   - **headers:** the hook title + sub (+ note) for the first line, then a
     `script` context line or a `section` header for each new idea. Write them
     as short summaries in her voice, not word-for-word transcripts.
   - **overlays:** a proof card whenever she mentions a result she has a
     screenshot for, an emoji sticker on objects or emotions you can picture,
     and a meme on hype moments. Aim for one visual every 2–4 s.
   - **punch_in.emphasis:** words that get the extra-tight zoom.
5. **Check the timeline:** `python scripts/render.py plan.json --timeline` shows
   the kept words with their output times and the final length.
6. **Render:** `python scripts/render.py plan.json`. A 60 s reel takes about a
   minute.
7. **Check it yourself before sending.** Build a contact sheet and look at it:
   `ffmpeg -i out.mp4 -vf "fps=1,scale=270:-2,tile=6x5" -frames:v 1 sheet.png`.
   Check that text doesn't overlap, that her face is never covered, and that
   nothing sits in the bottom 25% or the right 15% (Instagram's UI covers
   those). Fix the plan and re-render.
8. **Deliver:** in Claude Code, send the MP4 with SendUserFile. In the
   claude.ai chat app, save it to the outputs folder so it shows as a
   download. Include a suggested post caption and cover frame time. Never
   commit videos, footage or screenshots to the repository, because it's a
   public site.

## No-talking reels (hair/outfit reveals, transformations, day-in-the-life)
No speech means no captions. The story is told with text and graphics instead.
1. Join and speed-ramp the clips:
   `python scripts/assemble.py raw.mp4 beats.json "clip1.MOV@2" "clip2.MOV@1.5" "reveal.MOV" --mute`.
   Speed up the process parts (2×) and keep the reveal at 1×. Use `--mute`
   and tell her to add a trending sound in Instagram, which is free and helps
   reach. It prints beat indices per clip (0.5 s markers) and the `split_at`
   values for clip boundaries.
2. In the plan, set `"words": "beats.json"`, `"captions": {"on": false}`,
   `"cut": {"pad": 0}` and `"split_at"` (clip boundaries plus a mid-clip split
   or two, so the zoom changes every 3–4 s). Set `"glow": true` when text sits
   on busy or light backgrounds.
3. Story arc: a hook title ("Part 2: *the reveal*" + 👀) → numbered steps over
   the process → an emoji row (✨✨✨) on the reveal frame → "The *after*" →
   a detail callout (note + arrow) → a CTA ("rate it 1–10 in the comments").

## Brand colours (Jonalyn's choice)
Titles and section headers are **blush pink #F7C1C4** by default. Set
`"accent"` in the plan to override it (a hex code, or `"white"`). Handwritten
lines stay white, and highlights and notes stay cream. Keep `"glow": true`
so the pastel title reads on light walls.

## Mixing text styles and graphics
- Inside any header text: `*italic*` (serif italic), `==cream highlight==`,
  `~handwritten~`, and `\n` for a line break. Mix a serif title with an
  italic phrase, e.g. "Step 1: *the chop*".
- `label` style: dark text in a white box, for facts and stats (like her
  date pill).
- `graphic` overlays (drawn, pop in like stickers): `arrow`, `circle`,
  `underline`, `sparkle`, `heart`, in white, cream or dark, with `size`,
  `rotate` and `flip`. Point arrows at the detail being talked about and
  circle the number on a proof card.
- Use 2–3 text styles per screen at most: a serif header, a handwritten line
  and an optional cream note.

## Background music
Never bake a copyrighted song into the file: Instagram can mute or block the
reel, and the reel won't be linked to the song's audio page. Export the reel
silent (`--mute`) or with her own voice. Then help her pick the music:
- Search the web for this week's trending Instagram Reels audio that fits the
  mood (reveals and transformations need a clear beat drop). Suggest 3–5
  songs with sources, and tell her to look for the ↗ trending arrow in the app.
- Tell her the exact second the drop should land (the reveal, e.g. 0:12).
  In Instagram: tap + → Reel → pick the video → music note → choose the song →
  drag the song's start so the drop hits that second.
- If songs are missing, it's a business-account music limit. Switching to a
  Creator account (Settings → Account type) is free.

## Layout rules
- The **face is sacred.** Overlays go over the chest/torso (y 0.55–0.70) or
  the top band. Stickers go beside the head (x 0.75–0.8) or in the top band.
- The **top band** (y 0.10–0.35) holds one thing at a time: a header *or* an
  emoji row. If a sticker needs the top band, end the header first, or put
  the sticker beside the head.
- **Bottom 25%** is never used, because the username, caption and buttons
  sit there.
- Keep captions on the left. If she stands left of centre in the footage,
  set `captions.x` to 0.76 to put them on the right instead.

## Writing scripts for these reels
Use this structure:

1. **Hook (0–3 s):** a claim plus curiosity, e.g. "Spilling the tea on my
   $700k launch". This line becomes the title.
2. **Credibility/context:** who she is, as a side note.
3. **2–4 numbered points**, each of which gets a `section` header.
4. **CTA:** comment a keyword, save the reel or follow for part 2.

Mark planned visuals inline so she knows what to prepare. For example, mark
`[CARD: Stripe screenshot]`, `[EMOJI: 🧽 x3]` and `[MEME: lets go]` on the
exact word. For cleaner, cheaper edits, tell her to record in **SDR** (iPhone:
Settings → Camera → Formats → turn off HDR Video). Ask her to leave a
1-second pause before redoing a line, so the retake is easy to drop.

## Honest limits
- Without huggingface.co access, the transcript must come from a script
  (forced alignment). To allow it, add `huggingface.co` under the
  environment's Network access → Allowed domains.
- Background removal and collage cutouts are not supported.
- Copyrighted meme clips (movie scenes) carry some risk on a business
  account. Prefer her own clips, or clips she has rights to. Instagram's
  in-app GIF stickers can be added after upload.
- Fonts are free and OFL: Instrument Serif for titles, plus Patrick Hand and
  Kalam for handwriting. Jonalyn picked the handwriting fonts over thin script
  look-alikes because they're easier to read, and wanted everything 25% larger
  than Jessica's proportions. Never go below these sizes. Keep handwritten
  lines short (one or two lines) so they stay big.
