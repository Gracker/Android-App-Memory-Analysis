# Evidence Protocol

## Evidence order

1. Record target identity: package, PID, process role, user/profile, API level, build fingerprint, page size, device/RAM bucket, timestamp, scenario, phase, loops, cooldown, and tool switches.
2. Capture low-perturbation page evidence before diagnostic tools.
3. Choose a branch from the page evidence.
4. Add owner evidence only for that branch.
5. Capture exit/cooldown phases with the same identity and collection mode.
6. Generate derived reports after raw artifacts are stable.

## Artifact roles

| Artifact | Answers | Does not answer | Typical perturbation |
|----------|---------|-----------------|----------------------|
| `dumpsys meminfo --local` | Process page/category direction | Object or native callsite owner | Low |
| detailed `dumpsys meminfo` | Page categories plus runtime detail | Natural state after its GC-sensitive collection path | Medium |
| smaps/showmap | VMA/page location | Native allocation callsite | Low |
| HPROF | Managed objects, roots, reference paths | Total process pages, graphics, all native owners | High |
| heapprofd | Sampled native allocation callstacks | Exact unprofiled allocation total | Medium |
| gfxinfo | Rendering resources and frame statistics | Complete GPU/DMA-BUF ownership | Low |
| DMA-BUF | Shared buffer size/owner when exposed | Java lifecycle or complete driver-private memory | Low |
| `/proc/meminfo` | Whole-device page state | Pressure duration or process owner | Low |
| PSI | Time stalled on memory pressure | Which app allocation caused the pressure | Low |
| ZRAM/swap | Compressed swap state and I/O | Exact user-visible latency by itself | Low |
| ApplicationExitInfo | Exit reason, time, last sampled memory | Exact memory at the death instant | Low |
| Perfetto | Timeline, counters, scheduling, optional allocation profiles | Facts not enabled in the trace config | Medium |
| Android/logcat/LeakCanary logs | Timestamped detector reports, warnings, failures, pressure and kill events | Complete owner, trend, or accounting impact from one line | None to low |
| QA screenshots | Visible report state, values, filters, warnings, and chart window | Hidden/cropped content, machine-readable values, or trend outside the visible window | None |

`smaps` and `showmap` are alternatives for locating page cost by mapping. They are not substitutes for a symbolized native allocation profile when the question asks for a C/C++ owner or callsite. The repository helper records heapprofd data, but its generic `--analyze` summary does not render allocation callstacks; inspect the heap-profile track in Perfetto with matching symbols.

## Status rules

- `ok`: recognized content; still verify phase/target identity.
- `missing`: no candidate supplied or discovered.
- `empty`: zero-byte artifact.
- `invalid`: content does not match the claimed type.
- `permission_denied`: preserve as an acquisition result, then use a documented alternative.
- `command_failed`: distinguish unsupported command from transient device/process failure.
- `unreadable`: local access problem; do not infer device behavior.

## Partial-input response

Always separate:

- facts supported now;
- facts the input cannot support;
- plausible alternatives, explicitly labeled as hypotheses;
- the smallest next artifact that distinguishes those alternatives;
- exact prerequisites, Android version, permissions, perturbation, and command placeholders.

Never ask only for “more logs.” Name the artifact and the question it resolves.

For supplied QA logs or screenshots, read `qa-artifacts.md`. Multiple files remain distinct artifacts. The generated context contains bounded log signals and screenshot metadata, not raw lines, OCR text, or pixels; inspect the authorized originals before making a claim.

A recognized phase file is not automatically comparison-complete. The context marks it inadequate for leak/regression claims until timestamp, package, PID, process role, user/profile, scenario, phase, loops, cooldown, collection mode, and perturbation are represented; a comparison report is still required to establish a delta.

## Consistency checks

- Compare package and PID in meta, meminfo, reports, directory name, and user statement.
- Reject before/after comparison when PID/process role, phase, collection mode, device, or scenario differs without an explicit normalization argument.
- Do not add HPROF retained bytes to PSS/RSS/memtrack.
- Do not count the same GraphicBuffer through multiple owners or ledgers.
- Do not treat `SwapPss` as proof that the swap device is ZRAM; check `/proc/swaps`.
- Do not treat a process disappearance as LMKD; check exit reason and system timeline.
- Do not treat an OOM stack as the allocation owner, a LeakCanary notification as the full retained path, or a screenshot filename as visible evidence.
