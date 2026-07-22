# Intent Routing

## Quick triage

Start with valid meminfo plus device context. Identify the leading Android category, then choose exactly one owner branch. Use smaps/panorama as support, not as permission to guess.

## Java leak

Require an HPROF or equivalent complete retained-path report. A complete LeakCanary log can serve as the owner-path branch when it preserves the GC Root, reference path, leaking states, suspect edge, target/build/phase, and surrounding context; a notification, count, screenshot, OOM, or isolated marker cannot. Confirm lifecycle expectation, business owner, repeated scenario, and cooldown. Use meminfo to relate object findings to page direction without equating their sizes.

## Native memory

Use meminfo for direction and smaps/showmap for allocator/VMA location. Require heapprofd, malloc_debug, sanitizer evidence, or app allocation tracking to name a callsite. Treat DirectByteBuffer wrappers as one ownership path, not all native memory.

Use native allocator/JNI failure logs to choose the next branch and time window. Do not infer the allocating callsite from the failure line or abort site.

## Graphics/WebView/IPC

Correlate meminfo, gfxinfo, smaps, DMA-BUF/memtrack, process roles, WebView provider, and buffer lifecycle. Avoid duplicate counting across producer, consumer, importer, and compositor views.

Treat graphics allocation errors and screenshots as visible failure context. Preserve dimensions, format, filters, process roles, and the matching buffer/page evidence before assigning ownership.

## System pressure

Align `/proc/meminfo`, PSI, ZRAM/swap, scheduling/Perfetto, LMKD/system logs, and ApplicationExitInfo. Separate page shortage, reclaim cost, swap-in recovery, kill policy, and app allocation growth.

## Regression

Require before/after or multi-phase evidence with matching device, scenario, process semantics, collection mode, and cooldown. Report absolute delta, relevant same-ledger percentage, and whether the change survives exit/cooldown. A single after snapshot is not a regression.
