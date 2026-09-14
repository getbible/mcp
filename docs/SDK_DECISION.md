# Language and MCP SDK decision

## Decision

Maintain one Python MCP server using the stable official Model Context Protocol Python SDK 2.2.0,
implementing the 2026-07-28 protocol specification. Publish its
Python package for local stdio use and expose the same implementation as an embeddable ASGI library.
JavaScript and PHP integrations use compatible MCP clients or call the existing REST APIs.
This repository does not publish separate npm or Composer packages.

## Why

The workload is asynchronous HTTP, JSON and schema validation. Python fits the package's existing
implementation. Sharing one server object gives stdio and HTTP the
same schemas, validation, tools, resources and behavior, without maintaining three language-specific
implementations of the API and cache contracts.

MCP is a protocol rather than a requirement to install a server package in each caller's language.
A client library must implement initialization and capability negotiation before calling tools;
a generic REST request to the MCP endpoint is insufficient. For an application that only needs
scripture data, the underlying REST endpoints remain a valid direct integration.

## Version boundaries

| Version | Meaning |
|---|---|
| Python MCP SDK 2.2.0 | The stable official protocol library pinned in the dependency files |
| `getbible-mcp` 2.0.0 | This server's package release |
| `/mcp` path | The MCP protocol endpoint, independent of upstream versions |
| Tool `api_version` | The upstream contract: v3 by default or explicit v2 for scripture conveniences; v1 for study/bookmarks |

Dependency pins and API snapshots are independently reviewed release inputs. Evaluate SDK upgrades
on a branch and require stdio, Streamable HTTP, schema, resource, prompt, consistency and packaging
checks before changing the pin. Do not tie an upstream API version change to an SDK major version.

Official references:

- [MCP SDKs](https://modelcontextprotocol.io/docs/sdk)
- [Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Stable Python SDK 2.2.0 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0)
- [Python SDK documentation](https://py.sdk.modelcontextprotocol.io/)
