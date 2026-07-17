# MCP Registry publishing

The repository includes `server.json` for the official MCP Registry using the custom-domain
namespace:

```text
net.getbible/mcp
```

The Registry is currently a preview service, so validate the file with the current publisher before
every publication. The metadata advertises the public Streamable HTTP service and the
`getbible-mcp` PyPI package for stdio installation.

## Publish the remote service

After `https://mcp.getbible.net/v2` is publicly deployed and verified:

1. Install the current official `mcp-publisher` binary.
2. Validate `server.json` with the publisher's current command.
3. Authenticate using the Registry's DNS/domain flow for `getbible.net`.
4. Publish `server.json`.
5. Search the Registry API for `net.getbible/mcp` and inspect the returned metadata.

Official documentation:

- https://modelcontextprotocol.io/registry/about
- https://modelcontextprotocol.io/registry/quickstart
- https://modelcontextprotocol.io/registry/remote-servers

## stdio package discovery

The official Registry does not host code and does not treat a Git repository as an installable
package registry. The included package entry becomes valid after `getbible-mcp==1.0.0` is published
to PyPI:

1. Publish the built `getbible-mcp` package through the release workflow documented in
   [PUBLISHING.md](PUBLISHING.md).
2. Keep this exact verification marker in `README.md`:

   ```text
   <!-- mcp-name: net.getbible/mcp -->
   ```

3. Keep this entry in the `packages` array in `server.json` synchronized with the release version:

   ```json
   {
     "registryType": "pypi",
     "identifier": "getbible-mcp",
     "version": "1.0.0",
     "transport": {"type": "stdio"}
   }
   ```

4. Validate and publish the Registry metadata.

Do not publish `server.json` before its matching public PyPI release and remote MCP endpoint exist;
Registry ownership or reachability verification may fail.
