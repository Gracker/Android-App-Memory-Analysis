# meminfo-first / smaps-supplemental report contract

Use this contract whenever a valid `dumpsys meminfo` artifact exists. When the
context contains `evidence.accounting_ledger.status=available`, consume that
ledger instead of rebuilding category arithmetic from prose.

## Primary navigation

1. Keep the original meminfo main-table row order. Do not replace it with a
   six-number overview, a sorted TOP list, or an intent-specific subset.
2. For every row, report the meminfo PSS and available Private Dirty,
   Private Clean, SwapPss, RSS, and Heap Size/Alloc/Free values.
3. Attach same-category smaps PSS, SwapPss, mapping count, allocator subtype,
   and relevant top mappings as supplemental evidence when that detail is
   available. The AI context intentionally omits raw VMA names; inspect the
   authorized local smaps artifact when mapping names are needed. smaps does
   not overwrite the meminfo value.
4. Preserve `EGL mtrack`, `GL mtrack`, and other memtrack rows as
   `not-comparable`. They are driver/HAL attribution, not missing smaps VMAs.
5. Preserve the meminfo `TOTAL` row. If total reconciliation is available,
   state the exact formula and delta. Do not add HPROF retained bytes, system
   DMA-BUF totals, or another accounting domain.
6. Include Dalvik Details after the main table when present. Treat these as
   drill-down rows under Dalvik/Dalvik Other rather than additional process
   totals.

## Interpretation order

For each row:

- state the observed meminfo values and artifact binding;
- attach the smaps row evidence and comparison status;
- explain a difference as a possible collection-time or classification
  boundary until identity and phase prove otherwise;
- use VMA names to choose the next investigation branch, not to invent an
  allocation callsite or owner;
- keep threshold-driven concerns separate from leak or root-cause claims.

After every row is represented, lead the diagnosis toward the rows relevant to
the user symptom. A focused narrative may be short, but it must not silently
drop the other meminfo rows from the quantitative result.

## Missing or ambiguous pairing

- With meminfo but no smaps, still return the complete meminfo row ledger and
  state that row-level mapping evidence was not collected.
- When the ledger status is `unavailable`, the artifact did not yield a complete
  main table. Keep App Summary as a bounded fallback and request a full
  `dumpsys meminfo -d` capture; do not fabricate the missing rows.
- When the ledger status is `ambiguous`, do not pair one meminfo file with one
  of several smaps files by filename guess. Resolve package, PID, scenario, and
  phase first.
- With smaps only, use the smaps-only view and request meminfo as the familiar
  Android category baseline; do not fabricate meminfo rows.
