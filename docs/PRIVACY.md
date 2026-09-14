# GetBible MCP privacy notice

**Proposed notice for owner review — not ready for directory submission.** The API operator must
complete the retention and contact information below, confirm the deployed behavior, and approve
this notice before removing this paragraph or submitting its URL as an adopted privacy policy.

## Service and information processed

This notice concerns the official GetBible MCP service at https://mcp.getbible.net/ and the GetBible
APIs it calls. Public access does not require an account. When an AI client invokes GetBible, the
service processes the tool name and supplied inputs, such as Bible references, search terms,
translation choices, dictionary identifiers or public topic identifiers. Those inputs are used
to retrieve the requested public content and return it to the client.

The MCP tools do not request a user's full conversation, personal documents or contacts. What an
AI application chooses to send is controlled by that application's connection and privacy settings.
Avoid including personal or confidential information in scripture searches and references.

The hosting infrastructure records traffic and operational information for service reliability,
usage reporting, rate limits and abuse investigation. This can include IP addresses, request paths,
user agents, timestamps, response status, duration, request identifiers, selected tools, upstream
service/version, translation, selected references or query inputs, and MCP client name/version.
The MCP telemetry component excludes complete
tool arguments, request bodies and credential values from its structured events. Upstream access
logs can nevertheless contain references and search terms in request URLs. An issued access token
is processed to apply its access rules; never include a token in a support issue.

## Processing and recipients

Requested lookup inputs are sent to the relevant GetBible API. Results are returned to the AI
client that made the request. GetBible administrators use the service's operational records to
operate and protect the infrastructure. The AI provider's handling of the conversation and returned
content is governed separately by its own policies. A privately hosted MCP instance has its own
operator and privacy practices.

**Owner completion required:** identify the responsible operator and any hosting, monitoring,
backup or support providers that receive personal data; state their roles and any applicable
cross-border processing arrangements. Confirm the purposes above against actual operations.

## Retention

The MCP Python package does not retain an upstream response cache. The maximum 30-day downstream
content-cache contract concerns copied API content; it is not a promise about access-log retention.

**Owner completion required:** state the deployed maximum retention for traffic records, operational
logs, archives/backups and support correspondence, how deletion works, and any documented exceptions.
The API engine's configurable defaults are not evidence of production settings. Include backup and
log exports in this review; a traffic database's pruning rule does not delete unrelated copies.
Publish explicit retention timelines before submission.

## Choices, requests and contact

Users can stop sending new requests by disabling or removing the GetBible connection in their AI
client. That does not itself erase existing operational records or the client's conversation history.
The AI provider manages deletion requests for its own records.

**Owner completion required:** publish a monitored private contact route and the procedure for
requesting access, correction or deletion of GetBible-held personal data, including applicable
exceptions and response handling. Identify the operator responsible for these requests. This
information must be usable by someone without a GetBible account.

General technical issues can be reported through the
[GetBible MCP issue tracker](https://github.com/getbible/mcp/issues). Issues are public: do not post
tokens, personal data or sensitive privacy requests there.
