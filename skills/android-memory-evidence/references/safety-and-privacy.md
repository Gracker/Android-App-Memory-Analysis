# Safety and Privacy

## Raw artifact boundary

- Keep raw files local by default.
- Generate a context containing type, status, size, SHA-256, normalized summaries, and provenance before deciding whether an AI needs raw content.
- Do not embed arbitrary raw text or binary content in a prompt merely because it exists in a dump directory.

## HPROF

Assume an HPROF can contain credentials, URLs, user input, business objects, caches, identifiers, and complete relationship graphs.

Before capture or upload, establish:

- user and organizational authorization;
- debuggable/profileable/root permission boundary;
- capture trigger and maximum frequency;
- pause, storage, and timeout budget;
- encrypted storage and access control;
- retention/deletion policy;
- incident or dataset identifier without exposing user identity;
- approved external processor, if any.

Compression or an extension change is not redaction. Removing visible strings is not necessarily safe or tool-compatible.

## Perfetto and logs

Trace packets, ftrace events, atrace names, log buffers, process lists, and command lines can also expose user or business data. Capture only enabled sources needed for the hypothesis and bound the time window.

## Production

- Prefer platform-supported production profiling and aggregate counters.
- Gate Android 17 OOM/anomaly triggers and memory-limiter semantics by API level.
- Never enable invasive debug allocators, forced GC, or unrestricted heap dumps as a silent production fix.
- Treat access/permission failures as evidence about collection feasibility, not evidence that the memory category is absent.
