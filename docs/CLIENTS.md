# Connecting MCP clients

## Official GetBible endpoint

Connect to **[https://mcp.getbible.net/](https://mcp.getbible.net/)** using **Streamable HTTP**.
In your AI application's MCP connection settings, enter that exact URL and give the connection
a name such as `GetBible`. No account or token is required for free public access. Do not append
`/mcp`, `/v2` or `/v3`.

The endpoint exposes Bible, reference-query and search APIs v2/v3, plus dictionaries,
commentaries and public bookmarks v1. After connecting, your client discovers the available
tools, documentation resources and integration prompt. Use `query_verses` for references,
`search_verses` for text searches, and `discover_apis` to explore the complete versioned API catalog.

For example, an application using the official Python MCP SDK can request a passage:

```python
import asyncio

from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with Client(
        streamable_http_client("https://mcp.getbible.net/"), cache=None
    ) as client:
        result = await client.call_tool(
            "query_verses",
            {"translation": "kjv", "references": "John 3:16", "api_version": "v3"},
        )
        print(result.structured_content)


asyncio.run(main())
```

The free endpoint uses the same anonymous limits as GetBible search. Handle HTTP `429`, wait
for the duration indicated by `Retry-After`, and reduce concurrent requests. Contact the GetBible
administrators to request a token for this or another GetBible endpoint. If issued one, configure
your MCP client's secure HTTP authentication settings to send `Authorization: Bearer <your-token>`.
Tokens are issued for individual endpoints; use them only with the endpoint approved by the
administrators. The [usage policy](../site/v2/usage-policy.md) lists the default limits.

For the public ChatGPT plugin, choose **no authentication**. The generic bearer-header option above
applies to clients that support custom credentials; it is not an OAuth connection or a ChatGPT
API-key sign-in flow. See the [plugin connection and publishing steps](PLUGIN_PUBLISHING.md).

## Choose a transport

Use Streamable HTTP when an application provides a remote MCP service and your client supports
outbound HTTPS. Use stdio when the client launches a local server process. Both expose the same
GetBible tools, resources and prompts across all nine upstream API contracts.

The official endpoint is `https://mcp.getbible.net/`. For another instance, use the complete URL
supplied by its operator. Its path may be `/`, `/mcp`, or another supported exact path; the library
does not require a particular hostname or path.
Scripture tools default to upstream v3, with v2 available explicitly through `api_version`.

## Python, JavaScript and PHP

| Use case | Integration |
|---|---|
| AI host with remote MCP support | Configure the application's published MCP endpoint URL as a Streamable HTTP server. |
| Python, JavaScript or PHP application acting as an MCP client | Use a supported client library to discover the endpoint's capabilities, list tools and call them. |
| AI host requiring a local executable | Install the Python package and launch `getbible-mcp --transport stdio`. |
| Ordinary application needing scripture or study data | Call the published REST APIs using the desired upstream OpenAPI contract. |

This repository publishes one Python MCP package. It does not publish npm or Composer packages.
Clients discover the server's supported protocol versions and capabilities before calling tools.
For protocol 2026-07-28, `server/discover` replaces the initialization handshake: each request carries
its protocol version and client capabilities in `_meta`. A compatible SDK supplies this metadata.
The MCP endpoint does not accept arbitrary scripture paths or HTTP query parameters as a REST API.

## Streamable HTTP

Use the full MCP URL supplied by the application exactly, including its path. Do not append `/mcp`,
an API version, or a trailing slash. The library factory defaults to `/mcp`, while hosts may select
`/` or another supported path. Client libraries handle discovery, protocol headers, request metadata and
`tools/list`; a normal web-browser GET is not a sufficient protocol test.

Read the advertised tool schemas after discovery. Start with `discover_apis`, inspect a chosen
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

For a remote application, select Streamable HTTP and enter its published MCP endpoint URL. Connect,
list tools, inspect schemas, read documentation and OpenAPI resources, retrieve the prompt and make
representative calls. The [examples](../site/v2/examples.md) cover v3 scripture, grouped references,
search GET/POST, dictionaries, commentaries and bookmarks.

## Verify a remote endpoint

From a clone with this project's development dependencies installed:

```bash
.venv/bin/python scripts/check_endpoint.py
.venv/bin/python scripts/check_endpoint.py --expect-version 2.1.0 --upstreams
```

The first check connects with the official MCP SDK, validates discovery and tool schemas, reads
the guides and nine bundled contracts, and retrieves the integration prompt. The second also
requires the requested runtime version and calls each service/version with representative data.
It checks native response schemas, returned scripture, provenance, cache limits and tool errors.
It does not exercise every upstream route or prove a directory submission will be accepted.

Pass `--url` with another operator's complete endpoint URL to test that instance. HTTPS is required
except for explicit loopback HTTP testing. An administrator-issued token, when needed, is read
from `GETBIBLE_MCP_TOKEN`; keep it out of command arguments, transcripts and committed files.
The public endpoint needs no token.

The probe makes sequential, bounded requests and stops on failure. It does not retry or run on
a schedule. An HTTP 200 with MCP `isError: true` is a failed lookup. Honor rate limits before
retrying a failed remote run. Use `--help` for timeout options.

A browser GET to the protocol endpoint can wait on an event stream. `/healthz` describes the
runtime; the hosting application's `/readyz`, where supplied, checks startup. Use actual MCP
calls to test functionality. Finally, run the [plugin test cases](../plugin/getbible/test-cases.json)
inside the intended AI client to verify that the model chooses and combines the tools correctly.
