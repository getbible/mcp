# GetBible MCP

<!-- mcp-name: net.getbible/mcp -->

[![test](https://github.com/getbible/mcp/actions/workflows/test.yml/badge.svg)](https://github.com/getbible/mcp/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/getbible-mcp.svg)](https://pypi.org/project/getbible-mcp/)
[![License: GPL v2+](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)

Production-ready Model Context Protocol access to GetBible API V2 over both standard MCP transports:

- **Streamable HTTP** for the public service at `https://mcp.getbible.net/v2`
- **stdio** for developers who install the package and let an AI client launch it locally

Both transports expose exactly the same tools, resources, prompts, validation, and scripture-cache
integrity rules.

## What the two transports mean

| Transport | Who runs the server? | How a client connects | Best use |
|---|---|---|---|
| Streamable HTTP | GetBible operates it continuously | URL: `https://mcp.getbible.net/v2` | Easiest public integration; users install nothing |
| stdio | The developer installs this package locally | Client launches `getbible-mcp --transport stdio` | Desktop tools, private environments, local process control |

stdio does not create a public endpoint. The MCP host starts the command as a child process and
exchanges JSON-RPC messages over standard input and output. That local process still reads scripture
from the public GetBible API.

Streamable HTTP is a persistent remote service. Nginx accepts HTTPS connections and proxies only the
exact MCP endpoint to the Python application.

```text
                         ┌─ api.getbible.net/v2
AI client ── MCP ──> GetBible MCP
                         └─ query.getbible.net/v2

Remote: AI client ─ HTTPS ─ Nginx ─ Streamable HTTP process
Local:  AI client ─ stdio ─ locally installed process
```

## Public API access and translation rights

GetBible API V2 is open worldwide. It requires no registration, account, API key, authentication,
subscription, payment, or request quota. The supplied Nginx configuration likewise adds no
per-address request throttle. The underlying static API is built for heavy public use and already
serves millions of requests per day.

Each translation's return data includes its applicable copyright information, including in the
translation catalog. Applications must preserve and honor that metadata. GetBible does not add a
second copyright layer to scripture text, and this repository's GPL license applies only to the MCP
software—it does not relicense translations or override publisher terms.

Correct API use is conditioned on honoring the hash-validation cycle described below. An
integration that keeps cached scripture without revalidating its hashes is not complying with the
GetBible API usage agreement.

## MCP capabilities

### Tools

| Tool | Purpose |
|---|---|
| `list_translations` | Discover translations, copyright information, metadata, scope, and catalog hashes. |
| `list_books` | Discover numbered and localized book names and hashes. |
| `list_chapters` | Discover chapters and chapter hashes. |
| `get_scripture` | Retrieve a complete translation, book, or chapter with a consistency-checked hash. |
| `query_verses` | Retrieve selected/grouped verses and participating chapter hashes. |
| `get_hash` | Read one translation, book, or chapter `.sha` value. |
| `get_hash_manifest` | Read bulk checksum data for scheduled cache sweeps. |
| `check_for_updates` | Compare stored hashes and receive exact invalidation actions. |

All tools are read-only, non-destructive, and idempotent.

### Resources

- `getbible://docs/api-v2`
- `getbible://docs/cache-policy`
- `getbible://docs/usage-policy`

### Prompt

- `design_getbible_integration`

## Mandatory scripture-cache integrity

GetBible builds follow upstream CrossWire modules. When scripture is corrected upstream, the hash
for the affected scope changes. Every downstream integration that caches scripture must:

1. Store the payload with the hash for its exact translation, book, or chapter scope.
2. Revalidate that hash at least weekly.
3. Invalidate the changed scope and every cached descendant.
4. Fetch fresh scripture and its hash into temporary storage.
5. Atomically replace the stale record.

`get_scripture` checks the matching `.sha` value before and after retrieving JSON. If a build changes
mid-request, it retries once instead of returning mismatched data and hash. `query_verses` resolves
and returns the hash for every participating chapter, checking the complete hash set before and after
the query; unresolved results are marked non-cacheable.

See [site/v2/cache-policy.md](site/v2/cache-policy.md).

## Quick local stdio setup

Clone the repository and build an isolated environment:

```bash
git clone https://github.com/getbible/mcp.git getbible-mcp
cd getbible-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps .
```

Configure the MCP client with the absolute executable path:

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

Do not wrap or embed Python inside a shell configuration. The client launches the installed Python
entry point directly.

See [docs/CLIENTS.md](docs/CLIENTS.md) for stdio, remote, Docker, and Inspector examples.

## Quick production deployment

The included deployment assumes Ubuntu, Nginx, systemd, and DNS for `mcp.getbible.net`.

```bash
sudo apt-get install python3-venv rsync nginx certbot python3-certbot-nginx
sudo ./manage install
sudo certbot --nginx -d mcp.getbible.net
sudo ./manage status
```

The deployment is release-based. A new release and virtual environment are fully built before the
`/opt/getbible-mcp/current` symlink changes. If the service or health check fails, the manager restores
the previous release automatically.

Nginx serves the root discovery page and `/v2/` documentation directly. Only the exact, no-trailing-
slash endpoint `/v2` is proxied to the MCP process.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) before the first installation.

## Downloadable packages, TestPyPI, and PyPI

Every successful `test` workflow run builds and smoke-tests one wheel and one source distribution.
GitHub keeps them for 30 days in the run's **Artifacts** section under the name
`python-package-distributions`. This includes runs started manually from **Actions → test → Run
workflow**, so a package can be downloaded and tested without publishing anything.

The separate `publish-testpypi` workflow is manually triggered and publishes the same validated
artifacts to TestPyPI. Production publishing can be started manually or by publishing a GitHub
Release; `publish-pypi.yml` repeats the full validation, verifies the requested release tag, and
publishes the validated artifacts to PyPI.

TestPyPI uses Trusted Publishing. Production PyPI reads the project or account token only from the
`PYPI_MCP_TOKEN` GitHub Actions secret in the protected `pypi` environment. See
[docs/PUBLISHING.md](docs/PUBLISHING.md) for the download, TestPyPI, secret setup, and production
release procedures.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
chmod +x manage scripts/check
./scripts/check
```

The suite covers API validation, hash-consistent reads, grouped-reference hashes, MCP schema
discovery, Streamable HTTP initialization, stdio initialization, static JSON validation, and CLI
behavior.

## Repository layout

```text
src/getbible_mcp/       Python MCP implementation
site/                   Nginx-served discovery and V2 documentation
deploy/                 systemd, Nginx, and environment templates
docs/                   Architecture, deployment, clients, operations, security
tests/                  Unit and protocol integration tests
manage                  Pure Bash deployment and lifecycle manager
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Client connections](docs/CLIENTS.md)
- [Operations and updates](docs/OPERATIONS.md)
- [Security model](SECURITY.md)
- [Testing](docs/TESTING.md)
- [Publishing to PyPI](docs/PUBLISHING.md)
- [MCP Registry publishing](docs/REGISTRY.md)

## Versioning

The remote `/v2` endpoint and all files under `site/v2/` are permanently scoped to GetBible API V2.
Breaking MCP tool or output changes require an explicitly versioned migration. Compatible security,
validation, description, and reliability fixes may be released within this contract.

## License

The GetBible MCP software is licensed under the [GNU General Public License, version 2 or later](LICENSE).
Scripture translations remain governed by the copyright information returned for each translation;
the software license does not relicense scripture content.
