# Change Protocol

## Change contract

Write this before editing:

```text
Evidence:
  artifact IDs, phase, device, accounting domain, observed delta/path
Owner:
  class/component/native callsite/buffer producer/system policy
Mechanism:
  why memory stays allocated, reachable, resident, swapped, or repeatedly recreated
Change:
  smallest ownership/lifecycle/budget correction
Expected result:
  exact same-domain metric or object/resource lifecycle change
Risks:
  correctness, latency, jank, cache hit rate, I/O/network, CPU, battery, compatibility
Validation:
  tests plus matching before/after/cooldown evidence
Rollback:
  measurable condition and reversible action
```

## Java and lifecycle

- Remove or shorten the incorrect strong-reference path.
- Prefer lifecycle-aware registration/unregistration and scoped ownership.
- Preserve necessary state across configuration and process recreation.
- Avoid substituting weak/soft references when explicit ownership is required.
- Verify the object is expected to die, the path is gone, repeated loops stay bounded, and behavior still works.

## Cache and collections

- Establish owner, max policy, eviction, hit rate, refill cost, and product SLA.
- Change budget or key/value lifecycle rather than deleting all caching.
- Verify memory, hit rate, latency, I/O/network, and behavior together.

## Native/JNI

- Pair allocation and release at the real owner boundary.
- Preserve JNI global/local reference and thread-attachment rules.
- Handle error, cancellation, reinitialization, and process teardown paths.
- Verify callstack allocation deltas, VMA/page behavior, symbols, sanitizer signals, and functional tests.

## Graphics/WebView/IPC

- Release the producing/owning resource at the valid rendering/lifecycle boundary.
- Preserve asynchronous consumer/compositor use and fence/order semantics.
- Verify visual correctness, jank, buffer counts/owners, Graphics/memtrack/DMA-BUF direction, and recreation.

## System/background behavior

- Reduce unnecessary work, timers, wakeups, cached state, or restart loops through product lifecycle design.
- Do not tune LMKD/freezer/swap globally to hide an app owner issue.
- Treat platform/OEM changes as device-policy work with staged rollout and rollback.

## Anti-patterns

- calling `System.gc()` as a leak fix;
- adding an arbitrary MB threshold as the only remediation;
- clearing every cache on every lifecycle callback;
- calling `Bitmap.recycle()` without proving ownership and API/library semantics;
- converting strong references to weak/soft references without lifecycle design;
- freeing native memory from a non-owner or while another thread/consumer can use it;
- combining unlike metrics to claim improvement;
- accepting a one-run decrease without reproducibility.
