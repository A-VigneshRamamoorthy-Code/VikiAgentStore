# Sourcing

How to decide whether something is true enough to say out loud.

---

## The tiers

| Tier | What it is | Weight |
|---|---|---|
| **A — primary / adjudicated** | Court judgments and chargesheets, official inquiry and commission reports, government gazettes, legislative records, transcripts, contemporaneous official statistics, archival documents, first-hand testimony in a citable form | Can stand alone for a fact it directly adjudicates |
| **B — professional reporting & scholarship** | Wire services (Reuters, AP, AFP, PTI), major outlets with a corrections policy (BBC, Guardian, NYT, Hindu, Indian Express), peer-reviewed history, university-press books, encyclopaedias with signed authorship (Britannica) | Two independent B sources support a claim |
| **C — orienting only** | Wikipedia, aggregators, explainer sites, museum web copy, obituaries in local press | Use to *find* sources and to learn the shape of the story. Never the sole support for a figure, a date or a name |
| **D — excluded** | Blogs, forums, social posts, content farms, AI summaries, dramatisations, "based on a true story" films, tabloids | Not a source. May be a *subject* — "the film depicts…" is a claim about the film |

A claim with `"confidence": "high"` needs at least one Tier A or B source. The
linter enforces the count; only you can enforce the tier.

---

## Independence is the hard part

Two sources are independent when neither could be wrong *because* the other is.
The three failure modes, in ascending order of how often they catch people out:

1. **The wire echo.** Twelve outlets carrying the same Reuters copy is one
   source. Check the byline and the dateline, not the masthead.
2. **The citation loop.** A news article citing Wikipedia, and Wikipedia citing
   the news article. This happens more than it should with casualty figures.
   Follow every chain to its origin before counting it.
3. **The single official statement.** Every outlet quoting the same police
   spokesperson is one source — an important one, but one. Report it as what it
   is: *"police put the figure at…"*.

A useful test: if the earliest source turned out to be wrong, would the second
one still be right? If not, you have one source.

---

## Recency

Anything with a live legal, political or scientific thread must be re-checked at
the time of writing, not taken from the first article you found.

- Trials conclude and sentences are upheld, reduced or overturned.
- Long-running cases produce new facts decades on. A story set in one year may
   need a development from seventeen years later to be current.
- Tolls are revised. Early reporting under-counts; official counts land months
  later; anniversary journalism sometimes reverts to the early number.
- Attribution firms up. What was "suspected" in week one may be adjudicated in
  year four — or may still be suspected, in which case *say* "suspected".

Record an `accessed` date on every source. It is what lets a future reader know
which version of the world you were writing in.

---

## When sources disagree

Do not average them. Do not pick the biggest. Do not pick the one that scans
best. Do this instead:

1. **Prefer the adjudicated or official count** over contemporaneous reporting,
   and say whose count it is.
2. **Speak the floor with a hedge.** If reports range 31–36, write "at least
   31". Mark the claim `"contested": true` and put both figures in the ledger's
   `note`. The linter will then *require* a hedge word in any line that uses it.
3. **If the disagreement is itself the story, tell it.** "Estimates run from X
   to Y" is a legitimate sentence and often a more interesting one.
4. **Never let a total and its parts contradict each other on screen.** If you
   speak a total, check that the per-location figures you also speak can sit
   underneath it.

### The commonest trap: two figures counting different populations

A single reference work will often give a headline figure in its opening
paragraph and a different one in its body — because the two count different
populations. Totals that fold in perpetrators, crew, responders or
indirectly-attributed deaths sit above totals that do not.

Both numbers are correct and they will still look like an error if you mix them,
because the audience cannot see the definitions. Before treating a discrepancy
as a disagreement, **check whether it is a definition difference**. If it is,
the fix is not to pick one:

- Speak each population in its own sentence, so the definitions stay visible.
- Hedge whichever one has a genuine underlying range.
- Put the reconciliation in the ledger `note` so the next person does not
  rediscover it.

The worked example in [`examples/`](../examples/) carries a real instance of
this, with the arithmetic written out.

---

## Gathering, practically

**Encyclopaedic spine, as plain text:**

```bash
curl -sL "https://en.wikipedia.org/w/api.php?action=query&prop=extracts\
&explaintext=1&format=json&formatversion=2&titles=PAGE_TITLE" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['query']['pages'][0]['extract'])"
```

**Its citation list** — the actual point of the exercise:

```bash
curl -sL "https://en.wikipedia.org/w/api.php?action=parse&prop=externallinks\
&format=json&formatversion=2&page=PAGE_TITLE"
```

**Contemporaneous reporting** beats retrospective reporting for *sequence* and
loses to it for *causation*. Use archived day-of timelines for what happened
when, and later analysis for why. Day-of *figures* are almost always wrong —
see [When sources disagree](#when-sources-disagree).

### When the publisher refuses a plain request

Many of the outlets most worth citing answer `curl` with a bot-challenge page
rather than an article — major encyclopaedias, most national newspapers and a
good number of government portals. Legacy news archives and the Wikipedia API
generally return clean text; their modern equivalents generally do not.

Do not silently drop them, and do not cite a page you could not read. Fetch them
through a real browser engine instead:

```bash
npm i --no-save playwright-core
npx playwright install chromium --only-shell

node fetch-source.mjs targets.json sources/
```

`targets.json` is `{ "source-id": "url" }` keyed by the ids you will use in the
ledger. The helper writes `sources/<id>.txt` plus a `manifest.json` carrying the
URL, the page title, the HTTP status and the access date — which is most of a
ledger source record already.

The browser is always headless and never opens a window. Anything shorter than
about 1,200 characters is reported as `THIN`, because a challenge page and a
short article are indistinguishable by exit status alone.

**When even that fails, the claim is demoted, not asserted.** An official
register that would have been the primary source, but never responds, leaves the
claim resting on whatever weaker sourcing you have. The correct response is to
keep it at `confidence: medium`, attribute it out loud in the narration
("official accounts credit…"), and write the failed attempt into the ledger
`note` so the next person does not repeat it. The alternatives — asserting it
anyway, or dropping a well-attested fact — are both worse.

**Books** are cited by author, title, publisher, year and page. If you cannot
give a page, you have not read it and it is not a source.

---

## Recording a source

```json
{
  "id": "wire-timeline",
  "title": "Timeline: how the week unfolded",
  "publisher": "Reuters",
  "date": "2011-03-18",
  "url": "https://example.org/article/timeline",
  "tier": "B",
  "accessed": "2026-08-20",
  "note": "Contemporaneous; times are local and approximate, and the toll it carries was later revised."
}
```

`note` is where you keep the thing that will otherwise be forgotten: that the
times are approximate, that the figure was provisional, that the outlet later
issued a correction.
