# Publishing `getbible-mcp` to PyPI

The repository publishes automatically from a GitHub Release after every validation job succeeds.
It uses PyPI Trusted Publishing, so no password or long-lived PyPI API token is stored in GitHub.

## Chosen identities

```text
GitHub repository:  getbible/mcp
PyPI project:       getbible-mcp
Python command:     getbible-mcp
MCP Registry name:  net.getbible/mcp
Workflow file:      publish-pypi.yml
GitHub environment: pypi
```

## One-time GitHub setup

1. Create the public repository at `https://github.com/getbible/mcp`.
2. Push this project to its default `main` branch.
3. In **Settings → Environments**, create an environment named exactly `pypi`.
4. For completely automatic publishing, do not add required reviewers to that environment.
   Adding reviewers is an optional security gate, but it makes publication wait for approval.
5. Protect `main` and require the `test` workflow before merging changes.

Do not create a `PYPI_TOKEN` repository secret. The workflow does not read one.

## One-time PyPI setup

If `getbible-mcp` has never been published, create a pending publisher from the PyPI account
publishing page. Enter these values exactly:

```text
PyPI project name:  getbible-mcp
Owner:              getbible
Repository:         mcp
Workflow name:      publish-pypi.yml
Environment name:   pypi
```

PyPI creates the project on the first successful trusted publication. If the name is already owned
by someone else, stop before releasing and choose a new package name consistently in
`pyproject.toml`, `server.json`, the workflow URL, and this documentation.

For an existing PyPI project, add the same publisher under that project's publishing settings.

## Prepare a release

Every public version declaration must match:

- `pyproject.toml`
- `src/getbible_mcp/__init__.py`
- `server.json`
- `site/v2/manifest.json`

Verify locally, using the intended release tag:

```bash
.venv/bin/python scripts/verify_release.py v1.0.0
./scripts/check
```

Commit and push the release changes. In GitHub, create a Release targeting the tested commit and use
a tag matching the project version, normally `v1.0.0`. Publishing the GitHub Release starts the
`publish-pypi` workflow.

## What the workflow does

1. Calls the reusable test workflow.
2. Tests Python 3.11, 3.12, and 3.13.
3. Runs Ruff, strict mypy, all unit and protocol tests, and distribution builds.
4. Builds the production Docker image.
5. Verifies the release tag against all public version declarations.
6. Builds a fresh wheel and source distribution from the tagged commit.
7. Stores those exact files as one workflow artifact.
8. Gives only the final publishing job `id-token: write` permission.
9. Publishes the verified artifact through `pypa/gh-action-pypi-publish` and PyPI OIDC.

If any earlier job fails, the publishing job cannot start.

## Verify the publication

After the workflow succeeds:

```bash
python3 -m venv /tmp/getbible-mcp-test
/tmp/getbible-mcp-test/bin/python -m pip install getbible-mcp==1.0.0
/tmp/getbible-mcp-test/bin/getbible-mcp --version
```

The normal end-user installation can then be:

```bash
pipx install getbible-mcp
```

PyPI versions are immutable. Never attempt to replace an already published version; correct the
problem, increment the project version, and publish a new GitHub Release.

## MCP Registry follow-up

`server.json` already contains the PyPI stdio package and the hosted Streamable HTTP endpoint. After
both are publicly available, validate and publish that file as described in [REGISTRY.md](REGISTRY.md).
