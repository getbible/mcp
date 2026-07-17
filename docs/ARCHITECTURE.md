# Architecture

## Components

### Nginx

Nginx is the public boundary. It handles:

- TLS certificates and HTTPS
- the root discovery page
- all static files below `/v2/`
- exact routing of `/v2` to the MCP application
- a small MCP request-body safety limit, without API keys, quotas, or per-address throttling
- long response/SSE-compatible proxy settings

The trailing slash is meaningful:

- `/v2` is the MCP Streamable HTTP protocol endpoint.
- `/v2/` is the static human-readable documentation page.

The MCP specification assigns both POST and GET semantics to the same Streamable HTTP endpoint, so
Nginx must not serve an HTML page or redirect GET requests at exact `/v2`.

### Python MCP process

The official stable Python MCP SDK supplies JSON-RPC parsing, initialization, capability negotiation,
tools, resources, prompts, schemas, stdio, and Streamable HTTP.

The service runs as a stateless ASGI application. Two Uvicorn workers are used by default. The work
is I/O-bound: each tool validates arguments, constructs an allowlisted GetBible path, and retrieves
static JSON or SHA content. No database or persistent server state is required.

### GetBible APIs

The MCP process reads only these fixed bases:

```text
https://api.getbible.net/v2
https://query.getbible.net/v2
```

Callers never supply an arbitrary URL. Translation identifiers are restricted to safe abbreviation
characters, book/chapter values are bounded integers, redirects are rejected, responses are limited
in size to protect the MCP process, and requests have timeouts. These local safeguards are not
GetBible API usage quotas: the upstream API is public and has no authentication or request limits.

## Transport parity

The Python server object defines all MCP capabilities once. The stdio CLI and Streamable HTTP ASGI
application are different transports around that same object. There is no duplicate tool
implementation and therefore no intentional behavior difference.

## Hash-consistent scripture retrieval

For a complete translation, book, or chapter:

```text
read scope SHA
      │
      v
read scope JSON
      │
      v
read scope SHA again
      │
      ├─ unchanged ─> return JSON + SHA
      └─ changed   ─> retry once; otherwise return a tool error
```

For Query API results, the server resolves each reference through the translation's book mapping,
uses KJV names as the documented fallback, retrieves participating chapter hashes concurrently with
a limit, verifies that the hash set remains unchanged across the Query API read, and marks the result
non-cacheable if any reference remains unresolved.

## Scaling

The remote process is stateless and read-only. Normal scaling options are:

1. Increase Uvicorn workers on the existing host.
2. Run several service instances on different local ports and use an Nginx upstream group.
3. Run the container on several nodes behind a load balancer.

Because source API files are static and the server retains no MCP session state, no shared database
or session store is required by this implementation.
