# Testing and publishing `getbible-mcp`

The project has three deliberately separate package paths:

1. Every successful `test` run produces downloadable GitHub Actions artifacts without publishing.
2. A manually started `publish-testpypi` run validates and publishes to TestPyPI.
3. A manual `publish-pypi` run or published GitHub Release validates and publishes to production
   PyPI.

TestPyPI uses Trusted Publishing. Production PyPI uses the protected `PYPI_MCP_TOKEN` Actions
secret.

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

Create `PYPI_MCP_TOKEN` as a GitHub Actions **secret**, preferably inside the protected `pypi`
environment. Do not add the token as a plain Actions variable.

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

1. Create the protected GitHub environment named exactly `pypi`.
2. Add an environment secret named exactly `PYPI_MCP_TOKEN`.
3. For the first publication, use a PyPI token that is permitted to create the `getbible-mcp`
   project. An account-scoped token is normally required because a project-scoped token cannot be
   created before the project exists.
4. After `1.0.0` creates the project, replace the environment secret with a token scoped only to
   `getbible-mcp`.

The secret value must be the complete PyPI token, normally beginning with `pypi-`. If the package
name is already owned by someone else, stop before publishing and choose a new name consistently in
`pyproject.toml`, `server.json`, the workflow URL, and this documentation.

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

Commit and push the release changes. For an immediate publication, open **Actions → publish-pypi →
Run workflow**, enter `v1.0.0`, and run it from `main`. Alternatively, create a GitHub Release
targeting the tested commit with the tag `v1.0.0`; publishing the Release starts the same workflow.

## What the production workflow does

1. Calls the reusable test workflow.
2. Tests Python 3.11, 3.12, 3.13, and 3.14.
3. Runs Ruff, strict mypy, and all unit and protocol tests.
4. Builds the production Docker image.
5. Builds and smoke-tests a fresh wheel and source distribution from the tagged commit.
6. Stores those exact files as one workflow artifact for 30 days.
7. Verifies the release tag against all public version declarations.
8. Exposes `PYPI_MCP_TOKEN` only to the final publishing action.
9. Publishes the verified artifact through `pypa/gh-action-pypi-publish`.

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
