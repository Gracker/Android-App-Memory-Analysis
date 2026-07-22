# Analysis Iteration Protocol

Use this protocol whenever the folder or request refers to an earlier analysis, the user is dissatisfied, or QA adds, changes, or removes material.

## Establish the baseline

1. Rescan the entire current handoff directory. Do not scan only the files described as new.
2. Locate the old conclusion in this order:
   - the current conversation or task history;
   - each `previous_analysis_report` listed in `evidence.analysis_history`;
   - the request, support level, subject, and artifact snapshot summarized from each `previous_ai_context`.
3. Check `evidence.analysis_history.case_identity`, then confirm that the old and current analyses refer to the same package, process role, build, device bucket, scenario, and relevant phases. If stable identity differs, report a new case boundary instead of presenting a direct revision; if PID or phase differs, explain comparability before carrying claims forward.
4. Treat the old conclusion as derived claims. It is context to review, not raw evidence and not ground truth.

If the request declares a prior analysis but no old conclusion is available in the conversation or files, finish the folder inventory and state the evidence boundary, but obtain the old conclusion before claiming how the conclusion changed.

## Choose the mode

| Mode | Use when | Required behavior |
|------|----------|-------------------|
| `initial` | No prior analysis applies, including an explicit request to ignore discovered history | Build a fresh evidence and claim ledger. Keep old artifacts as inventory only and require `baseline_applied=false`. |
| `reanalysis` | The user challenges or rejects the prior reasoning | Rebuild the current claim ledger independently, then compare it with the old claims. Do not merely paraphrase the old answer. |
| `supplement` | The user wants to extend a still-usable baseline or evidence changed without a challenge | Propagate every added, changed, and missing artifact through the affected claims. Preserve a claim only when its evidence fingerprint and case identity remain valid. |
| `reanalysis-with-new-evidence` | The old reasoning is challenged and the evidence set materially changed | Perform the independent reanalysis and the full evidence-delta propagation. |
| `clarification-required` | Prior analysis exists, the evidence is unchanged, and the request does not distinguish redo from extension | Inventory may continue, but ask the user to choose reanalysis or supplement before presenting a final diagnosis. |

An explicit user choice wins. Automatic routing is evidence for workflow selection, not permission to invent the user's goal.

## Interpret the evidence delta

`evidence.analysis_history.evidence_delta` compares the newest recognized context snapshot with the current rescan by path, artifact type, status, size, and SHA-256 when available.

- `added`: absent from the old snapshot and present now;
- `changed`: same path and type but a different fingerprint or status;
- `missing_since_previous`: present before and absent now; this is not proof that QA deleted it when indexing was truncated or paths were reorganized;
- `unchanged_by_fingerprint_count`: matching snapshot entries, not proof that the old interpretation was correct.

Read the delta limitations. A missing hash weakens change detection. A renamed file can appear once as missing and once as added. A context from another root can make paths incomparable. Inspect important raw artifacts even when their fingerprint is unchanged if the old reasoning is being challenged.

## Review every old claim

Create a revision ledger with one row per material prior claim:

| Status | Meaning |
|--------|---------|
| `confirmed` | Current evidence independently supports the claim and its identity/proof boundary still holds. |
| `revised` | The core claim remains relevant but its scope, owner, mechanism, accounting, or certainty changes. |
| `retracted` | Current evidence contradicts it, exposes an invalid inference, or removes its required binding. |
| `unresolved` | Current evidence cannot confirm or reject it. |

Record the old evidence binding, current binding, and reason. List genuinely new claims separately. Never label an unchanged old claim `confirmed` solely because its source file hash is unchanged.

## Durable report shape

When the user asks to save a follow-up report, create a new revision; do not overwrite raw evidence or the old report without explicit authorization. Use recognizable headings such as:

```markdown
# Android Memory Analysis Revision

## Analysis mode and baseline
## Evidence delta
## Prior claim revision status
## Analysis conclusion
## Observed facts
## Hypotheses and contradictions
## New claims
## Unresolved questions and next evidence
```

Include the current context path and generator/schema version. Keep secrets, raw log lines, screenshot pixels, HPROF bodies, and trace bodies out of the report unless the user explicitly authorizes their inclusion.
