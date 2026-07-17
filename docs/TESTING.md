# Testing and release validation

## Local environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
chmod +x scripts/check manage
./scripts/check
```

The check script is Bash-only and invokes separate Python tools. It does not embed Python inside a
shell script.

## Test coverage

The suite validates:

- translation path injection is rejected;
- declared and streamed response-size limits;
- correct translation, book, and chapter URL construction;
- `.sha` format validation;
- before/after hash consistency and the one-retry behavior;
- grouped verse reference-to-book mapping and chapter hash collection;
- non-cacheable behavior for unresolved query references;
- strict scope validation;
- MCP tool discovery and expected schemas;
- Streamable HTTP initialization at exact `/v2`;
- stdio subprocess initialization and tool discovery;
- root/static manifest and OpenAPI JSON syntax;
- public access, usage-policy, and PyPI package metadata;
- CLI defaults and version output;
- Bash syntax for `manage` and `scripts/check`;
- release-tag consistency and fail-closed version mismatch behavior;
- tokenless PyPI publishing only after the reusable validation workflow;
- wheel and source-distribution builds.

Unit tests use an in-memory HTTP transport and do not depend on live GetBible availability. This keeps
CI deterministic. A staging deployment should additionally call representative live endpoints and
MCP tools before production promotion.

## Local release gate

Before deploying a release:

1. Run `./scripts/check`.
2. Run `.venv/bin/python scripts/verify_release.py vX.Y.Z` for the intended tag.
3. Build and scan the container if Docker artifacts are published.
4. Start the HTTP service on a staging port.
5. Use MCP Inspector for initialization, tools, resources, prompts, and representative calls.
6. Confirm a whole chapter result carries the matching current `.sha` value.
7. Confirm a grouped query returns all participating chapter hashes.
8. Validate Nginx configuration with `nginx -t`.
9. Deploy using `sudo ./manage update` and verify public health.

Publishing a GitHub Release performs the complete validation again before PyPI upload; see
[PUBLISHING.md](PUBLISHING.md).
