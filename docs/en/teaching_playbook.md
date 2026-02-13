# Teaching Playbook

This playbook is the shared workflow template for workshops, onboarding, and team postmortems.

## Standard Analysis Workflow

### Step 1: Baseline Capture

```bash
python3 analyze.py live --package <package>
```

### Step 2: Signal Triage

- Check total memory trend first.
- Split by Java heap, Native, Graphics, and file mappings.
- Mark suspicious buckets before deep-dive.

### Step 3: Root-cause Analysis

- Use `smaps` and `meminfo` together for source-of-truth confirmation.
- Use HPROF for object ownership and retention evidence.
- Validate hypotheses with reproducible scenario steps.

### Step 4: Fix and Verification

- Re-run the same scenario with identical capture commands.
- Compare before/after memory distributions.
- Document side effects and regression risk.

## Automation Baseline Script

```bash
#!/bin/bash

PACKAGE=$1
INTERVAL=${2:-300}
LOG_DIR="memory_logs"

mkdir -p "$LOG_DIR"

while true; do
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  PID=$(adb shell "pidof $PACKAGE")

  if [ -n "$PID" ]; then
    python3 tools/smaps_parser.py -p "$PID" -o "$LOG_DIR/smaps_$TIMESTAMP.txt"
    TOTAL=$(grep -E "Total Memory Usage|总内存使用" "$LOG_DIR/smaps_$TIMESTAMP.txt" | grep -oE '[0-9.]+' | head -1)
    echo "$TIMESTAMP,$TOTAL" >> "$LOG_DIR/memory_trend.csv"
  fi

  sleep "$INTERVAL"
done
```

## Team Report Template

```markdown
# Memory Analysis Report

## Basic Information
- App Version:
- Android Version:
- Device Model:
- Analysis Time:

## Scenario and Reproduction
- Trigger steps:
- Expected behavior:
- Actual behavior:

## Memory Snapshot Summary
- Total Memory:
- Java Heap:
- Native Memory:
- Graphics Memory:

## Key Findings
1. [Issue]
   - Impact:
   - Evidence:
   - Root cause:

## Fix Plan and Validation
1. [Action]
   - Expected gain:
   - Verification result:

## Attachments
- smaps output:
- meminfo output:
- hprof output:
```

## Code Review Checklist

- [ ] Any unbounded collection growth
- [ ] Any lifecycle-bound object leaks
- [ ] Any large bitmap or buffer retention
- [ ] Any unsafe native allocation pattern
- [ ] Any missing cleanup path in async or callback flows

## Android 16 Compatibility Checklist

- Verify parsing and interpretation on 16KB page-size devices.
- Keep `smaps` capture fallback order: direct cat -> `su -c` -> `su 0`.
- Validate that non-root flows still produce actionable meminfo-based diagnosis.
- Ensure comparisons always use the same capture method across baseline and verification.
