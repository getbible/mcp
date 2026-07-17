# Security policy and threat model

## Supported release

Security fixes are applied to the current production release. Dependency upgrades must preserve both
transports and pass the complete test suite before deployment.

## Reporting

Report suspected vulnerabilities privately through the GetBible support process rather than opening
a public issue containing exploit details:

https://github.com/getbible/mcp/security/advisories/new

## Public-service model

GetBible MCP exposes only public, read-only scripture data. It has no write tools, user accounts,
database, filesystem tool, shell tool, secret-bearing responses, or arbitrary URL fetcher. Anonymous
remote access is therefore intentional.

If future tools access private data, accept writes, or act for a user, implement the MCP authorization
specification before publishing those tools. A shared static bearer token is not a substitute for a
proper authorization design.

## Implemented controls

- Fixed allowlisted upstream API bases
- Strict translation-character and numeric-bound validation
- No arbitrary URL tool input
- Redirect rejection
- Upstream timeouts and response-size limits
- Bounded parallel hash checks
- DNS-rebinding Host and Origin validation in the MCP SDK
- Loopback-only application listener
- Nginx TLS boundary and MCP request-body safety limit
- Non-root service account and hardened systemd sandbox
- Read-only, non-destructive MCP tool annotations
- Locked production dependency versions
- Stateless application with no persisted credentials
- Before/after hash checks to avoid mismatched scripture and version tokens

## Nginx and proxies

Preserve the original `Host` and scheme headers exactly as provided in the deployment configuration.
Do not disable Origin validation to solve a client configuration error. Add a verified required origin
to `/etc/getbible-mcp.env`, restart the service, and test it deliberately.

The supplied Nginx configuration does not impose per-address throttling. GetBible API V2 and this
public MCP service require no account, API key, or usage quota. If operational abuse controls become
necessary later, base them on observed traffic and document them without presenting them as API
licensing conditions.

## Dependency maintenance

The Python MCP SDK is pinned below its next major version. Review upstream security notices, create a
test branch for dependency updates, regenerate the lock, and run linting, typing, unit tests, both
protocol transports, package builds, and a staging deployment before production.
