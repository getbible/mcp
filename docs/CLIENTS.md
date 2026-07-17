# Connecting MCP clients

## Choose a transport

Use the public remote service when the MCP host supports Streamable HTTP and outbound HTTPS. It is
the simplest option because the user installs nothing.

Use stdio when the client expects a local server process, when the environment does not accept remote
MCP URLs, or when the operator wants the MCP process under local control.

Both choices call the same public GetBible APIs and expose the same MCP contract.

## Streamable HTTP

Configure the MCP client with this exact URL:

```text
https://mcp.getbible.net/v2
```

Do not append a trailing slash. `/v2/` is documentation, not the MCP protocol endpoint.

The MCP client performs initialization, capability negotiation, and `tools/list` automatically. A
normal web-browser GET is not a valid protocol test because MCP requests require the expected MCP
headers and JSON-RPC messages.

## stdio from a repository clone

Install into an isolated environment:

```bash
git clone https://github.com/getbible/mcp.git getbible-mcp
cd getbible-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps .
```

Generic MCP configuration:

```json
{
  "mcpServers": {
    "getbible": {
      "command": "/absolute/path/getbible-mcp/.venv/bin/getbible-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

Always use an absolute command path. The MCP host may start with a restricted `PATH` and a different
working directory.

The server writes MCP messages to stdout. Application logs and diagnostic output must never be sent
to stdout in stdio mode because they would corrupt the protocol stream.

## pipx installation from PyPI

For a machine-wide per-user command without manually managing a venv:

```bash
pipx install getbible-mcp
```

The client command is then the absolute path reported by `command -v getbible-mcp`.

## Docker stdio

Build once:

```bash
docker build -t getbible-mcp:1.0.0 .
```

Generic client configuration:

```json
{
  "mcpServers": {
    "getbible": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "getbible-mcp:1.0.0",
        "getbible-mcp", "--transport", "stdio"
      ]
    }
  }
}
```

The `-i` flag is mandatory because it keeps standard input attached.

## MCP Inspector

After installing the project's development dependencies, inspect stdio with:

```bash
npx @modelcontextprotocol/inspector \
  .venv/bin/getbible-mcp --transport stdio
```

For the remote service, open MCP Inspector and select Streamable HTTP with:

```text
https://mcp.getbible.net/v2
```

Use Inspector to initialize, list tools, inspect generated JSON Schemas, read both resources, retrieve
the prompt, and call representative tools.
