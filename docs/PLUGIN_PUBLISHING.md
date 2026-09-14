# Publish the GetBible plugin

Use [getBible.net](https://getBible.net) as the project website and
[getBible.net/mcp](https://getBible.net/mcp) as the MCP usage documentation page.

The GetBible plugin connects ChatGPT and Codex to the existing official MCP endpoint,
**https://mcp.getbible.net/**. The server supplies the tools, schemas and API contracts. This
repository supplies the plugin package, study guidance and review materials. API hosting remains
the responsibility of the API operator.

Use the complete URL above: the endpoint is `/`, with no `/mcp` or API-version suffix. Select
Streamable HTTP and no authentication for public access. The plugin does not require an XML
manifest, a browser page, a JavaScript server or a custom UI.

These materials target MCP package **2.1.1**, including the dictionary-index search tool. They
are prepared for the publisher; public submission still requires final policy information,
the matching live runtime, and recorded client tests.

## What to hand to the publisher

| File | Use |
| --- | --- |
| [`plugin/getbible/`](../plugin/getbible/) | Plugin metadata and its remote MCP connection; see its README for supported local clients. |
| [`submission.json`](../plugin/getbible/submission.json) | Ready-to-copy listing text, connection values and remaining operator actions. This is GetBible handoff data, **not an OpenAI upload schema**. |
| [`test-cases.json`](../plugin/getbible/test-cases.json) | Reproducible user prompts, expected tool behavior and acceptance criteria. These are test plans, not recorded passes. |
| [`assets/logo.png`](../plugin/getbible/assets/logo.png) | GetBible logo for the listing. |
| [`STUDY_WORKFLOWS.md`](STUDY_WORKFLOWS.md) | How scripture, lexical data, commentaries and public bookmarks fit together. |

The listing name is **GetBible**. Use the descriptions and starter prompts from `submission.json`.
The service is free for anonymous use, subject to the existing public limits. HTTP 429 means the
client should honor `Retry-After`. Administrators issue tokens for approved access; public plugin
testing does not require a token.

## 1. Confirm publisher-owned information

Choose the verified GetBible publisher identity in the correct OpenAI organization. The submitter
needs **Apps Management: Write**. Use a project eligible for MCP submissions; OpenAI currently
requires global rather than EU data residency. See its
[MCP review requirements](https://developers.openai.com/plugins/deploy/app-review).

The repository's software license is not a hosted-service privacy policy or permission to
redistribute every translation. Ask the API operator to confirm the public policy accurately
describes request processing, traffic logging, retention, access and contact procedures. The
MCP package's lack of an API-response cache does not mean the hosted service keeps no logs.
Do not insert an assumed retention period or claim that no data is collected. Before submission,
the public privacy policy must state the actual retention timelines, recipients and user controls.
Keep public policy, terms and support details consistent with the publisher. See OpenAI's
[privacy and support requirements](https://developers.openai.com/plugins/app-guidelines#privacy).

The proposed [privacy policy](PRIVACY.md) and [service terms](TERMS.md) need owner review.
Their proposed public URLs in `submission.json` become available after merge. Complete the privacy
policy's outstanding hosting facts and remove its draft status only after approval. Verify both
public documents before copying their URLs into the portal. Do not submit a draft policy.

`submission.json` identifies the remaining publisher work under `operator_actions`. Complete those
items after the owner supplies the information. Select a suitable current directory category and
only the countries the publisher approves.

Use the existing [GetBible support site](https://git.vdm.dev/getBible/support) from the repository's
homepage metadata. GitHub issues are disabled on this repository. Confirm that the support site
is accessible to users and reviewers, and provide a private contact route for token and privacy
requests; do not direct those requests into a public discussion.

## 2. Test the connection in ChatGPT

In ChatGPT, open **Settings → Security and login → Developer mode**. Open **Plugins**, use the
plus button, and create a connection named **GetBible** with the official URL and no
authentication. Inspect its discovered tools. Availability of developer mode depends on the
account and workspace. Start a new conversation with GetBible enabled and run the test cases.
Record prompts, selected tools, arguments, results and errors. After server metadata changes,
refresh the development connection and retest. See OpenAI's
[connection and testing guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).

For an independent protocol check, use the [client guide](CLIENTS.md) and MCP Inspector. A browser
request to `/` can remain open because it receives an event stream. A successful `/healthz`
response identifies the running package; `/readyz` checks application startup. Neither proves
that every upstream service works.

Once the API operator confirms package 2.1.1 is live, run the supplied endpoint check from an
activated development environment with this repository's dependencies installed:

```bash
python scripts/check_endpoint.py --expect-version 2.1.1
python scripts/check_endpoint.py --expect-version 2.1.1 --upstreams
```

The first command checks discovery and protocol behavior. The second explicitly adds representative
read-only calls across all nine API contracts. Record their actual outcomes alongside the ChatGPT
tests; a successful representative check is not proof that every API operation was exercised.

The development evidence available when these materials were prepared was a successful public
`tools/list` response exposing 12 tools and a successful v3 KJV John 3:16 query. The latter
included native tokens and spans. This does not establish ChatGPT acceptance, directory approval,
or successful dictionary, commentary, bookmark and v2 requests. Run and record those cases before
claiming them as tested.

After the 2.1.1 upgrade, discovery should expose 13 tools, including `search_dictionary_entries`.

The study instructions and resources come from the MCP server; this package contains no bundled
skills or UI. Repeat the study cases with the connection enabled and confirm that the discovered
tools and instructions work together. A successful raw call alone does not test model selection.
The plugin README also describes optional local package testing in supported Codex clients.
Use the direct developer connection above for ChatGPT testing; importing a local package is not
a substitute for registering the public MCP plugin through the portal.

## 3. Complete the directory draft

Open the plugin submission portal linked in OpenAI's
[submission guide](https://developers.openai.com/plugins/deploy/submission). Choose **Create plugin →
With MCP → Universal**. Enter `https://mcp.getbible.net/` and no authentication. Copy the listing
materials, upload the logo, add starter prompts and test evidence, then use **Scan Tools**.
Check every reported schema and annotation before continuing.

This submission has no skill bundle, UI component or UI screenshots to upload. The scan imports
the MCP server's instructions and tool metadata.

GetBible's tools should advertise `readOnlyHint: true` and `destructiveHint: false`.
`discover_apis` and `describe_api_operation` read bundled contracts and should set
`openWorldHint: false`; tools that request public APIs should set it to `true`.
A read-only search POST does not create content. Review the per-tool justifications against
OpenAI's [annotation requirements](https://developers.openai.com/plugins/app-guidelines#correct-annotation).
The generic `call_api_operation` tool intentionally handles different native response shapes;
review its operation-specific contract through `describe_api_operation`.

### Domain verification

If the portal requests verification, give its exact token to the API operator. The required
challenge path is `/.well-known/openai-apps-challenge`; the response must be the single token.
The challenge may use the MCP hostname or the allowed parent origin `https://getbible.net`.
Choose the parent only after the operator confirms it can serve that challenge. See the
[domain-verification requirements](https://developers.openai.com/plugins/deploy/submission#domain-verification).

The MCP protocol endpoint does not publish that verification file. Keep challenge hosting in
the API operator's deployment work; do not put the token in the Python package or replace the
MCP URL with a challenge URL.

## 4. Submit, then publish

Attach recorded results for the cases in `test-cases.json`; the set includes at least five positive
and three negative cases. Resolve failed cases and missing publisher information. Review the
listing and policy attestations, then submit for review. After approval, the publisher chooses
when to publish to the shared ChatGPT/Codex Plugins Directory. Submission alone does not publish.
See the [publishing flow](https://developers.openai.com/plugins/deploy/submission#public-publishing-flow).

## Maintain the published plugin

The plugin package is **1.0.1**; the matching MCP runtime is **2.1.1**. Their versions and
the directory listing have separate lifecycles. A merged code
change can release a new PyPI package; the API operator decides when the hosted runtime uses it.
A changed OpenAPI contract can alter the advertised operation schemas without changing the
public endpoint URL.

Published tools and server instructions are a reviewed snapshot. Rescan changed metadata,
submit a new plugin version and publish after approval. Refreshing a development connection
does not update the public listing. Compatible server fixes can reach live tool calls without
a new listing review. Keep previously published contracts working while adding new capabilities;
deploying an incompatible schema can break installed clients before review completes. Changing
the MCP origin requires a new plugin; a path change uses a new version. See OpenAI's
[metadata-version rules](https://developers.openai.com/plugins/deploy/app-review#how-published-mcp-metadata-versions-work).

Keep the review evidence tied to the tested package version and plugin revision. Recheck the
affected cases when tools, schemas, instructions, study guidance or access behavior change.
Do not describe the OpenAPI synchronization workflow as automatically publishing a new directory
version.
