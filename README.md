# 🏬 VikiAgentStore

<div align="center">

### 🌐 [**Browse the Plugin Store →**](https://agentstore.sololeapinc.com)

<sub>Mirror: [a-vigneshramamoorthy-code.github.io/VikiAgentStore](https://a-vigneshramamoorthy-code.github.io/VikiAgentStore/)</sub>

</div>

---

**A GitHub Copilot CLI plugin marketplace by [Vignesh Ramamoorthy](https://github.com/A-VigneshRamamoorthy-Code).**

VikiAgentStore packages a curated set of [Copilot CLI skills](https://docs.github.com/copilot/concepts/agents/copilot-cli/about-cli-plugins) as **plugins** you can install straight from the Copilot CLI — **no need to clone or download this repo**. The CLI fetches only the plugin you ask for.

---

## 🚀 Quick start

### 1. Register the marketplace (one time)

```bash
copilot plugin marketplace add A-VigneshRamamoorthy-Code/VikiAgentStore
```

### 2. Browse what's available

```bash
copilot plugin marketplace browse VikiAgentStore
```

### 3. Install any plugin

```bash
copilot plugin install design@VikiAgentStore
copilot plugin install notch-companion-app@VikiAgentStore
copilot plugin install product-launch@VikiAgentStore
copilot plugin install apple-dev@VikiAgentStore
copilot plugin install file-organise@VikiAgentStore
copilot plugin install google-dev@VikiAgentStore
copilot plugin install hosting@VikiAgentStore
```

That's it — the skill is now available to Copilot. Run `copilot plugin list` to confirm.

Inside an interactive Copilot session you can also use the `/plugin` command to manage everything from the UI.

> **Note:** Installing via `plugin@VikiAgentStore` (after registering the marketplace) is the recommended, forward-supported path. Direct one-liner installs such as
> `copilot plugin install A-VigneshRamamoorthy-Code/VikiAgentStore:plugins/design`
> still work but are being deprecated by the CLI in favor of marketplace installs.

---

## 📦 Available plugins

| Plugin | What it does |
| --- | --- |
| **design** | Visual design language **plus motion** for all UI output. Bundles three skills: **clean-ux** (tokens, typography, buttons, cards, accordions, sidebars, modals), **motion-ux** (timing, easing, choreography and Disney animation principles), and **minimal-ux** (light, editorial/agency aesthetic with advanced GSAP/Lenis animations, 3D scroll experiences). Use it whenever you build and animate landing pages, web apps, portfolios, or dashboards. |
| **notch-companion-app** | Playbook for building lightweight native macOS "notch companion" apps — transparent overlays, physics-driven animation, 0%-idle-CPU loops, and DMG/GitHub distribution (no Xcode required). |
| **product-launch** | Turns a product demo recording into a polished, motion-designed launch video — branded intro, synced captions, transitions, music bed, and outro CTA. Cross-platform (ffmpeg + Python). |
| **apple-dev** | Skills for Apple development, including architecture, app store submission, widgets, in-app purchases, etc. |
| **file-organise** | Cleans up and organises messy file collections. Bundles the **songs** skill: a playbook for repairing music library metadata, filenames, folder structure and album art at scale — using acoustic fingerprinting (Chromaprint + AcoustID) to identify untagged files and catch duplicates that name matching cannot see. |
| **google-dev** | Getting Google Sign-In and OAuth scopes through Google's verification review — choosing the narrowest scope, the sensitive/restricted tiers and when a CASA assessment applies, the privacy-policy disclosures reviewers look for, recording a demo video that is not rejected, and replying to a rejection. |
| **hosting** | Deploys a web app to Vercel and wires up custom DNS — `vercel.json`, production deploys, domain linking, and registrar instructions. |

---

## 🔄 Managing installed plugins

```bash
copilot plugin list                          # see what's installed
copilot plugin update <name>                 # update a single plugin
copilot plugin update                        # update everything
copilot plugin uninstall <name>              # remove a plugin
copilot plugin marketplace update VikiAgentStore   # refresh the catalog
```

---

## 🗂️ Repository layout

```
VikiAgentStore/
├── .github/
│   ├── plugin/marketplace.json       # GENERATED — catalog the Copilot CLI reads
│   └── workflows/publish.yml         # regenerates the catalog + deploys the site
├── plugins/
│   └── <plugin-name>/
│       ├── plugin.json               # plugin manifest ("skills": ["./skills/"])
│       └── skills/
│           └── <skill-name>/         # one or more skills (SKILL.md + resources)
├── mcp/                              # optional MCP servers (listed on the site)
├── scripts/
│   ├── generate-catalog.mjs          # the generator — filesystem is the source of truth
│   └── store-meta.json               # presentation only (icon, accent, category…)
└── docs/                             # the website
    └── catalog.json                  # GENERATED — catalog the website reads
```

Each plugin is self-contained and may bundle one or more skills, so the CLI can install a single plugin without pulling the rest of the store. (For example, the **design** plugin bundles the `clean-ux`, `motion-ux` and `minimal-ux` skills.)

> ⛔️ **`docs/catalog.json` and `.github/plugin/marketplace.json` are generated — never edit them by hand.** Both are derived from `plugins/` and `mcp/` by `scripts/generate-catalog.mjs`.

---

## ➕ Adding your own plugin

1. Create `plugins/<your-plugin>/skills/<your-skill>/SKILL.md` (plus any resources).
2. Add `plugins/<your-plugin>/plugin.json`:
   ```json
   {
     "name": "your-plugin",
     "version": "1.0.0",
     "description": "What your skill does and when to use it.",
     "skills": ["./skills/"],
     "license": "MIT"
   }
   ```
3. Commit and push.

**That's it.** CI regenerates both catalogs and redeploys the store, so the plugin
shows up on the website *and* becomes installable — no manual registration.

Run it yourself any time:

```bash
node scripts/generate-catalog.mjs           # regenerate
node scripts/generate-catalog.mjs --check   # fail if out of date (CI uses this)
```

To give the plugin a custom icon, accent colour or category on the website, add an
entry to [`scripts/store-meta.json`](scripts/store-meta.json). See
[**AGENTS.md**](./AGENTS.md) for the full contributor guide.

---

## 📄 License

[MIT](./LICENSE) — the bundled skills retain their original licenses.
