# The Last Light on Rowan Street — Storyboard & Technique Map

**Runtime** 2:19 (139.7s) · **262 words** · **112.5 gross WPM** (intimate/documentary band)
**Voice** `en-GB-RyanNeural` · `--rate="-25%"` · `--pitch="-5Hz"`

Every beat below is annotated with the researched technique it implements, so
the script can be audited against the skill's reference modules rather than taken
on faith.

---

## Why the rate is `-25%`, not the skill's default `-15%`

The `voice-booth` skill documents `-15%` as the storytelling default.
Measured against this script that produced **127.5 gross WPM** — the *explainer*
band. The research target for intimate documentary narration is **100–115 WPM**.

| Rate | Duration | Gross WPM | Band |
|---|---|---|---|
| `-15%` | 123.2s | 127.5 | Explainer (too brisk) |
| `-20%` | 130.9s | 120.1 | Still high |
| **`-25%`** | **139.7s** | **112.5** | **Intimate / documentary** |

The slower rate is only safe because every sentence is 8–16 words. Grok's report
warns that a slow rate *plus* clause-heavy sentences reads as sedated; short
sentences are what buy the headroom.

---

## Beat map

| Time | Line | Technique |
|---|---|---|
| 0:00 | "At three in the morning, one window on Rowan Street was still burning." | **Cold open / in medias res.** Concrete specific detail. No preamble, no title restatement. |
| 0:06 | "It had been burning for nine years." | **Curiosity gap** (Loewenstein). Opens **macro loop A: why?** |
| 0:10 | "Nobody knew why... and tonight, for the first time, it went dark." | **Stakes + anomaly.** The status quo breaks — this is the inciting change, landed by 10s. |
| 0:17 | "Maya walked that street home from the hospital every night." | Character introduced with **capability** (nurse) and **relationship** to the anomaly. |
| 0:24 | "She noticed the things that stopped." | Competence signal — earns her the right to act. |
| 0:28 | "So she crossed the road, and she knocked." | **Therefore-chaining.** Character becomes **active** at 20% of runtime. Opens **loop B**. |
| 0:32 | "Nobody answered. / She knocked again... harder. / The rain began." | **Try-fail 1 — "No, and…"** It fails, *and* conditions worsen. **Re-hook @ 25%.** |
| 0:43 | "Then a lock turned." | Reversal of the failure; short sentence as a beat change. |
| 0:52 | "He would not talk about the lamp." | **Try-fail 2 — "Yes, but…"** She gets the door, but not the answer. |
| 0:58 | "The house sells in the morning." | **Ticking clock (loop D).** Converts curiosity into urgency. **Signposts the deadline, conceals the cause.** |
| 1:01 | "Maya stood there... soaked, and foolish, and certain." | **Tricolon.** Deliberate **slow beat** before the climax so the fast beats land. |
| 1:11 | "And the one thing on that street that never went dark." | Plants the clue the ending will reinterpret — required for an **earned reveal**. |
| 1:16 | "Tomas had a son. The son left after a bad winter." | **Reveal — closes loop C.** **Re-hook @ ~54%.** |
| 1:26 | "Always. / Nine years. / Nobody came." | **One-word and two-word sentences** reserved for the strongest discovery. End-focus. |
| 1:33 | "So I am finished," he said, and he reached for the door. | Lowest point. Full form instead of a contraction, used as a hammer. |
| 1:38 | "But Maya put her hand out." | **But-chaining** — the pivot. |
| 1:41 | "He is not the only one who saw it." | **Contradiction re-hook @ 72%** — replaces the viewer's model of the story. |
| 1:45 | "She told him… / She told him…" | **Anaphora.** Rising delivery into the payoff. |
| 1:55 | "You have passed a light like that. You just never knocked." | **Direct address + relatability.** The share trigger — names a precise private feeling. |
| 2:02 | "…and he switched it on." | **Payoff.** Pays loop A's promise through a character *choice*, not coincidence. |
| 2:07 | "The house sold anyway." | Refuses the cheap win — the cost stands, so the ending is earned. |
| 2:10 | "But on Rowan Street, there is still one light at three in the morning. / It is only in a different window now." | **Emotional button + reinterpretation loop seam.** Echoes the opening line with changed meaning, making the first 10 seconds worth replaying. |

**Loop ledger**

```text
A  why is the window lit?    OPEN 0:06  PROGRESS 1:11  CLOSE 2:02
B  will Maya get an answer?  OPEN 0:28  PROGRESS 0:43, 0:52  CLOSE 1:41
C  who was the lamp for?     OPEN 0:52  CLOSE 1:16
D  the house sells at dawn   OPEN 0:58  CLOSE 2:07
```

Never more than three loops live at once. Closed in reverse order of opening.

---

## Visual plan

Palette: near-black street, one **warm amber** source (the lamp), cold blue rain.
Amber vs blue *is* the story — do not add a third accent.

| Time | Shot | Motion | Interrupt |
|---|---|---|---|
| 0:00–0:06 | ECU: filament in a bare bulb, rain-streaked glass | slow push-in 2%/s | Opening frame **is** the thumbnail |
| 0:06–0:10 | Wide: one lit window in a black terrace | Ken Burns 5%/4s | — |
| 0:10–0:16 | The window goes dark. Hold. | static | **Dip to black 0.5s** on "it went dark" |
| 0:17–0:31 | Maya walking, foreground occlusion (railings, rain) | parallax, handheld 1 Hz | — |
| 0:32–0:42 | Knuckles on wet door; rain intensity up | push-in 3%/s | Cuts tighten to ~1.5s ASL |
| 0:43–0:57 | Door opens, amber spills onto wet stone | L-cut into Tomas | **Colour shift** — first warm frame since 0:10 |
| 0:58–1:00 | ECU: estate-agent board | snap zoom 120% | **Zoom punch-in** on "sells" |
| 1:01–1:15 | Maya in rain, wide, small in frame | near-static, 4s ASL | **Slow beat** — let the mix breathe |
| 1:16–1:32 | Archival grade: a boy leaving, a winter road | 4:3 crop, film grain | **Aspect-ratio + medium shift** |
| 1:33–1:44 | Tomas' hand on the door; Maya's hand out | match cut hand→hand | — |
| 1:45–2:06 | Intercut: lit window seen from Maya's past walks | accelerating cuts to 1.2s | Fastest cutting of the piece |
| 2:07–2:19 | SOLD board; pull back to reveal a **different** lit window | slow pull-out, ease | Return to opening framing — the seam |

**Pattern interrupts used: 5** across 2:19 — within the 2–3 per minute ceiling.

**Captions.** Burn in karaoke cues (4 words each) for TikTok/Reels/Shorts; ship
the sentence-level `--write-subtitles` track on YouTube. Keep text inside the
centre 1080×1000 golden box. Ultra-bold sans, heavy drop shadow — the
amber-on-black frames will otherwise eat white text.

**Audio.** Sparse, unresolved bed — a low drone, no percussion, no cadence the
ear can lock to. Duck −10 dB under VO.
Drop the bed entirely for exactly one line — **"Nobody came." (1:30)** — then
bring it back under "But Maya put her hand out." Master −14 LUFS, ≤ −1 dBTP.
Keep room tone under every pause; never let the mix hit true digital silence.

---

## Files

| File | Purpose |
|---|---|
| `script.txt` | edge-tts input. Pure narration — punctuation is the only timing markup. |
| `README.md` | Why this example exists, the loop ledger, and the lint verdict |

Audio is not committed; regenerate it with the command in
[README.md](README.md). Measured output for reference: **139.7s** at `-25%`
(Ryan), **138.1s** at `-15%` (`en-IE-EmilyNeural`, a warmer alternate read).

Captions: `--write-subtitles` gives sentence-level cues, which suit YouTube. For
short-form burn-in, rebuild them at 3–5 words per cue from `WordBoundary` events
— see [tts-scripting.md](../../reference/tts-scripting.md#cli-facts).
