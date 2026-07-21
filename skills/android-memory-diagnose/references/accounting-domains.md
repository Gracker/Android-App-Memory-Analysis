# Accounting Domains

## Domain map

| Domain | Typical values | Main question | Common invalid comparison |
|--------|----------------|---------------|---------------------------|
| `process-pages` | PSS, RSS, Private Dirty/Clean, SwapPss | What page cost is attributed to this process? | Adding HPROF retained bytes |
| `android-summary` | Java Heap, Native Heap, Code, Graphics, Private Other, System | Which Android category is the first branch? | Treating category labels as specific owners |
| `runtime-heap` | Heap Size, Alloc, Free | What space does ART/allocator manage or retain? | Treating Alloc as resident physical pages |
| `object-graph` | shallow size, retained size, instances, GC roots | Which managed objects are alive and reachable? | Calling retained size process PSS |
| `allocation-profile` | sampled allocations by callstack | Which callsites allocate/retain native memory? | Assuming samples equal exact total pages |
| `memtrack` | EGL/GL/Other mtrack | What driver/HAL memory is attributed? | Blindly adding to DMA-BUF or process pages |
| `cross-process-buffers` | DMA-BUF, GraphicBuffer, Surface owner | Who owns/imports shared buffers? | Counting each importer as a unique allocation |
| `system-pages` | MemAvailable, cache, slab, anon, swap totals | What is the whole-device page state? | Inferring app owner from a device total |
| `pressure-time` | PSI some/full windows | How long are tasks stalled by shortage? | Treating a single snapshot as a duration |
| `process-exit` | reason, time, importance, last RSS/PSS | Why and when did a process exit? | Treating last sample as exact death state |
| `timeline` | scheduling, counters, events | What sequence connected allocation, reclaim, stall, and exit? | Inferring disabled trace sources |

## Comparison gate

Before comparing values, require:

- same domain and definition;
- same units;
- same target process role;
- same device/API/vendor policy unless normalized;
- same scenario and phase;
- same collection mode and perturbation;
- stable PID semantics;
- matching inclusion/exclusion of swap and memtrack.

If a comparison crosses domains, provide an official formula or state that the values are contextual, not additive.

## Frequent traps

- Heap Alloc can exceed current heap PSS.
- HPROF retained size can exceed or overlap process page summaries.
- App Summary Graphics can combine smaps and memtrack components.
- `Unknown` means an Android classification stopped, not that the VMA has no owner.
- `System` in App Summary is not `system_server` memory.
- `SwapPss` does not identify ZRAM without `/proc/swaps`.
- RSS/PSS from ApplicationExitInfo is a prior sample and may be zero.
