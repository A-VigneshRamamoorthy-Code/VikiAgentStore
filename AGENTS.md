# VikiAgentStore — Agent Guide

Technical guide for agents working in this repository. Read this before adding
or changing a plugin, skill or MCP server.

## What this repo is

A **GitHub Copilot CLI plugin marketplace** plus the static website that
showcases it.

- **Plugins** live in `plugins/<id>/` and are installed by the Copilot CLI.
- **MCP servers** live in `mcp/<id>/` and are listed on the site.
- **The website** is a dependency-free static site in `docs/` (HTML + one JS
  file + one CSS file), deployed to **Vercel** and **GitHub Pages**.

## ⛔️ The single most important rule

**`docs/catalog.json` and `.github/plugin/marketplace.json` are GENERATED. Never
hand-edit them.**

Both are produced from the filesystem by:

```bash
node scripts/generate-catalog.mjs           # write
node scripts/generate-catalog.mjs --check   # exit 1 if out of date (used by CI)
```

Hand-editing them causes the two registries to drift apart — which is exactly
what happened before this was automated: the CLI manifest listed `hosting` but
not `file-organise`, while the website listed the opposite.

## Source of truth

| Input | Feeds |
|-------|-------|
| `plugins/<id>/plugin.json` | plugin id, version, license, description |
| `plugins/<id>/skills/<skill>/SKILL.md` | skill name + description (YAML frontmatter) |
| `plugins/<id>/**/*.md` | `docCount` shown on the card |
| `mcp/<id>/mcp.json` | MCP server name, description, tools |
| `scripts/store-meta.json` | **presentation only** — icon, accent, category, tagline, tags, highlights |

Everything factual is derived from the plugin itself. `store-meta.json` holds
only how it *looks* in the store.

## Adding a plugin

```
plugins/<id>/
├── plugin.json
└── skills/<skill-name>/
    ├── SKILL.md          # required, with YAML frontmatter
    └── *.md              # optional reference modules
```

`plugin.json`:

```json
{
  "name": "<id>",
  "version": "1.0.0",
  "description": "One or two sentences. Shown on the card and in the CLI.",
  "skills": ["./skills/"],
  "license": "MIT"
}
```

`SKILL.md` frontmatter:

```yaml
---
name: <skill-name>
description: >
  What the skill does and when to use it. Written so an agent can decide
  whether to load it.
license: MIT
metadata:
  author: Your Name
  version: "1.0.0"
---
```

Then commit and push. **That is the whole process** — the catalog regenerates
itself in CI and the site redeploys.

### Optional polish

A new plugin appears immediately with a default icon under **Uncategorised**. To
give it a proper identity, add an entry to `scripts/store-meta.json`:

```jsonc
"<id>": {
  "name": "Display Name",
  "icon": "🗂️",
  "accent": "teal",                  // brand | sky | pink | teal | orange
  "category": "Files & Media",
  "tagline": "One line shown on the card.",
  "author": "Your Name",
  "tags": ["up", "to", "three shown"],
  "highlights": ["Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4"],

  // optional: a shorter display blurb than the SKILL.md frontmatter
  "skillDescriptions": { "<skill-name>": "Short version for the store." }
}
```

New categories must also be listed in `categoryOrder` to control their position;
unknown categories are appended alphabetically.

## Adding an MCP server

See [`mcp/README.md`](mcp/README.md). MCP servers are listed on the website but
deliberately **not** written into `.github/plugin/marketplace.json`, because that
manifest describes Copilot CLI *plugins*.

## The website

`docs/` is served as-is. There is no build step.

- `docs/index.html` — markup and the stat placeholders
- `docs/app.js` — fetches `catalog.json` and renders everything
- `docs/styles.css` — accent tokens are `[data-accent="brand|sky|pink|teal|orange"]`
- `docs/catalog.json` — **generated**

`app.js` renders whatever is in `catalog.json`, so a plugin that is missing from
the catalog is invisible on the site no matter what exists on disk.

### Verifying a change to the site

The page is JavaScript-rendered, so `curl` alone proves nothing. Use the
committed checker, which executes the real `app.js` and clicks every card:

```bash
npm i --no-save jsdom
node scripts/verify-site.mjs                              # docs/ on disk
node scripts/verify-site.mjs https://agentstore.sololeapinc.com   # a live site
```

Two things worth knowing:

- **Skills and install commands render only inside the modal**, which `app.js`
  builds on click — asserting against the card grid gives false failures.
- **Headless Chrome hangs on this project's macOS setup** (both `--headless` and
  `--headless=new`, >210 s, even with a fresh `--user-data-dir`). jsdom is the
  supported path.

## Deployment

| Host | URL | Trigger |
|------|-----|---------|
| **Vercel** (canonical) | `agentstore.sololeapinc.com` | `publish` workflow, needs `VERCEL_TOKEN` |
| **GitHub Pages** (mirror) | `a-vigneshramamoorthy-code.github.io/VikiAgentStore` | automatic from `main:/docs` |

Vercel project `viki-agent-store` — org `team_1GZSIzrQV6ZhpNr15XmWY5GW`, project
`prj_lqT4dPlOS5XaGsakbpxYCSDWSMdM`, `outputDirectory: docs`, no build step.

- DNS for `agentstore.sololeapinc.com` is a **CNAME to `cname.vercel-dns.com`**,
  managed at **Squarespace**. It is already configured and working.
- ⚠️ **The Vercel project is NOT git-linked, so pushing to GitHub does not deploy
  it by itself.** Linking requires the [Vercel GitHub App](https://github.com/apps/vercel)
  to be installed on the GitHub account; it currently is not, and the API refuses
  the link until it is (`bad_request: you need to install the GitHub integration
  first`). Installing it is a browser flow.
- Until then, the `publish` workflow is what keeps the domain current — and it
  needs a token:

  ```bash
  gh secret set VERCEL_TOKEN --repo A-VigneshRamamoorthy-Code/VikiAgentStore
  ```

  Create the token at <https://vercel.com/account/settings/tokens>.
  `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` are already in the workflow — they are
  identifiers, not credentials.
- **If `VERCEL_TOKEN` is absent the production domain silently serves stale
  content** while GitHub Pages updates normally. The workflow emits a warning and
  a job summary rather than failing, so watch for it.

Either of these fixes it permanently — installing the GitHub App is the better
one, because it needs no secret at all.

### Deploying by hand

```bash
npx vercel@latest deploy --prod --yes    # uses ~/Library/Application Support/com.vercel.cli
```

The CLI's stored session expires every 8 hours. It refreshes itself; if it has
been dormant too long, `npx vercel@latest login` re-authenticates.

## CI

`.github/workflows/publish.yml`:

- **on pull request** — runs `--check` and fails if the generated files are stale.
- **on push to `main`** — regenerates, auto-commits any change with `[skip ci]`,
  verifies the site renders, then deploys to Vercel.

The auto-commit uses the default `GITHUB_TOKEN`, whose pushes do not re-trigger
workflows, so there is no recursion.

⚠️ **Pushing a change to `.github/workflows/` needs a token with `workflow`
scope.** The default macOS git credential helper usually has a plain `repo`-scoped
OAuth token and the push is rejected. Use `gh`'s token — and note that the helper
list must be **reset** first, or the keychain helper wins:

```bash
git -c credential.helper= \
    -c credential.helper='!f(){ echo username=x-access-token; echo "password=$(gh auth token)"; };f' \
    push
```

## Conventions

- Keep the website dependency-free — no framework, no build step.
- The generator uses only the Node standard library, so CI needs no `npm install`.
- Prefer splitting a large skill into `SKILL.md` plus reference modules, so an
  agent loads only what it needs (see `plugins/file-organise/skills/songs/`).
- `id` is the directory name and is what users type:
  `copilot plugin install <id>@VikiAgentStore`. Keep it kebab-case.
