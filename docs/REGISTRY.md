# MCP Registry publishing

The repository includes `server.json` for the official MCP Registry with the custom-domain name
`net.getbible/mcp`. Its package entry identifies `getbible-mcp` on PyPI and the stdio transport.
No hosted service is advertised before an application actually publishes and verifies one.

## Package discovery

The Registry describes installable packages; it does not host package code. After
`getbible-mcp==2.0.0` is published to PyPI:

1. Keep the verification marker `<!-- mcp-name: net.getbible/mcp -->` in `README.md`.
2. Keep the package version in `server.json` synchronized with the published release.
3. Validate the metadata using the current official `mcp-publisher` binary.
4. Authenticate using the Registry's domain ownership flow for `getbible.net`.
5. Publish the metadata and inspect the resulting `net.getbible/mcp` entry.

The package entry is:

```json
{
  "registryType": "pypi",
  "identifier": "getbible-mcp",
  "version": "2.0.0",
  "transport": {"type": "stdio"}
}
```

Do not advertise an unpublished package version. Package publication is described in
[PUBLISHING.md](PUBLISHING.md).

Official references:

- [About the Registry](https://modelcontextprotocol.io/registry/about)
- [Publisher quickstart](https://modelcontextprotocol.io/registry/quickstart)
- [Remote server metadata](https://modelcontextprotocol.io/registry/remote-servers)
