# Connecting MCP clients

## Choose a transport

Use Streamable HTTP when an application provides a remote MCP service and your client supports
outbound HTTPS. Use stdio when the client launches a local server process. Both expose the same
GetBible tools, resources and prompts across all nine upstream API contracts.

The protocol endpoint is `/mcp`. The application providing that endpoint determines its public base
URL; this package does not assume a particular host. Scripture tools default to upstream v3, with v2
available explicitly through `api_version`.

## Python, JavaScript and PHP

| Use case | Integration |
|---|---|
| AI host with remote MCP support | Configure the application's published `/mcp` URL as a Streamable HTTP server. |
| Python, JavaScript or PHP application acting as an MCP client | Use a supported client library to initialize that endpoint, discover tools and call them. |
| AI host requiring a local executable | Install the Python package and launch `getbible-mcp --transport stdio`. |
| Ordinary application needing scripture or study data | Call the published REST APIs using the desired upstream OpenAPI contract. |

This repository publishes one Python MCP package. It does not publish npm or Composer packages.
MCP clients perform JSON-RPC initialization and capability negotiation before calling tools. `/mcp`
is not a REST endpoint accepting arbitrary scripture paths or HTTP query parameters.

## Streamable HTTP

Use the full MCP URL supplied by the application. The exact protocol path is `/mcp`, without a
trailing slash. Client libraries handle initialization, protocol headers and `tools/list`; a normal
web-browser GET is not a sufficient protocol test.

Read the advertised tool schemas after initialization. Start with `discover_apis`, inspect a chosen
service/version through `describe_api_operation`, and execute its operation with
`call_api_operation`. Use the convenience scripture/search tools for common tasks.

## stdio from a repository clone

Install into an isolated environment:

```bash
git clone https://github.com/getbible/mcp.git getbible-mcp
cd getbible-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps .
```

Configure the MCP host to launch the installed `getbible-mcp` executable with arguments
`["--transport", "stdio"]`. Use its absolute path: the host may have a restricted `PATH` and a
different working directory.

The server writes MCP messages to stdout. Application logs and diagnostics go to stderr because
writing them to stdout would corrupt the protocol stream.

## PyPI installation

For an isolated per-user command:

```bash
pipx install getbible-mcp
command -v getbible-mcp
```

Use the returned executable path in the MCP host's command configuration.

## MCP Inspector

Inspect a local installation with:

```bash
npx @modelcontextprotocol/inspector \
  .venv/bin/getbible-mcp --transport stdio
```

For a remote application, select Streamable HTTP and enter its published `/mcp` URL. Initialize,
list tools, inspect schemas, read documentation and OpenAPI resources, retrieve the prompt and make
representative calls. The [examples](../site/v2/examples.md) cover v3 scripture, grouped references,
search GET/POST, dictionaries, commentaries and bookmarks.
