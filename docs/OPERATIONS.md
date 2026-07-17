# Operations

## Status and health

```bash
sudo ./manage status
systemctl status getbible-mcp.service
curl --fail http://127.0.0.1:3100/healthz
curl --fail https://mcp.getbible.net/healthz
```

`/healthz` is a liveness check for the MCP process. It deliberately does not call the upstream APIs;
otherwise a temporary API or network problem would cause the process supervisor to restart a healthy
MCP service.

## Logs

```bash
sudo ./manage logs
journalctl -u getbible-mcp.service --since today
```

stdio mode must keep stdout reserved for MCP messages. When debugging a locally launched stdio
server, capture stderr through the MCP host rather than adding print statements.

## Releases and rollback

List releases and the active target:

```bash
readlink -f /opt/getbible-mcp/current
ls -1 /opt/getbible-mcp/releases
```

`manage install` and `manage update` automatically restore the former target if the new systemd
service or health check fails.

For an intentional manual rollback:

```bash
sudo ln -s /opt/getbible-mcp/releases/RELEASE-ID /opt/getbible-mcp/.current-next
sudo mv -Tf /opt/getbible-mcp/.current-next /opt/getbible-mcp/current
sudo systemctl restart getbible-mcp.service
sudo ./manage status
```

Only remove old release directories after confirming that no rollback will need them.

## Configuration changes

Edit the persistent environment file:

```bash
sudoedit /etc/getbible-mcp.env
sudo systemctl restart getbible-mcp.service
sudo ./manage status
```

Important controls:

- `GETBIBLE_MCP_WORKERS`: Uvicorn worker count; default 2.
- `GETBIBLE_MCP_REQUEST_TIMEOUT`: upstream timeout; default 20 seconds.
- `GETBIBLE_MCP_MAX_RESPONSE_BYTES`: hard upstream response limit; default 32 MiB.
- `GETBIBLE_MCP_MAX_PARALLEL_HASH_CHECKS`: concurrency for grouped/check operations; default 10.
- `GETBIBLE_MCP_ALLOWED_HOSTS`: DNS-rebinding Host allowlist.
- `GETBIBLE_MCP_ALLOWED_ORIGINS`: allowed Origin values when that header is present.

The release manager preserves an existing Nginx site file because Certbot edits it in place. When a
release changes the Nginx template, review the diff and merge the relevant location/security changes
without removing Certbot's TLS directives:

```bash
diff -u /etc/nginx/sites-available/mcp.getbible.net.conf \
  /opt/getbible-mcp/current/deploy/nginx/sites-available/mcp.getbible.net.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Monitoring

Monitor at least:

- systemd active state and restart count;
- `/healthz` externally over HTTPS;
- Nginx 4xx/5xx rates and request latency;
- MCP process memory and file descriptors;
- upstream timeouts and HTTP errors in the journal;
- disk use under `/opt/getbible-mcp/releases`;
- TLS certificate renewal.

The application itself stores no scripture, sessions, secrets, or database state. Backup the Git
repository and `/etc/getbible-mcp.env`; releases can be rebuilt from source and the dependency lock.

## Capacity

The workload is primarily concurrent outbound HTTP. Two async workers are a conservative default.
Measure before raising worker count because every worker has its own connection pool and memory.

If a single host becomes insufficient, use multiple local ports or hosts behind an Nginx upstream.
This server is stateless, so requests do not require sticky routing.
