---
name: pragmatic-ood-reverser
description: >-
  理解既存 Java 17+/Spring Boot 或服务端 TypeScript（Next.js/Node）单体代码：架构摸底、代码考古、变更影响评估、重构前诊断。Use for evidence-based codebase onboarding, change-impact analysis, and OOD reconstruction. Not for greenfield design or implementing the refactor.
compatibility: 本地静态测绘需 Python 3.9+；无第三方依赖。无仓库或无 Python 时可作局部人工走查。
---

# Pragmatic OOD Reverser

帮助维护者回答三个问题：业务从哪里进入，哪些约束不能破坏，改动会传到哪里。以 TC++PL 第四部分为分析方法，不把书中原则当作项目证据。

## 先确定范围与写入权限

1. 从请求、构建文件和可读源码确定目标、源码根、语言和档位。不按文件多数猜语言。混合仓库选择相关源码根；两侧都有关时分别建图，不从两个静态图推断跨进程关系。超出支持范围要说明，不套用本流程。
2. **默认只读**：所有档位都可完全在对话中交付。用户说“只 review／先别改／不要写”优先于任何档位、恢复或自动模式：不创建、刷新或迁移地图，不改源码。读文件、运行本 Skill 的只读脚本即可；不运行目标项目的构建、迁移等有副作用命令。
3. **写盘是独立选择**：用户指定保存路径即用该路径；要求保存但未定路径，只确认一次默认 `docs/architecture/ood-system-map.md`。明确要求“直接生成并保存，不用问”则用指定或默认路径一次交付。一般的“不用问”不等于授权写文件。有旧地图也不代表本轮有写入授权。仅增量更新本次核实的章节，保留人工记录；不能安全合并时先给对话版。
4. **恢复前核实**：若有地图，读 YAML 与地图第 0/9 节，比对源码根、Git HEAD 和工作区变更（可用 `git --no-optional-locks status --short`），重开焦点文件核对符号与行号。不同提交、未提交改动、无 Git 或旧 schema 缺基线时，不复用未经复核的结论。旧地图无需先迁移才能阅读。

## 按用户问题选路线，不按轮数交作业

| 档位 | 路线 | 可以停止的条件 |
|---|---|---|
| `onboarding` 接手项目 | T → S0+S1 → S2+S4；不强制 S3 | 给出入口、组件关系、核心概念和下一份值得读的文件 |
| `impact` 评估具体改动 | T → S0/S1 定位上下游 → S3 → S4；按需补 S2 | 给出变更入口、关键写入和副作用、要守的约束与回归检查 |
| `deep-audit` 重构前摸底 | T → S0 → S1 → S2/S3 按焦点迭代 → S4 | 已回答目标模块的边界、角色与不变式，列明未走查部分；用户准备重构时提供 R0 移交，不实施重构 |

已给目标就直接查，不重复问档位。要求一次性全景时自动选代表入口，写明**已扫描范围、精读样本、未验证区域**；抽样不是全量走查。只给代码片段时用片段行号，不编造仓库路径或全库指标。

## 什么算证据

- **已观察**：给出仓库相对 `path:L10-L25` 和符号/测试/迁移。报告里的路径先从扫描根换算到仓库根。同一行可证明有守卫，不证明所有写入都经过它；读了测试也不等于运行过测试。
- **推断**：说明由哪些已观察事实推出、适用范围及可能的反例。设计意图始终是解释，不是作者证词。**待验证**：写出缺失的证据和下一步怎么查；未知不等于安全。
- 架构判断用源码定位 + 方法论双锚定：书中原则 `[§x.y]`，语言类比 `[§x.y · 扩展]`，工程经验 `[扩展]`。单纯代码事实不硬贴书号；节号不能替代源码。核对引语才定点检索 `references/source/part4.md`，不整本加载。
- 扫描器给出**物理导入**，不是业务边界、运行时调用或安全证明。先验一条真实边，再画图；区分 TS 类型声明、值候选和未解析项。S3 若发现静态图之外的监听/注入/事务边，用不同边型回补 S1 并附源码。热点只用于选读，不自动判风险。

## 按阶段加载（相对本 SKILL 所在目录）

链接带 `#` 时先定位锚点，再仅读到下一同级标题；不要为读一张卡加载整套手册。

| 活动 | 何时用什么 |
|---|---|
| T / S0 范围与物理快照 | [定范围](./references/10-excavation-flow.md#triage)、[物理测绘](./references/10-excavation-flow.md#S0)。用终端运行 `python3 "<skill_dir>/scripts/scan_topology.py" "<source_root>"`，可选 `--language java17` 或 `--language ts-server`。[扫描脚本](./scripts/scan_topology.py) 仅读取目标；失败或无源码时解释限制，改人工抽样。 |
| S1 组件与分层 | [S1](./references/10-excavation-flow.md#S1) + 目标语言的边界节：[Java](./references/50-java-spring-reverse.md#boundaries) 或 [TS](./references/51-ts-nextjs-reverse.md#boundaries)。遇到隐式链路再读该语言第 2 节。 |
| S2 概念与角色 | [S2](./references/10-excavation-flow.md#S2)、[七类角色](./references/20-role-anatomy.md)；有信号才查 [RL1–5](./references/30-reverse-lenses.md#RL1-RL5)；字段分群时查[访问矩阵](./references/21-invariant-mining.md#matrix)。 |
| S3 链路与约束 | [S3](./references/10-excavation-flow.md#S3)、[五类证据源](./references/21-invariant-mining.md#sources)、按需查 [RL6–10](./references/30-reverse-lenses.md#RL6-RL10)；隐式控制流只读目标语言的 [Java](./references/50-java-spring-reverse.md#implicit) 或 [TS](./references/51-ts-nextjs-reverse.md#implicit) 节。 |
| S4 修改指南与移交 | [S4](./references/10-excavation-flow.md#S4)；需要结构化地图或 R0 时用[空白模板](./resources/system-map-template.md)。溯源或核对 P 编号才查[索引](./references/00-provenance.md)。 |

## 对话交付

先回答本轮问题，再给最少够用的图、表或调用链；末尾列未覆盖项或建议的下一步。结构诊断最多展开 1–2 张卡：**定位 → 善意假设 → 风险成立的条件 → 修改前核查**。代码能回答的自己查。只有目标、保存或关键取舍不清时才用宿主提问工具（没有则用文本）；一次一个问题，推荐项说明理由。不为凑轮数停下来等用户。
