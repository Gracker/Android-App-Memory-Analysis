# Documentation Learning Path (EN)

This index keeps all teaching docs on one consistent structure: fundamentals -> single-source interpretation -> integrated analysis -> team workflow.

## 1) Fundamentals

- [Android Memory Debug Guide](./android_memory_debug_guide.md)
- [Android 17 / API 37 Adaptation Review](./android_17_adaptation_review.md)
- [Android 16 / API 36 Adaptation Review](./android_16_adaptation_review.md)

## 2) Single-source Interpretation

- [SMAPS Interpretation Guide](./smaps_interpretation_guide.md)
- [Meminfo Interpretation Guide](./meminfo_interpretation_guide.md)
- [Showmap Interpretation Guide](./showmap_interpretation_guide.md)
- [Proc Meminfo Interpretation Guide](./proc_meminfo_interpretation_guide.md)

## 3) Integrated Analysis

- [Analysis Results Interpretation Guide](./analysis_results_interpretation_guide.md)
- [Panorama Guide](./panorama_guide.md)

## 4) Teaching and Team Workflow

- [Teaching Playbook](./teaching_playbook.md)

## Recommended Study Order

1. Start from `android_memory_debug_guide.md` to align metric vocabulary.
2. If the target device runs Android 17 or the demo target is API 37, run the build, memory-limiter, and capture checklist in `android_17_adaptation_review.md`.
3. If the target device or target SDK is Android 16, or if the question is specifically about 16 KB page size, run the checklist in `android_16_adaptation_review.md`.
4. Read `smaps_interpretation_guide.md` and `meminfo_interpretation_guide.md` together.
5. Move to `analysis_results_interpretation_guide.md` for combined diagnosis.
6. Use `teaching_playbook.md` as the execution template for team practice and review.
