# Licensing, asset by asset

## The register

`meta/assets.json` — every visual and audio element that reaches the screen.

```json
[
  { "file": "art/cooper_sketch.png", "license": "public-domain",
    "source": "FBI, 1971 composite sketch" },
  { "file": "art/map.png", "license": "cc-by",
    "credit": "© OpenStreetMap contributors",
    "source": "https://www.openstreetmap.org/copyright" },
  { "file": "art/board.png", "license": "generated",
    "source": "style-paper procedural collage" }
]
```

`file` and `license` are required. `credit` is required for anything in the
CC-BY family. `source` is not checked but is what makes a challenge answerable
a year later.

## Recognised licences

| value | obligation | notes |
|---|---|---|
| `public-domain` | none | verify the *jurisdiction* — US federal works are PD in the US; Crown copyright is not |
| `cc0` | none | explicit dedication, safer than assumed PD |
| `cc-by`, `cc-by-sa`, `cc-by-nd`, `cc-by-nc`, `cc-by-nc-*` | credit, visibly | `-nc` variants are unusable on a monetised channel |
| `owned` | none | shot or commissioned by the channel |
| `original` | none | drawn or written for this film |
| `generated` | none | procedural or synthesised by the pipeline |
| `licensed` | per contract | record the licence id in `source` |
| `fair-dealing` / `fair-use` | argued, not assumed | see below |

Anything else is refused rather than guessed at.

## The traps

**Public domain is not global.** A 1971 FBI photograph is public domain in the
United States and may not be elsewhere. Record the jurisdiction you are relying
on.

**"Found on Wikipedia" is not a licence.** Wikipedia hosts CC-BY-SA, CC0, PD
and fair-use images side by side. Open the file page and read the actual tag.

**`-nc` means non-commercial.** A monetised YouTube channel is commercial.
There is no grey area here, and the takedown comes from the photographer, not
the platform.

**News stills are almost never free.** Agency photographs (AP, Reuters, Getty)
are licensed per use. Using one because it appeared in a news article is the
single most common way a documentary channel gets struck.

**Music is two rights, not one.** The composition and the recording are
licensed separately. A public-domain composition performed in 2019 has a
copyrighted recording. This is why the pipeline synthesises its beds.

**AI-generated imagery carries the prompt's problems.** A model asked for "a
photo in the style of a named living photographer" produces something with a
plausible claim against it. Record `generated` only for assets whose inputs you
control.

## Fair dealing / fair use

A real defence, not a label. It is only arguable when the use is
*transformative* — the film comments on the asset itself — and uses no more
than needed. Showing a newspaper front page while discussing that front page is
arguable. Using the same page as wallpaper behind unrelated narration is not.

If you record `fair-dealing`, write the argument in `source`. A clearance
record that says "fair use" and nothing else is worth nothing at the moment it
is needed.

## Claims in the metadata

The second half of clearance is not about assets at all. The title is written
last, by whoever wants the click, and it is where a careful film starts
overclaiming.

Every **figure** and every **absolute** in the title or description must appear
in the ledger:

- *"The 40,000 dollar ransom"* — refused if the ledger says 200,000.
- *"The only unsolved hijacking"* — *only* is a claim; source it or cut it.
- *"They never found him"* — *never* is a claim about the present; check it is
  still true on the day of upload.

Hedged phrasing that the ledger supports always survives. *"Still unsolved"*
costs nothing and cannot be falsified next year.
