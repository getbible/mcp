# Testing and release validation

## Local environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps -e .
chmod +x scripts/check
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
- all nine packaged OpenAPI contracts and their declared operations;
- path/query parameter schemas, repeated arrays, read-only search POST and URL encoding;
- native v2/v3 scripture, query and search data preservation;
- query/search non-cacheable defaults and source HTTP freshness;
- 30-day retention ceiling, shorter freshness, Age, Expires and no-store;
- dictionary, commentary and bookmark operations, including introductions and text/hash responses;
- strict scope validation;
- MCP tool discovery and expected schemas;
- Streamable HTTP initialization at exact `/mcp`;
- stdio subprocess initialization and tool discovery;
- root/static manifest and OpenAPI JSON syntax;
- public access, usage-policy, and PyPI package metadata;
- CLI defaults and version output;
- Bash syntax for `scripts/check`;
- release-tag consistency and fail-closed version mismatch behavior;
- downloadable wheel and source artifacts only after Python validation;
- tokenless TestPyPI and protected-token PyPI publishing only after reusable validation;
- wheel and source-distribution builds.

Unit tests use an in-memory HTTP transport and do not depend on live GetBible availability. This keeps
CI deterministic. Optional live checks can verify representative public API calls without becoming
a requirement for local tests or package builds.

## Local release gate

Before publishing a package release:

1. Run `./scripts/check`.
2. Run `.venv/bin/python scripts/verify_release.py vX.Y.Z` for the intended tag.
3. Build the wheel and source distribution, and verify both contain the complete contract snapshots.
4. Verify library factories import without allocating a default client and expose both transports.
5. Use protocol tests or MCP Inspector to check initialization, tools, resources and prompts.
6. Confirm scripture consistency checks, native query/search data and source freshness in both API
   versions, including non-cacheable runtime results.
7. Confirm dictionary, commentary and bookmark coverage through the generic operation tools.

Every successful test run stores downloadable distributions for 30 days. Manual TestPyPI and
GitHub Release production publishing both perform the complete validation again; see
[PUBLISHING.md](PUBLISHING.md).
