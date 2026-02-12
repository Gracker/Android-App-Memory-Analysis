# HPROF sample package

The demo HPROF sample is stored as a gzip package to keep repository size manageable and avoid large-file push issues.

- Sample package: `heapdump_latest.hprof.gz`
- Optional extraction command:

```bash
gzip -dk heapdump_latest.hprof.gz
```

After extraction, use the normal `.hprof` path in analysis commands:

```bash
python3 analyze.py hprof demo/hprof_sample/heapdump_latest.hprof
python3 analyze.py combined --modern --hprof demo/hprof_sample/heapdump_latest.hprof --smaps demo/smaps_sample/smaps --meminfo demo/smaps_sample/meminfo.txt
```

`analyze.py` also supports direct `.hprof.gz` input and will extract it to a temporary file automatically.
