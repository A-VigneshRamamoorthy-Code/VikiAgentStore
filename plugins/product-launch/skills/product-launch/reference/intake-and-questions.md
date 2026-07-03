# Intake and Questions

The product-launch skill is generic and user-driven. Every brand-specific name, link, claim, and visual direction must come from the user or their config.

---

## ⛔ Mandatory first question: demo recording

A **demo recording is required**.

If the user has not provided a video path/attachment, the agent **MUST ask via `ask_user` before doing anything else**. Do not probe, build, mock footage, or invent a product story.

Ask clearly:

> Please share a screen recording / demo video of the product in action (about 15–60s is ideal). What is the file path?

If they cannot provide a recording, stop and explain that the skill needs real product footage.

---

## Required / useful details

Collect these before authoring the final config:

| Detail | Why it matters | Can default? |
|--------|----------------|--------------|
| Demo recording path | Required `input` | No |
| Product name | `brand.name`, intro, end-card | No |
| Tagline / one-line pitch | `brand.tagline`, intro subtitle | Ask or leave blank |
| 3–6 feature captions | `captions[].text` | Ask; do not invent claims |
| Brand accent color | `brand.primary` | Offer a default, confirm |
| 2–3 gradient colors | `brand.bg_gradient` | Can derive from accent if approved |
| Motion personality | `personality` | Offer choices |
| Output aspect | `resolution` | Offer 16:9 default |
| Outro headline | `outro.headline` | Ask |
| CTA button/link | `outro.cta_text`, `outro.link` | Optional; never invent links |
| Footnote | `outro.footnote` | Optional |
| Logo/app icon | `brand.logo` | Optional; `null` generates a mark |
| Music vibe | `music.vibe`, `music.enabled` | Offer choices |

---

## Choices to offer

| Question | Options |
|----------|---------|
| Motion personality | `playful`, `premium`, `corporate`, `energetic` |
| Aspect | 16:9 `[1920,1080]`, 1:1 `[1080,1080]`, 9:16 `[1080,1920]` |
| Transition style | `wipe`, `dissolve`, `cut` |
| Music vibe | `modern-playful`, `calm`, `energetic`, `corporate`, or disabled |
| Fit | `height`, `width`, `contain`, `cover` |

---

## `ask_user` form template

Adapt this form to the missing fields. Keep related questions batched.

```json
{
  "message": "I can turn your demo recording into a polished launch video. Please provide the missing details below.",
  "fields": [
    {
      "name": "input",
      "label": "Path to the demo recording",
      "type": "string",
      "required": true,
      "placeholder": "demo.mov"
    },
    {
      "name": "brand.name",
      "label": "Product name",
      "type": "string",
      "required": true
    },
    {
      "name": "brand.tagline",
      "label": "One-line tagline / positioning",
      "type": "string",
      "required": false
    },
    {
      "name": "features",
      "label": "3–6 feature captions or key selling points",
      "type": "textarea",
      "required": true,
      "placeholder": "One feature per line"
    },
    {
      "name": "brand.primary",
      "label": "Brand accent color (hex)",
      "type": "string",
      "required": false,
      "placeholder": "#5B8DEF"
    },
    {
      "name": "brand.bg_gradient",
      "label": "Optional 2–3 gradient colors (hex)",
      "type": "string",
      "required": false,
      "placeholder": "#14172B, #1E2348, #101326"
    },
    {
      "name": "personality",
      "label": "Motion personality",
      "type": "select",
      "options": ["playful", "premium", "corporate", "energetic"],
      "default": "playful"
    },
    {
      "name": "aspect",
      "label": "Output aspect",
      "type": "select",
      "options": ["16:9", "1:1", "9:16"],
      "default": "16:9"
    },
    {
      "name": "outro.headline",
      "label": "Outro headline",
      "type": "string",
      "required": false
    },
    {
      "name": "outro.cta_text",
      "label": "Optional CTA button text",
      "type": "string",
      "required": false
    },
    {
      "name": "outro.link",
      "label": "Optional CTA link",
      "type": "string",
      "required": false
    },
    {
      "name": "brand.logo",
      "label": "Optional logo/app-icon path",
      "type": "string",
      "required": false
    },
    {
      "name": "music.vibe",
      "label": "Music vibe",
      "type": "select",
      "options": ["modern-playful", "calm", "energetic", "corporate", "disabled"],
      "default": "modern-playful"
    }
  ]
}
```

---

## Defaulting rules

- Offer defaults for style: aspect, colors, motion personality, transitions, music.
- Confirm defaults before rendering when they affect brand identity.
- Never invent product names, links, customer claims, performance claims, prices, or availability.
- If the user gives rough feature bullets, rewrite them into concise captions without changing their claims.
