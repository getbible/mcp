# Contributing

Changes must preserve stdio and Streamable HTTP parity, GetBible API V2 compatibility, and the
mandatory cache-integrity policy.

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
- a cache-hash design for any scripture payload that can be persisted.

Do not commit virtual environments, generated distributions, credentials, production environment
files, or server logs.

