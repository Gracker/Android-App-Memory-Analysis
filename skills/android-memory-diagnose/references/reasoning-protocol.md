# Reasoning Protocol

## Claim ledger

Build every analysis around four claim kinds.

| Kind | Allowed content | Required binding |
|------|-----------------|------------------|
| `observed` | A field, event, mapping, object path, or status directly present in evidence | `artifact_id`, path/section, target identity, phase |
| `derived` | A deterministic transformation or comparison | Input artifact IDs, formula, units, accounting domain |
| `hypothesis` | A mechanism consistent with current evidence | Supporting evidence, contradicting evidence, discriminator |
| `recommendation` | Capture, code, config, or test action | Supported owner/mechanism, expected observation, risk, verification |

Never write a hypothesis in observed-fact grammar.

For QA artifacts, bind a log observation to artifact ID plus archive member when present and line number/hash, and bind a screenshot observation to artifact ID plus visible region. Signal inventories and image metadata only navigate the raw artifact; they are not the observation itself.

## Evidence support

- `insufficient`: explain the artifact, terminology, and limits; do not select a root cause or code fix.
- `limited`: identify direction and multiple alternatives; collect branch-owner evidence.
- `supported`: select the best-supported explanation while naming residual alternatives and validation.
- `strong`: required/supporting evidence is present, but every claim still needs artifact binding.

These are coverage categories, not probabilities.

## Hypothesis ranking

For each hypothesis, state:

1. mechanism;
2. accounting domain expected to change;
3. evidence supporting it;
4. evidence that would contradict it;
5. current contradicting or absent evidence;
6. next smallest discriminator;
7. Android/API/vendor/tool boundary.

Prefer hypotheses that explain multiple independent observations without mixing ledgers. Keep alternatives when evidence cannot distinguish them.

## Derived-report policy

Treat panorama, combined, diff, and third-party reports as derived evidence.

- Use them to navigate.
- Verify critical fields against raw inputs.
- Respect their schema version; treat absent versions as unversioned.
- Do not repeat threshold recommendations as diagnosis.
- Explicitly flag summaries that place object/runtime values next to page totals as non-comparable.
- Treat automated log matches as derived indexes and screenshot OCR as unperformed unless an authorized visual/OCR step actually occurred.

## Citation policy

- Cite raw artifacts by `artifact_id` and section/field.
- Cite theory by knowledge record ID.
- Link the official source carried by the knowledge record near the platform claim.
- Use private theory provenance as development lineage, not as an inaccessible end-user citation.
- Mark inference as inference.

## Explanation template

```text
Bounded conclusion:
  [what current evidence supports]

Observed:
  [artifact id] [field/event] [value/unit/domain/phase]

Interpretation:
  [knowledge id] [mechanism and version boundary]

Does not prove:
  [explicit non-claim]

Hypotheses:
  H1 [support, contradiction, discriminator]
  H2 [support, contradiction, discriminator]

Next evidence:
  [command, prerequisites, perturbation, expected discriminator]

Verification:
  [same scenario/device/phase contract]
```
