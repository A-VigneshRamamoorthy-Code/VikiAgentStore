# Consent — whose voice you may clone

Voice cloning is the one part of this pipeline where the technical capability
runs well ahead of what you are permitted to do with it.

---

## The rule

> Clone only a voice you have the **right** to clone.

**Fine:**

- Your own voice.
- A **synthetic / AI-generated** voice (no human identity attached).
- A free **Edge / Azure neural voice** — what `build_cast.py` uses by default.
- A real person who **agreed in writing**, for this specific purpose.
- Licensed stock voice-over where the licence permits synthesis.

**Not fine:**

- A YouTuber, podcaster, presenter, actor, singer or public figure.
- Anyone identifiable who has not agreed — including a colleague or friend whose
  voice note you happen to have.
- "Just for testing." The clone itself is the risk, not what you intend to do
  with it afterwards.

---

## Why "just for testing" doesn't hold

Four separate things go wrong the moment the clone exists, regardless of intent:

1. **Data protection.** In the UK and EU a voiceprint is biometric/personal data.
   Processing it needs a lawful basis. Testing is not one.
2. **Right of publicity.** Several US states (California, New York, Tennessee's
   ELVIS Act) protect a person's voice as a property right. Some cover
   *simulations* explicitly.
3. **Platform terms.** Downloading YouTube audio to extract a voice breaches the
   YouTube ToS independently of anything else.
4. **The artefact outlives the intent.** A cloned reference is a file. It gets
   copied, committed, shared, or reused six months later by someone who never saw
   the "test only" note.

---

## What to do instead when someone points at a reference video

Almost always, what they actually want is the **delivery**, not the person. Style
is not ownable; a voice is.

Characterise the reference and reproduce it with a licensed voice:

| Extract from the reference | Reproduce with |
| --- | --- |
| Register (colloquial vs formal, Tanglish density) | rewrite the script |
| Pace, pauses, phrase length | sentence chunking + `rate` |
| Pitch centre and range | `pitch` on the Edge reference |
| Energy, warmth, brightness | source voice choice + mastering EQ |

This gets you a voice that *feels* like the reference and is entirely yours.

---

## How to raise it

If asked to clone a specific real person, say no once, plainly, and immediately
offer the alternative — the goal behind the request is nearly always legitimate:

> I can't clone <person> — that's a real, identifiable voice and we don't have
> their consent. What I can do is match the *style*: same colloquial register,
> same pacing and energy, built on a licensed voice. Want me to build that?

Don't lecture, and don't refuse without giving them a path forward.

---

## Recording your own reference

The best reference is one you record yourself:

- 8–12 s of continuous natural speech
- quiet room, no music, one speaker, minimal reverb
- speak as you want the character to sound — the clone copies delivery, not just
  timbre
- get the transcript exactly right (`scripts/transcribe.py`)

```bash
.venv/bin/python scripts/narrate.py --ref me.m4a \
    --ref-text "<exactly what you said>" --script "..." --out out.mp3
```
