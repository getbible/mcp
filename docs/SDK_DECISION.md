# Language and MCP SDK decision

## Decision

Use Python with the official Model Context Protocol Python SDK.

## Why

The MCP project currently classifies Python, TypeScript, C#, and Go SDKs as Tier 1. All official SDKs
support tools, resources, prompts, local transports, and remote transports. TypeScript therefore has
no industry-support advantage for this service.

Python is the most suitable operational fit because:

- GetBible already deploys on Ubuntu behind Nginx.
- the workload is HTTP, JSON, validation, and I/O rather than CPU-intensive processing;
- virtual environments give clean dependency isolation from Ubuntu's system Python;
- systemd and Uvicorn provide a small, familiar production service;
- the same package can be launched directly over stdio by local MCP clients.

Go would also be technically sound, but it would add implementation and maintenance cost without a
meaningful operational benefit for this particular proxy-and-validation workload.

## SDK release selection

The repository pins `mcp==1.28.1`, the current stable production line when this release was built.
The Python SDK's 2.x line is prerelease software and its own maintainers state that it should not yet
be used in production.

The Python SDK version and GetBible API version are unrelated:

- `mcp==1.28.1` identifies the Python protocol library release.
- `/v2` identifies the GetBible API and MCP contract exposed by this repository.

When the Python SDK publishes a stable 2.x release, evaluate it on a separate branch. Do not change
the dependency pin until stdio, Streamable HTTP, tool-schema, resource, prompt, cache-integrity, and
deployment tests all pass.

Official references:

- https://modelcontextprotocol.io/docs/sdk
- https://github.com/modelcontextprotocol/python-sdk
- https://py.sdk.modelcontextprotocol.io/

