# Contributing

Changes must preserve stdio and Streamable HTTP parity, complete coverage of the nine reviewed
GetBible API contracts, native response data and the 30-day cache ceiling.

Before submitting a change:

```bash
./scripts/check
```

Tool additions require:

- a clear read-only purpose or an explicit security review for side effects;
- strict typed input and structured output;
- fixed upstream destinations rather than arbitrary URLs;
- documentation in the MCP description, static tool catalog, and examples;
- unit tests and both-transport discovery tests;
- HTTP freshness metadata and service-specific hash guidance for cacheable data.

The package contains reusable MCP capabilities and generic usage documentation. Infrastructure
configuration and deployment instructions belong to the application consuming this package.

Do not commit virtual environments, generated distributions, credentials, production environment
files, or server logs.
