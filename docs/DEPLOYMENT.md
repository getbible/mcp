# Production deployment on the existing GetBible Ubuntu/Nginx server

The MCP service can run beside the existing static API. It does not modify `/home/ubuntu/api`, the
scripture repositories, or their updater. It reads the same public API URLs as every other consumer.

## Resulting layout

```text
/opt/getbible-mcp/
├── current -> /opt/getbible-mcp/releases/<release-id>
└── releases/
    └── <release-id>/
        ├── .venv/
        ├── src/
        ├── site/
        └── deploy/

/etc/getbible-mcp.env
/etc/systemd/system/getbible-mcp.service
/etc/nginx/sites-available/mcp.getbible.net.conf
```

The application listens only on `127.0.0.1:3100`. Nginx is the only public listener.

## 1. DNS

Create the A and, if used, AAAA records for `mcp.getbible.net` and point them to the Nginx server.

## 2. Packages

```bash
sudo apt-get update
sudo apt-get install python3 python3-venv rsync nginx certbot python3-certbot-nginx
```

The manager uses virtual environments and never installs packages into Ubuntu's system Python. It
does not use `pip install --user`.

## 3. Clone the repository

```bash
git clone https://github.com/getbible/mcp.git /home/ubuntu/getbible-mcp
cd /home/ubuntu/getbible-mcp
chmod +x manage scripts/check
```

## 4. Review configuration

Review these files before installation:

```text
deploy/getbible-mcp.env
deploy/getbible-mcp.service
deploy/nginx/sites-available/mcp.getbible.net.conf
```

The initial environment file is installed once. Later repository updates do not overwrite
`/etc/getbible-mcp.env`, so local production settings are preserved.

The Nginx site file is also installed only when absent. Later updates preserve the live site file so
Certbot-managed certificate directives are never overwritten. Compare repository Nginx changes with
the live file manually before applying them.

## 5. Install

```bash
sudo ./manage install
```

The manager:

1. creates a locked-down `getbible-mcp` system user if needed;
2. copies the repository into a new timestamped release;
3. builds a release-specific Python virtual environment;
4. installs the locked production dependencies and application;
5. atomically changes the `current` symlink;
6. installs and validates systemd and Nginx configuration;
7. starts the MCP service;
8. waits for the local health check;
9. restores the previous release automatically if startup or health fails;
10. reloads Nginx only after validation and health succeed.

No application source is copied into the existing API directory.

## 6. TLS

On the first deployment:

```bash
sudo certbot --nginx -d mcp.getbible.net
sudo nginx -t
sudo systemctl reload nginx
```

Confirm Certbot's renewal timer using your normal server practice.

## 7. Verify

```bash
sudo ./manage status
curl --fail https://mcp.getbible.net/
curl --fail https://mcp.getbible.net/v2/manifest.json
curl --fail https://mcp.getbible.net/healthz
```

Test `https://mcp.getbible.net/v2` with MCP Inspector or another real MCP client. A plain browser GET
is not a valid protocol exchange.

## Updating

Pull the tested repository revision and deploy a new immutable release:

```bash
cd /home/ubuntu/getbible-mcp
git pull --ff-only
sudo ./manage update
```

Old releases are retained for inspection and manual rollback. See [OPERATIONS.md](OPERATIONS.md).

## Existing Nginx configuration

The repository installs a separate virtual host for `mcp.getbible.net`; it does not replace the
`api.getbible.net` or `query.getbible.net` configurations.

Nginx serves:

```text
/                      static discovery HTML
/manifest.json         static discovery JSON
/v2/                   static V2 documentation
/v2/*.json|md|txt      static machine and human documentation
/healthz               proxied liveness response
/v2                    exact MCP Streamable HTTP endpoint
```

The exact `/v2` block disables request and response buffering for MCP/SSE compatibility and retains
long read timeouts. Do not add an automatic slash redirect for this path.

## Alternative Docker deployment

The native systemd deployment is recommended on the existing GetBible server. Docker is supported
when isolation or portability is preferred:

```bash
docker compose up --build -d
curl --fail http://127.0.0.1:3100/healthz
```

Keep the same Nginx virtual host. The container binds only to host loopback through Compose.

## Uninstall and purge

Remove runtime integration while preserving releases and environment configuration:

```bash
sudo ./manage uninstall
```

Remove all releases and configuration explicitly:

```bash
sudo ./manage purge --yes
```
