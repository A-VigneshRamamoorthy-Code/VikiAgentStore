# Sensitive subjects

Atrocities, disasters, crime, and the people still living with them.

Set `sensitive: true` in the frontmatter. The linter then checks the vocabulary.
Everything else here is on you.

---

## The line

**Report, do not dramatise.** A factual account of an atrocity is journalism. The
same account written for effect is entertainment made out of someone's worst
day, and the families are still alive to watch it.

The practical test: *would a survivor recognise this as an account of what
happened, or as a performance of it?*

---

## Rules

### 1. Anchor on people and place, not on the act

The subject is the city, the building, the people who were in it. Not the
violence. A siege is described by its duration, its geography and its cost — not
by choreography.

### 2. No tactical detail

Nothing that reads as method. No weapons inventories, no explosive
specifications, no description of how a defence was defeated, no operational
sequence that would function as instruction. Say a bomb was planted and it
exploded; do not say what it was made of or where it was placed to best effect.

### 3. Name the adjudicated, not the alleged

For a long-form factual account, naming a convicted perpetrator and the
organisation a court found responsible is **required for accuracy** — an
anonymous account of an attack is not a truthful one. But:

- Name only what has been **adjudicated or officially attributed**, and say
  which. "A court convicted X" is a fact; "X did it" may not be.
- Anyone acquitted, uncharged or merely suspected is described as such, once,
  and not returned to.
- **No ideology, no manifesto, no grievance narrative, no biography of a
  perpetrator's motivation.** These are the parts that recruit. State the
  organisation, state the finding, move on.
- Do not give a perpetrator the last word, the emotional beat, or the close.

> This deliberately differs from `paper-explainer`'s rule for
> **30-second** pieces, which drops perpetrator names entirely. A short piece
> cannot carry the context that makes naming responsible; a 10-minute one
> cannot omit it without misleading. Match the rule to the length.

### 4. Casualty figures stand alone

- Their own line, their own beat, real silence around them.
- Never scored, never stung, never stacked with a second figure in the same
  breath.
- Hedge them — see `contested` in [fact-ledger.md](fact-ledger.md).
- Give the count **and** at least one named person, so the number does not
  become an abstraction.

### 5. Victims are people, not material

Name victims who are already publicly named and whose naming serves the account
— the officers who died, the staff who stayed. Do not name minors, do not name
the injured, do not describe wounds, do not describe how anyone died beyond what
is necessary to establish the fact. No signs of torture, no last moments, no
recreated dialogue.

### 6. Nothing is recreated

No invented dialogue, no invented interiority, no "he must have thought". If it
is not in a source, it did not happen. Speculation phrased as narration is the
most common way an accurate script becomes a false one.

### 7. Close on what followed

End on consequence, restoration, memory, or an unresolved question — never on
the worst moment. The last thirty seconds are what the viewer keeps.

### 8. Living people and defamation

- Any assertion about a living, identifiable person needs a Tier A/B source and
  should be attributed in the narration.
- Convictions: state the court and the date. Overturned convictions must be
  reported as overturned in the same breath.
- Do not imply a link between a named person and a crime that no court or
  official finding has made.
- Ongoing proceedings: say they are ongoing.

### 9. Communities

An attack carried out by members of an organisation is not an attack carried out
by a nationality, a religion or an ethnicity. Attribute to the organisation and
to the individuals a court identified. State officially-established state
involvement as exactly what the official finding says and no further.

---

## Vocabulary

`sensitive: true` in the frontmatter turns on the dramatising-register check. It
warns rather than fails, because it is a prompt to look — but each hit needs a
reason to stay, and `--strict` turns every one of them into a failure.

| Avoid | Why | Use |
|---|---|---|
| massacre, slaughter, carnage, bloodbath, butchered | Tabloid intensifiers | killed; the attack |
| horrific, chilling, terrifying, shocking, brutal, savage | Tells the viewer how to feel | Let the fact do it |
| cold-blooded, evil, monster, mastermind | Character judgement, not reporting | Name the finding |
| stormed, unleashed, rampage, hail of bullets, war zone | Action-film register | entered; opened fire |
| miraculously, tragically, heartbreakingly | Editorialising | Cut |
| innocent victims | Implies some were not | victims; the dead |
| claimed the lives of | Euphemism | killed |

The general rule: **an adjective doing emotional work in a sentence about a
death is doing the viewer's job for them.** The facts of a real event do not
need help.

---

## Silence

On this material, silence is content. Budget it:

- **1.0–1.5 s** before and after a casualty figure.
- **A full beat** at the end of any chapter that ends in a death.
- **2–3 s of tail** on the final image, with no narration over it.

If the piece comes in under target because of the rests, that is the correct
outcome. Do not backfill with words.

---

## Before shipping

1. Could any line be read as instruction? Cut it.
2. Does any adjective tell the viewer how to feel? Cut it.
3. Is every named person named for a reason, and sourced?
4. Is anything asserted about a perpetrator's beliefs or motives? Cut it.
5. Is any death described beyond the fact of it? Cut back to the fact.
6. Does the piece end on consequence rather than on the attack?
7. **Is the provenance on screen, legible, and unhurried?**
8. Would you screen it, unannounced, to someone who was there?

### On-screen provenance

A sensitive piece has to show where it got this. Give the source line **its own
beat in the tail**, after the closing image, with nothing else competing for
attention.

Do not scatter it through the film as background furniture. A credit set as
permanent decor is the worst of both worlds: it is never actually read, and it
is the element most likely to end up half-covered by artwork — in the
`paper-explainer` skill, literally so, because background-baked elements are
drawn beneath everything else (see that skill's `storyboard-reference.md`). A credit that
renders half-eaten is worse than no credit, because it signals carelessness
about exactly the thing you most need the audience to trust.
