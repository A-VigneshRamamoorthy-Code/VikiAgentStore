# 🏬 VikiAgentStore

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
copilot plugin install design-system@VikiAgentStore
copilot plugin install motion-design@VikiAgentStore
copilot plugin install notch-companion-app@VikiAgentStore
copilot plugin install product-launch@VikiAgentStore
```

That's it — the skill is now available to Copilot. Run `copilot plugin list` to confirm.

Inside an interactive Copilot session you can also use the `/plugin` command to manage everything from the UI.

> **Note:** Installing via `plugin@VikiAgentStore` (after registering the marketplace) is the recommended, forward-supported path. Direct one-liner installs such as
> `copilot plugin install A-VigneshRamamoorthy-Code/VikiAgentStore:plugins/design-system`
> still work but are being deprecated by the CLI in favor of marketplace installs.

---

## 📦 Available plugins

| Plugin | What it does |
| --- | --- |
| **design-system** | Visual design language for all UI output — tokens, typography, buttons, cards, accordions, sidebars, modals and more. Use it whenever you build landing pages, web apps, or dashboards. |
| **motion-design** | Emotionally-driven, technically-sound animation: timing, easing, choreography and Disney animation principles adapted for UI. Works with CSS, Framer Motion, GSAP, Lottie, Spring. |
| **notch-companion-app** | Playbook for building lightweight native macOS "notch companion" apps — transparent overlays, physics-driven animation, 0%-idle-CPU loops, and DMG/GitHub distribution (no Xcode required). |
| **product-launch** | Turns a product demo recording into a polished, motion-designed launch video — branded intro, synced captions, transitions, music bed, and outro CTA. Cross-platform (ffmpeg + Python). |

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
├── .github/plugin/marketplace.json   # marketplace catalog (indexes every plugin)
└── plugins/
    └── <plugin-name>/
        ├── plugin.json               # plugin manifest ("skills": ["./skills/"])
        └── skills/<plugin-name>/     # the skill (SKILL.md + resources)
```

Each plugin is self-contained, so the CLI can install a single one without pulling the rest of the store.

---

## ➕ Adding your own plugin

1. Create `plugins/<your-plugin>/skills/<your-plugin>/SKILL.md` (plus any resources).
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
3. Register it in `.github/plugin/marketplace.json` under `plugins`:
   ```json
   { "name": "your-plugin", "source": "plugins/your-plugin", "description": "…", "version": "1.0.0" }
   ```
4. Commit and push. Users get it instantly with `copilot plugin marketplace update VikiAgentStore`.

---

## 📄 License

[MIT](./LICENSE) — the bundled skills retain their original licenses.
