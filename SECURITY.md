# Security policy

Security fixes target the supported package release. Report vulnerabilities privately through
[GitHub security advisories](https://github.com/getbible/mcp/security/advisories/new).

## Package boundaries

The package exposes reviewed read-only GetBible operations. Search POST performs retrieval, not a
write. There are no shell, filesystem, arbitrary-URL, personal-account or database tools. Publisher
content is returned as data and must not be interpreted as instructions.

Implemented controls include:

- Schema validation against bundled OpenAPI contracts, including version-specific bounds.
- Operator-configured service destinations; tool callers cannot supply a host or HTTP method.
- Encoded path segments, explicit supported methods and no automatic redirect following.
- Bounded response sizes, request timeouts and parallel hash checks.
- MCP Host/Origin validation, read-only annotations and stateless HTTP support.
- No stored API responses or persisted credentials.
- Before/after Bible version checks and conservative HTTP cache advice with a 30-day ceiling.

Configuration and custom HTTP clients are trusted application inputs. Embedding applications own
their network boundary, authentication policy and resource lifecycle. Keep origin validation enabled
and do not expose private service destinations through a public MCP application without an explicit
access policy. Returned upstream documents and Location headers remain untrusted data.

## Dependencies

Production dependencies are pinned. Review updates in branches and run schema, client, lifecycle,
stdio, Streamable HTTP, type and package checks before releasing a new package.
