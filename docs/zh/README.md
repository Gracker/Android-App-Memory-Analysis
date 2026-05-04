# 文档学习路径（中文）

本索引把教学文档统一为同一结构：基础认知 -> 单数据源解读 -> 综合分析 -> 团队实践。

## 1）基础认知

- [Android 内存调试指南](./android_memory_debug_guide.md)
- [Android 16 / API 36 适配 Review](./android_16_adaptation_review.md)

## 2）单数据源解读

- [SMAPS 解读指南](./smaps_interpretation_guide.md)
- [Meminfo 解读指南](./meminfo_interpretation_guide.md)
- [Showmap 解读指南](./showmap_interpretation_guide.md)
- [Proc Meminfo 解读指南](./proc_meminfo_interpretation_guide.md)

## 3）综合分析

- [分析结果解读指南](./analysis_results_interpretation_guide.md)
- [Panorama 指南](./panorama_guide.md)
- [Memory Lab Demo 实战案例](./memory_lab_demo_case_study.md)

## 4）教学与团队流程

- [教学实践手册](./teaching_playbook.md)

## 推荐阅读顺序

1. 先读 `android_memory_debug_guide.md`，统一指标和术语。
2. 如果目标设备或目标 SDK 是 Android 16，先跑 `android_16_adaptation_review.md` 的构建、16 KB page size 和采集清单。
3. 结合 `smaps_interpretation_guide.md` 与 `meminfo_interpretation_guide.md` 建立证据链。
4. 再读 `analysis_results_interpretation_guide.md` 做综合诊断。
5. 最后用 `teaching_playbook.md` 作为团队演练和复盘模板。
