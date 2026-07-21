# Android 内存 AI 工作流

这套能力把当前仓库的实战采集/解析与 `Gracker/android-memory` 的理论边界连接起来，但不把诊断权交给一个黑盒模型。仓库先生成可校验、可追溯、与模型厂商无关的上下文；用户再把上下文交给 Codex、Claude 或其他支持 Skills 的 AI。

## 架构

<table><thead><tr><th>层</th><th>组件</th><th>稳定边界</th></tr></thead><tbody><tr><td>用户与 AI 项目</td><td><code>android-memory-evidence</code><br><code>android-memory-diagnose</code><br><code>android-memory-remediate</code></td><td>用户问题、证据状态、事实/假设/建议分离</td></tr><tr><td>AI 协议层</td><td>Skill 内置 runtime<br><code>analyze.py ai-context</code><br><code>android_memory_ai.context</code></td><td><code>android-memory-ai-context</code> schema 1.0 与生成器版本</td></tr><tr><td>证据与知识层</td><td>artifact validators<br>intent coverage<br><code>android_memory_catalog.json</code></td><td>哈希、来源、账本域、版本、缺口、冲突、理论来源</td></tr><tr><td>现有实战层</td><td>meminfo/smaps/HPROF/gfxinfo/DMA-BUF/ZRAM/Perfetto/panorama/diff</td><td>原始文件与现有派生报告；保持现有 CLI 兼容</td></tr><tr><td>Android / Linux</td><td>ART、Scudo、memtrack、LMKD、PSI、ZRAM、VMA、进程退出</td><td>API/内核/ROM/权限/设备差异</td></tr></tbody></table>

贯穿所有层的约束：隐私、采集扰动、package/PID/phase 身份、Android 版本、账本不可混加、派生报告不替代原始证据。

## 为什么先生成上下文

现有分析器已经能给出大量数值和建议，但它们不是统一协议：

- panorama/combined JSON 没有统一 schema version、数据源、哈希与采集上下文；
- HPROF 对象账、Heap Alloc、PSS/RSS 与 memtrack 可能并列出现，但不能直接相加或计算占比；
- 文件名存在不代表采集成功，权限失败、空文件和错误格式必须显式保留；
- 单点阈值只能触发调查，不能独立证明泄漏或 owner；
- 用户描述可能缺少 package、PID、设备、场景、phase 或采集模式。

`ai-context` 先解决这些边界，再让 AI 解释。

新的 live dump 还会生成 `manifest.json`，逐项记录 `ok`、`empty`、`permission_denied`、`not_supported`、`command_failed`、`skipped`、`not_applicable` 或 `not_collected`，同时说明命令、账本、扰动和失败理由。`not_collected` 不等于对应内存不存在。

## 生成 AI 上下文

对已有 dump 目录：

```bash
python3 analyze.py ai-context \
  -d ./dumps/com.example.app_20260721_120000 \
  --question "退出页面后 Native 内存仍持续增长" \
  --format json \
  -o android-memory-context.json
```

生成中文人读报告：

```bash
python3 analyze.py ai-context \
  -d ./dumps/com.example.app_20260721_120000 \
  --intent native-memory \
  --format markdown \
  --lang zh \
  -o android-memory-context.md
```

显式补充不在目录内的文件与用户上下文：

```bash
python3 analyze.py ai-context \
  -d ./case \
  --meminfo /evidence/meminfo.txt \
  --smaps /evidence/smaps.txt \
  --analysis-report /evidence/panorama.json \
  --package com.example.app \
  --android-sdk 37 \
  --phase after-exit-30s \
  --question "这是否是 JNI 泄漏？"
```

`--strict` 只用于自动化门禁。必需证据不完整时仍会写出上下文，但返回 exit code 2。交互式分析不应使用 strict 阻止“当前能解释什么”和“下一步怎么采”。

artifact 路径默认只保留相对路径，目录外文件会脱敏成 `<external>/文件名`。只有消费上下文的 AI 在同一台已授权机器上运行、且确实需要打开原始证据时，才添加 `--include-local-paths`；它会写入绝对 evidence root 与文件路径。未经单独隐私复核，不要把这种上下文外发。

## 上下文结构

| 字段 | 作用 |
|------|------|
| `request` | 显式或推断的意图、候选意图、原始问题 |
| `subject` | package、PID、时间、Android/API、fingerprint、page size、phase |
| `subject_candidates` | 每个来源给出的候选值，用于审计冲突 |
| `evidence.artifacts` | 类型、状态、路径、大小、SHA-256、账本域、扰动、校验信息 |
| `evidence.coverage` | 当前意图的 required/supporting/any-of 覆盖与分类级别 |
| `evidence.intent_coverage` | 自动问题中每个候选意图各自的覆盖；整体 support level 取最弱边界 |
| `evidence.conflicts` | 不会被静默覆盖的 package/PID/phase 等冲突 |
| `evidence.derived_reports` | 现有报告的安全摘要、账本域与限制 |
| `knowledge.records` | 与问题/证据相关的理论条目、不能证明什么、版本与官方来源 |
| `analysis_contract` | AI 必须遵守的事实/推导/假设/建议与隐私规则 |
| `next_evidence` | 可执行命令、前提、扰动、替代入口与解决的问题 |

支持级别是证据覆盖分类，不是概率：

- `insufficient`：解释当前输入与边界，不能选定根因或直接修代码；
- `limited`：能判断方向，但必须保留替代解释；
- `supported`：核心证据与部分 owner/时间证据可用；
- `strong`：该意图定义的证据齐全，但每条结论仍需绑定 artifact。

例如“Native memory 持续增长”会同时评估 native owner 分支和 regression 断言。Native 单点事实可以解释，但只要增长所需的可比 phase/对比证据不足，整体 `analysis_contract.support_level` 就仍是 `insufficient`；分支自身级别保留在 `primary_intent_support_level`。

artifact 格式有效，不代表对当前意图已经足够。尤其是单次 live snapshot 虽然有合法 `phase`，Java/Native leak 与 regression 仍需要 timestamp、process role、user/profile、scenario、loops、cooldown、collection mode、perturbation 和可比 phase；这类材料会进入 `evidence.coverage.inadequate`，并继续出现在 `next_evidence`。

## 安装公开 Skills

公开包包含三个 Skill，以及一个只依赖 Python 标准库的自包含证据 runtime。生成上下文需要 Python 3.8+，不需要另外 clone 本仓库，也不需要设置 `ANDROID_MEMORY_ANALYSIS_ROOT`。

使用开放 Skills CLI（Node.js 18+）安装到当前项目：

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*'
```

团队项目推荐使用项目级安装，因为生成的 `skills-lock.json` 会记录来源与安装哈希。全局安装到 Codex：

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*' \
  --agent codex \
  --global \
  --yes
```

安装到其他 Agent 时替换 `codex` 标识。安装或更新完成后，重启或重新加载 Agent。

更新全局安装时重新执行同一来源命令；CLI 会覆盖托管副本并刷新哈希：

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*' \
  --agent codex \
  --global \
  --yes
```

交互式刷新项目级安装时去掉 `--global` 和显式 Agent。Evidence Skill 的 `runtime/runtime-manifest.json` 固定 runtime、上下文 schema、知识目录版本和文件哈希。维护者从根目录唯一源码生成 bundle；用户不应手工修改生成文件。

完整仓库仍是 live capture、panorama、diff 和 Perfetto helper 的可选增强层。只有明确选择某个源码 checkout 时才传 `--repo /path/to/Android-App-Memory-Analysis`。部分高级补证命令会用 `ANDROID_MEMORY_ANALYSIS_ROOT` 引用这份可选 checkout，但安装后的上下文 runtime 不会发现或依赖这个变量。

推荐调用顺序：

1. `$android-memory-evidence`：校验用户材料、保留冲突、生成上下文、指导补证；
2. `$android-memory-diagnose`：结合知识条目、原始 artifact 与派生报告给出有边界的详细解释；
3. `$android-memory-remediate`：只有 owner/机制被证据支持且用户要求修改时，才改代码并做同场景验收。

## 用户信息残缺或不准确时

不要只回复“请提供更多日志”。应按下面格式继续：

1. 当前观察：文件/字段/状态/账本/phase；
2. 当前可解释：理论定义与方向；
3. 当前不能证明：根因、owner、趋势、kill 原因或跨设备结论；
4. 替代解释：至少保留仍与证据一致的机制；
5. 最小区分证据：给出 artifact、命令、权限、版本、扰动与预期区分结果；
6. 用户描述冲突：同时列出各来源，不把用户陈述或工具自动识别当绝对真相。

## 私有理论与公开知识边界

运行时知识目录是 [android_memory_catalog.json](../../knowledge/android_memory_catalog.json)：

- 记录私有来源仓库与 commit，用于维护追溯；
- 使用原创、压缩的操作性解释，不复制整篇私有文章；
- 对外引用 Android/AOSP/Linux/Perfetto 等可访问的一手来源；
- 把 `does_not_prove`、证据要求、Android 版本和实践工具作为一等字段；
- OpenClaw review 历史不作为运行时知识真相。

当前理论来源 revision：`2feca977830e99ddfb191022e9ba02409e7f0e19`。理论更新后，应逐条复核知识记录、官方链接、工具映射与版本边界，不能只替换 revision。

## 隐私与成本

- 上下文默认不嵌入原始 HPROF、trace 或任意文件正文；
- 上下文默认不暴露目录外绝对路径，本地路径必须显式 `--include-local-paths`；
- 小于 512 MiB 的 artifact 默认计算 SHA-256，更大文件需显式 `--hash-large-files`；
- HPROF 和 trace 可能包含用户输入、URL、token、业务对象、进程/线程名与命令行；
- 向外部模型提供原始 artifact 前必须单独进行授权、合规、访问控制与留存审查；
- `ai-context` 不会自动运行 HPROF/panorama 等重分析，避免意外 CPU/内存/时间成本。

## 验证

本仓库为新增 AI/Skills 能力定义的门禁是：

```bash
python3 scripts/sync_skill_runtime.py --write  # 仅在唯一 runtime/catalog 源码变化后执行
./scripts/verify.sh
./scripts/verify_npx_skill_install.sh
```

生成后的 runtime 必须与唯一源码修改一起提交。`verify.sh` 不会帮忙重新生成；bundle 过期或缺失会直接失败。这些门禁覆盖 stdlib 单元测试、bundle 漂移检查、隔离复制 Skill 执行、知识/Skills 静态验证、真实 demo CLI smoke test、strict 缺证据 exit-code，以及通过临时 Git 仓库执行的 `npx skills` 安装/重装。Skill Creator 的 `quick_validate.py` 仍需对每个 Skill 单独执行。

GitHub Actions 的 `AI Knowledge and Skills` workflow 会在 Python 3.8 与 3.12 上运行同一门禁。独立 public-install job 会在干净项目里通过固定版本的真实 `npx skills` 安装并重装三个 Skill，移除仓库和环境变量发现路径，再证明两次复制后的 runtime 都可以生成上下文。CI 不需要模型凭证，也不会上传 dump artifact。
