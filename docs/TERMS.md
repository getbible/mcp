# GetBible MCP access terms

**Proposed terms for owner review.** The publisher must approve these terms and confirm the public
administrator contact route before removing this draft status and using this URL in a submission.

These terms describe access to the official GetBible MCP endpoint at https://mcp.getbible.net/.
The service retrieves public Bible text and study material. Its tools are read-only: they do not
create accounts, alter translations or write personal bookmarks.

Public access is free and requires no account or token. Anonymous traffic is subject to the same
default limits as GetBible search. Respect HTTP 429 responses and `Retry-After`; reduce request
volume rather than attempting to evade limits. Administrators may restrict abusive traffic and
issue tokens for approved access. Tokens apply only to the endpoint approved by the administrators.
See the [usage policy](../site/v2/usage-policy.md).

Translation and study-module rights remain with their respective publishers. Read and preserve
the copyright, license, attribution and provenance supplied by the catalogs and content. Availability
through the service does not grant unrestricted redistribution rights. The repository's
GPL-2.0-or-later software license applies to the MCP implementation and does not relicense scripture,
dictionary definitions or commentary text.

The MCP package does not cache upstream results and recommends leaving query and search results
uncached. If your application retains eligible API content, honor upstream HTTP freshness and a
maximum of 30 days, validate available hashes, invalidate changed scopes and refresh expired data.
An unchanged hash does not extend an expired response. See the
[cache contract](../site/v2/cache-policy.md).

Identify the translation and study sources used. Distinguish source text from generated explanation;
dictionary links do not automatically mean synonyms, and commentary represents its author's work.
Report missing coverage and service errors accurately rather than presenting invented content as
an API response.

The [privacy notice](PRIVACY.md) describes request processing and operational records. General
technical support starts at the [GetBible support site](https://git.vdm.dev/getBible/support).
Do not post credentials or personal information in public discussions. Before publication, the operator must confirm
the administrator contact route for private access-token requests and approve the final terms.
