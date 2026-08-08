# MCP Servers

Drop an MCP server here and it appears on the store automatically — no catalog
editing, no website change.

## Layout

```
mcp/
└── <server-id>/
    ├── mcp.json      # required — the manifest below
    └── README.md     # optional — counted towards the store's doc count
```

## `mcp.json`

```jsonc
{
  "name": "example-server",
  "displayName": "Example Server",          // optional; defaults to a title-cased name
  "description": "What this server gives an agent.",
  "version": "1.0.0",
  "license": "MIT",

  // How an agent launches it. Either "command" (stdio) or "url" (http/sse).
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@example/mcp-server"],
  "env": {
    "EXAMPLE_API_KEY": "${EXAMPLE_API_KEY}"
  },

  // Tools the server exposes. These render as the entries inside the
  // store's "What's inside" panel, exactly like a plugin's skills.
  "tools": [
    { "name": "search", "description": "Search the example corpus." },
    { "name": "fetch",  "description": "Fetch a document by id." }
  ]
}
```

Only `name` and `description` are strictly required; everything else has a
sensible default.

## Presentation (optional)

By default an MCP server is listed under the **MCP Servers** category with a
generic icon. To customise it, add an entry under `mcp` in
[`scripts/store-meta.json`](../scripts/store-meta.json):

```jsonc
{
  "mcp": {
    "example-server": {
      "name": "Example Server",
      "icon": "🔌",
      "accent": "orange",
      "category": "MCP Servers",
      "tagline": "One-line pitch shown on the card.",
      "tags": ["mcp", "search"],
      "highlights": ["What it does well", "Another selling point"]
    }
  }
}
```

## Publishing

Commit and push to `main`. The `publish` workflow regenerates
`docs/catalog.json`, commits it if it changed, and deploys the site. Nothing
else to do.

> MCP servers are listed on the **website** but are deliberately **not** written
> into `.github/plugin/marketplace.json`, because that manifest describes
> Copilot CLI *plugins*. MCP servers are configured by the user's MCP client.
