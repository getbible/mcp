# Changelog

## 2.1.1 — 2026-09-14

- Use https://getBible.net as the project website in documentation, package and plugin metadata, and MCP server discovery.
- Point MCP usage documentation and HTTP discovery at https://getBible.net/mcp.
- Keep the official Streamable HTTP service at https://mcp.getbible.net/ and retain configurable host URLs.

## 2.1.0 — 2026-09-14

- Add bounded dictionary-index lookup with exact identifiers, accent-insensitive matching and pagination.
- Guide AI clients through dictionary relationships and commentary coverage, introductions and ranges.
- Advertise the supplied GetBible icon and description through standard MCP server metadata.
- Distinguish local contract discovery from public API calls in tool annotations.
- Include portable plugin metadata, branding, review test cases and a concrete publishing handoff.
- Add an opt-in, bounded endpoint probe and protocol-level study workflow checks.
- Preserve all nine API contracts, native responses, uncached reads and the existing main-merge release gate.

## 2.0.2 — 2026-09-14

- Require a verified PR merge into `main` before production publication; remove manual release dispatch.
- Retry temporarily missing or incomplete PyPI metadata after upload while preserving strict artifact identity checks.
- Keep the 2.0.1 runtime, all nine API contracts and the configurable domain-root HTTP endpoint.

## 2.0.1 — 2026-09-14

- Allow consuming applications to serve Streamable HTTP directly at the domain root.
- Keep protocol discovery and tool/resource behavior consistent at configurable HTTP paths.
- Clarify host-selected endpoint paths in generic client and library documentation.
- Document the official public endpoint, search-equivalent anonymous limits and optional token access.

## 2.0.0 — 2026-09-14

- Cover all nine upstream OpenAPI contracts: scripture/query/search v2 and v3, and dictionaries,
  commentaries and public bookmarks v1.
- Use the stable official Python MCP SDK 2.2.0 and the 2026-07-28 protocol specification.
- Expose the `/mcp` protocol endpoint through import-safe library factories and retain stdio parity.
- Default scripture convenience tools to upstream v3; support upstream v2 through explicit selection.
- Add API discovery, operation inspection and contract-validated execution, including search GET
  and read-only POST, text indexes, schemas, catalogs and checksum routes.
- Preserve native v3 tokens, spans, paragraph markers and source data throughout retrieval.
- Apply a 30-day caching ceiling and source HTTP freshness; keep query/search uncached.
- Distinguish scripture SHA-1 from study/topic SHA-256 manifests and search source metadata.
- Publish complete OpenAPI resources and nine static snapshots, with a reviewed refresh workflow.
- Keep the PyPI library, client guidance and package publishing in this repository; consuming
  applications own infrastructure setup and lifecycle.

## 1.0.0 — 2026-07-15

- Introduced scripture v2 tools, documentation resources and an integration-design prompt.
- Added read-only MCP access, scripture consistency checks and translation-rights guidance.
- Established PyPI publishing, Registry metadata and package/protocol validation.
