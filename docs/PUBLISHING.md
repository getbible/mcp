# Testing and publishing `getbible-mcp`

The project has three deliberately separate package paths:

1. Every successful `test` run produces downloadable GitHub Actions artifacts without publishing.
2. A manually started `publish-testpypi` run validates and publishes to TestPyPI.
3. Publishing a GitHub Release validates and publishes to production PyPI.

Both indexes use Trusted Publishing, so GitHub stores no password or long-lived PyPI API token.

## Chosen identities

```text
GitHub repository:  getbible/mcp
PyPI project:       getbible-mcp
Python command:     getbible-mcp
MCP Registry name:  net.getbible/mcp
Test workflow:      test.yml
TestPyPI workflow:  publish-testpypi.yml
PyPI workflow:      publish-pypi.yml
Test environment:   testpypi
Release environment: pypi
```

## Download a package without publishing

Push a commit, or open **Actions → test → Run workflow** to start a manual build. After the run is
green:

1. Open the completed workflow run.
2. Find **Artifacts** at the bottom of the run summary.
3. Download `python-package-distributions`.
4. Extract the downloaded ZIP. It contains the `.whl` and `.tar.gz` files.

Test the wheel in a clean environment:

```bash
python3 -m venv /tmp/getbible-mcp-artifact
/tmp/getbible-mcp-artifact/bin/python -m pip install ./getbible_mcp-1.0.0-py3-none-any.whl
/tmp/getbible-mcp-artifact/bin/getbible-mcp --version
```

Artifacts are retained for 30 days. They appear on the Actions run, not in the repository's
**Packages** tab. A GitHub package registry entry is neither required nor useful for a normal PyPI
wheel.

## One-time GitHub setup

1. Create the public repository at `https://github.com/getbible/mcp`.
2. Push this project to its default `main` branch.
3. In **Settings → Environments**, create environments named exactly `testpypi` and `pypi`.
4. For completely automatic production publishing, do not add required reviewers to `pypi`.
   Reviewers are an optional security gate but make publication wait for approval.
5. Protect `main` and require the `test` workflow before merging changes.

Do not create a `PYPI_TOKEN` repository secret. The workflow does not read one.

## One-time TestPyPI setup

TestPyPI has separate accounts and configuration from production PyPI. Sign in at
`https://test.pypi.org/`, open the account publishing page, and create a pending GitHub publisher
with these exact values:

```text
TestPyPI project name: getbible-mcp
Owner:                 getbible
Repository:            mcp
Workflow name:         publish-testpypi.yml
Environment name:      testpypi
```

Then open **Actions → publish-testpypi → Run workflow**. The workflow repeats all validation,
builds and smoke-tests the distributions, and publishes only if every gate passes.

Verify from both indexes so runtime dependencies can come from production PyPI:

```bash
python3 -m venv /tmp/getbible-mcp-testpypi
/tmp/getbible-mcp-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  getbible-mcp==1.0.0
/tmp/getbible-mcp-testpypi/bin/getbible-mcp --version
```

Package versions are immutable on TestPyPI too. To test another upload after `1.0.0` exists there,
increment all version declarations before running the workflow again.

## One-time production PyPI setup

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

Do not configure `test.yml` as the publisher: PyPI does not accept a reusable workflow as the
Trusted Publisher identity. The top-level `publish-pypi.yml` workflow owns the OIDC publishing job.

## Prepare a production release

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

## What the production workflow does

1. Calls the reusable test workflow.
2. Tests Python 3.11, 3.12, 3.13, and 3.14.
3. Runs Ruff, strict mypy, and all unit and protocol tests.
4. Builds the production Docker image.
5. Builds and smoke-tests a fresh wheel and source distribution from the tagged commit.
6. Stores those exact files as one workflow artifact for 30 days.
7. Verifies the release tag against all public version declarations.
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
