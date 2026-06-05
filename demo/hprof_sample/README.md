# HPROF sample package

The demo HPROF sample is stored as a gzip package to keep repository size manageable and avoid large-file push issues.

- Sample package: `heapdump_latest.hprof.gz`
- Optional extraction command, only needed when using lower-level tools that do not read `.gz` directly:

```bash
gzip -dk heapdump_latest.hprof.gz
```

Use the packaged sample directly through the unified CLI:

```bash
python3 analyze.py hprof demo/hprof_sample/heapdump_latest.hprof.gz
python3 analyze.py combined --modern --hprof demo/hprof_sample/heapdump_latest.hprof.gz --smaps demo/smaps_sample/smaps --meminfo demo/smaps_sample/meminfo.txt
```

`analyze.py` extracts `.hprof.gz` to a temporary file automatically. It also falls back from a missing sibling `.hprof` sample path to `.hprof.gz` for old commands.
