FROM python:3.14-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt pyproject.toml README.md LICENSE ./
COPY src ./src
RUN /opt/venv/bin/python -m pip install -r requirements.txt \
    && /opt/venv/bin/python -m pip install --no-deps .

FROM python:3.14-slim-bookworm

LABEL io.modelcontextprotocol.server.name="net.getbible/mcp"

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GETBIBLE_MCP_BIND_HOST=0.0.0.0 \
    GETBIBLE_MCP_BIND_PORT=3100

COPY --from=builder /opt/venv /opt/venv
USER 65532:65532
EXPOSE 3100
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3100/healthz', timeout=3)"]
CMD ["uvicorn", "getbible_mcp.server:app", "--host", "0.0.0.0", "--port", "3100", "--workers", "2"]
