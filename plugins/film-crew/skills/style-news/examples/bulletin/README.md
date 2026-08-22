# Worked example — a bulletin

A short report, from beat plan to contact sheet.

```bash
S=../..                      # the news style folder

python3 $S/scripts/compile.py beat-plan.json -o storyboard.json
python3 $S/scripts/render.py storyboard.json --sheet
python3 $S/scripts/render.py storyboard.json --preview     # 26s, half resolution
```

`bulletin_sheet.jpg` is the committed output of the middle command. If your
sheet does not look like it, something in the style has changed.

## What to notice

- **The film opens on a title card.** The first beat is an `establish`, which
  compiles to a locator — a chip in the corner and nothing else. That would
  have left the first 4.7 seconds without a graphic, so the compiler inserts
  the title. Delete `title` from the beat plan and watch the opening go bare.
- **`MAHARASHTRA` never leaves.** One locator beat, and the chip holds for the
  whole report because a locator is an overlay rather than a card.
- **`12,000 households lost power` split itself in two.** The compiler pulls
  the leading figure out of the subject and gives it the frame. Written as
  `households losing power reached 12,000` it would have compiled to a headline
  bar instead — the number matters, so put it first.
- **The list has no red header.** Its kicker would have been its own first
  keyword, so the compiler drops it rather than printing `SAFETY AUDITS` above
  `Safety audits`. Give the beat an act with a title if you want a header.
- **Nothing is on screen twice and nothing is on screen never.** Each
  full-width graphic ends exactly where the next begins.

## Narration

`duration` on each line is what makes this work. Here they are plausible
numbers typed by hand; in a real production they are measured from the rendered
audio by [`voice-booth`](../../../voice-booth/), so the graphics land on the
voice rather than near it.
