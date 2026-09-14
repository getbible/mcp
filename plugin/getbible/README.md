# GetBible plugin package

GetBible provides read-only Bible retrieval, reference lookup, scripture search, dictionaries,
commentaries and public study topics through **https://mcp.getbible.net/**. Public access is free,
rate limited and requires no account. Use the exact root URL with Streamable HTTP.

This package prepares the connection and listing metadata. It does not assert that GetBible is
already approved or listed in the public Plugins Directory. Follow the
[publisher handoff](https://github.com/getbible/mcp/blob/main/docs/PLUGIN_PUBLISHING.md) for the concrete remaining steps.

## Package contents

- `plugin.json`: portable Agent Plugins manifest with OpenAI presentation metadata.
- `mcp.json`: public remote MCP connection, without embedded credentials.
- `.codex-plugin/plugin.json` and `.mcp.json`: matching compatibility metadata for older hosts.
- `assets/`: original GetBible branding supplied by the maintainers.
- `submission.json`: listing copy and operator actions; not an official upload format.
- `test-cases.json`: seven positive and three negative client acceptance cases.

The plugin package version, initially **1.0.0**, is independent of the Python runtime version.
These materials target MCP **2.1.0**. A PyPI release does not deploy the API or publish a directory
listing. Proposed privacy and terms links require completed, approved public policies before
submission; see the handoff. The server supplies study instructions and documentation resources.
There are no bundled skills, custom widgets, install scripts or additional server processes.

## Test the connection

In ChatGPT, enable developer mode, open Plugins and add the official URL with no authentication.
Run the supplied cases in a new conversation with GetBible enabled. This direct connection is the
primary ChatGPT test; no assigned connection ID or legacy XML manifest is needed in this package.
If separately packaging a registered ChatGPT connection for a local installation, use the ID
actually assigned to it rather than inventing an `.app.json` mapping.

For a local Codex plugin test, copy this complete directory to `plugins/getbible` in a trusted
test repository. Add this entry to that repository's `.agents/plugins/marketplace.json`:

```json
{
  "name": "getbible-local",
  "interface": {"displayName": "GetBible local test"},
  "plugins": [{
    "name": "getbible",
    "source": {"source": "local", "path": "./plugins/getbible"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Education"
  }]
}
```

Keep any existing marketplace entries. The source path is relative to the test repository root.
Restart the desktop client, select that local marketplace and install GetBible. Enable its MCP
server and test in a new conversation. The marketplace authentication policy is an installation
setting; this public MCP connection itself has no credentials. This local test does not publish
to the public directory. The [official packaging guide](https://developers.openai.com/plugins/build/plugins)
defines the format and supported host behavior.

## Branding

`assets/logo.png` is the supplied 230 × 230 PNG; `assets/composer-icon.png` is the supplied 96 × 96
PNG. Both are unchanged originals. The Python wheel includes the same logo for standard MCP
server discovery, so it does not depend on an external image URL. These assets identify GetBible;
they do not grant permission to present an unrelated service as the official GetBible service.
If a submission surface requests a larger image, obtain a higher-resolution original from the
maintainers. Do not claim that enlarging this file adds image detail.
