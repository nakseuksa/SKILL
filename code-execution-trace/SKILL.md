---
name: code-execution-trace
description: 以运行时物理执行流视角（文件路径:行号、确切函数名与调用链、内存锁/注册表的存放位置与作用域、数据结构形变、写盘方式与崩溃语义、异步边界）机械、可验证地拆解本工作区的代码流程。每条结论必须先用 grep/read 取证并带 path:line 出处。当需要从代码层级理解某个功能的实现、拆解调用链路、排查底层逻辑时使用。
---

# SKILL: 代码执行流追踪 (Code Execution Trace)

## 0. 目标与适用范围

帮助读者**从代码层级理解工作区项目**：任何一段描述，读者都应能凭 `path:line` 直接跳到源码核对。

- 适用：HTTP 路由处理、回合（turn）生命周期、后台任务/流水线、store 读写、构建脚本、前端组件的数据流。
- 不适用：架构愿景讨论、产品需求解释（这些不需要本 skill 的精度）。

核心原则只有一条：**精确性来自取证，而不是来自措辞。** 一段看起来很"物理"但函数名是编的描述，比一段模糊的描述危害更大。

---

## 1. 证据规则（最高优先级，先于一切格式要求）

1. **先取证，后叙述。** 写出任何函数、常量、类型、文件、环境变量之前，必须已经用 `grep` / `glob` / `read` 在本次会话中确认其存在。
2. **出处格式统一为 `path:line`**（相对仓库根目录），在该标识符**首次出现**时附上。例：`triggerExtraction()`（`src/server/turn-service.ts:109`）。
3. **三级置信标记**，凡不是"读到原文"的内容都必须标注：
   - 无标记 = 已读到代码原文，直接陈述。
   - `【推断】` = 由已读代码的顺序/结构推出，但没有直接读到对应代码或测试（例：崩溃发生在两次写盘之间时的磁盘状态）。
   - `【未验证】` = 没有读到相关代码（例：某个 store 方法内部的写盘方式没打开看）。
4. **禁止为满足格式而补写。** 模板中的某一项在当前链路中不存在时，写 `N/A — <原因>`，不得虚构锁、写盘或校验。
5. **签名照抄。** 函数参数列表、返回类型、接口字段以源码为准逐字抄写，不得凭记忆"简化"。
6. **框架行为不凭记忆。** 涉及 Next.js 的路由、缓存、渲染行为时，按 `AGENTS.md` 要求先读 `node_modules/next/dist/docs/` 中对应文档；读不到则标 `【未验证】`。

---

## 2. 表达规则

### 2.1 禁止
- **拟人化**：「系统认为…」「AI 决定…」「智能体协商…」。
- **无代码对应的比喻**：「消息容器」「大脑」「试探阶段」等在代码中不存在的说法。
- **模糊的数据描述**：「把数据传过去」「处理一下结果」。
- **未解释的自造术语**：任何不是代码标识符、也没有给出定义的名词。

### 2.2 允许（并鼓励）
- **代码中真实存在的业务标识符**，如 `coverage`、`probe` / `teach` / `practice`、`ledger`、`digest`。首次出现时注明它对应的类型、字段或文件，例：「coverage（`CoverageEntry`，`src/store/graph.ts:126` 的形状校验；落盘于 `coverage.jsonl`）」。
- **开头 ≤3 行的总览**，用于定位，不承载细节。
- **Mermaid 时序图/流程图**辅助展示跨链路关系（可配合 `pele-mermaid` skill 校验渲染）。图中每个参与者必须是真实文件或函数。

### 2.3 LLM 调用的标准写法
用以下四项替代「AI 决定 / 模型理解」：

| 项 | 写什么 |
|---|---|
| 输入 | system prompt 常量名 + 拼接后的 prompt 结构 + 暴露给模型的 tool 名与 schema 常量 |
| 输出 | 被捕获的 tool call 参数类型（不是"模型的回答"） |
| 校验 | 校验函数名及其失败返回值 |
| 失败处理 | 重试机制（轮数上限）或抛出的 Error 类型/消息 |

---

## 3. 工作流程

1. **定位入口**：grep 路由文件、事件处理器或用户指定的函数，确认入口 `path:line`。
2. **沿调用向下读**：顺着 import 与调用逐个打开函数，直到以下任一终点：
   - 写盘 / 网络 / 进程边界；
   - 第三方包的调用点（如 `next`、`@earendil-works/pi-agent-core`），只记录调用点和入参，不进入包内部；
   - 用户指定的深度。
3. **标出生命周期边界**（见第 4 节），按边界把流程切成若干条物理链路。
4. **每条链路套用 5 阶段模板**（第 5 节），并应用第 6 节的专项规则。
5. **补充佐证**：grep `tests/` 中覆盖该链路的测试，作为行为证据引用（`tests/xxx.test.ts:line`）。
6. **执行第 8 节自检清单**，修正后再输出。

---

## 4. 物理生命周期切分

**严禁把跨边界的复合流程压成一条 1~5 阶段。** 先按边界切成多条【物理链路】，各自走 5 阶段模板，并在链路之间写明【衔接机制】。

以下任一情况都构成边界：

| 边界类型 | 代码特征 | 衔接机制要写什么 |
|---|---|---|
| 独立网络请求 | 不同的 route handler / 不同的 fetch | 状态码、响应头、响应体字段 |
| 不等待的 Promise | `void p`、`p.catch(...)` 不 await、`setTimeout(fn)` | 调用方何时返回、Promise 的 rejection 由谁处理 |
| 流式响应 | SSE / ReadableStream，回调在流读尽时触发 | 回调注册位置、触发条件 |
| 排队 / 信号量 / 互斥 | 信号量、FIFO promise 链 | 队列存放位置、何时放行、中止时如何出队 |
| 定时器 | `setInterval`、`setTimeout` | 定时器句柄存放位置、清理位置 |
| 进程 / IPC | `child_process`、Electron IPC、worker | 消息格式、通道名 |
| 浏览器侧 | `useEffect`、`sessionStorage`、路由跳转 | 存取的键名、触发时机 |

---

## 5. 单链路 5 阶段模板

每条物理链路按顺序展开以下 5 个阶段。**不存在的阶段写 `N/A — <原因>`。**

### 阶段一：触发入口与输入
- 入口函数 `path:line`，及它被谁、在什么条件下调用。
- 输入参数：逐字抄写签名；参数是对象时写出用到的字段。

### 阶段二：前置守卫与内存状态
- 锁 / 注册表 / 状态标志：按第 6.1 节格式描述。
- 进入主逻辑前的每个 `if` 早退或 `throw`：写出条件表达式原文，以及结果（静默 `return` 的返回值 / Error 类型 / HTTP 状态码）。

### 阶段三：调用链与数据变换
- 按执行顺序列出调用树，每个节点带 `path:line`。
- 标注每一步的 `await` 与串行/并行关系（`for…of + await` 是串行，`Promise.all` 是并行）。
- 数据形变：写明 `A 类型 → B 类型`，以及经过哪个函数、删除/注入了哪些字段、生成了哪些 ID。

### 阶段四：写盘与副作用
- 每一次写盘：目标文件（常量名 + 解析后的路径 + 常量定义处 `path:line`）、调用的 fs 方法、写入类型（第 6.2 节），以及崩溃语义。
- 写盘顺序必须与执行顺序一致（第 7 节规则 1）。
- 其他副作用：事件广播（`emit()`）、注册表增删、定时器启动。

### 阶段五：返回与资源释放
- 返回值类型，以及**调用方如何处理它**（使用 / 丢弃 / `.catch` 吞掉）。
- `finally` 中的释放动作（锁删除、注册表清理、连接关闭），带 `path:line`。

---

## 6. 专项规则

### 6.1 锁与注册表：位置 + 作用域
每个锁或注册表都写明以下四项：

| 项 | 示例 |
|---|---|
| 数据结构 | `Set<string>` / `Map<string, number>` / `{ tail: Promise<void> }` |
| 存放位置 | `globalThis.__lhExtractionRuns.inFlight`（定义处 `path:line`） |
| 作用域 | 单进程 RAM；挂在 `globalThis` 时在多个模块实例间共享；不跨进程，进程重启后丢失 |
| 获取 / 释放点 | 各自的 `path:line`；释放是否在 `finally` 中 |

**同名不同物必须靠路径区分。** 例如本工作区至少有三个 `inFlight`：
- `src/server/turn-liveness.ts:35`：`Map<string, number>`（`globalThis.__lhTurnRegistry`）
- `src/server/compaction.ts:122`：`Map<string, Promise<void>>`（`globalThis.__lhCompaction`）
- `src/agent/subagents/extraction.ts:669`：`Set<string>`（`globalThis.__lhExtractionRuns`）

### 6.2 写盘：区分三种写法
| 类型 | 代码特征 | 崩溃语义 |
|---|---|---|
| 直接覆盖 | `fs.writeFileSync(file, …)` | 非原子；崩溃可能留下截断的文件 |
| 原子替换 | `fs.writeFileSync(tmp)` + `fs.renameSync(tmp, file)` | 要么旧文件、要么新文件；可能残留 tmp 文件 |
| 追加 | `fs.appendFileSync(file, line)` | 已写的行保留；最后一行可能被截断，看读取端是否跳过坏行 |

不要笼统地写「原子写盘」或「持久化」。

### 6.3 异常与环境分支
- 列出每个 `catch` 的处理方式：重新抛出 / 记录日志后吞掉 / 转换为别的 Error 或 HTTP 状态码。
- 列出 `process.env.*` 造成的分支（例：`NODE_ENV === "test"` 时早退）。
- 列出中止路径：`AbortSignal`、`err.name === "AbortError"` 的判断位置和后果。

### 6.4 追踪深度
- 默认追到第一个写盘点或第三方包调用点为止。
- 同一个函数在多条链路中出现时，只完整展开一次，其他位置写「见链路 X 阶段 Y」。

---

## 7. 负面约束

1. **严禁时序倒挂。** 写盘与数据生成的顺序必须与执行流一致。后续链路依赖前序写入的文件时，该写盘必须在前序链路的阶段四中交代，不得挪到最后。
2. **路径不可悬空。** 任何标识符首次出现都带 `path:line`。
3. **锁必须物理化。** 按 6.1 节写出位置和作用域。
4. **数据结构必须显式。** 写出 `{ id, role, content }[]` 这样的形状，而不是「消息数据」。
5. **异常必须具象。** 写出 Error 类型 / 消息 / HTTP 状态码，以及由谁捕获。
6. **不得为填模板而编造。** 不存在就写 `N/A`，不确定就标 `【推断】` 或 `【未验证】`。

---

## 8. 输出前自检清单

- [ ] 每个函数、常量、文件都在本次会话中 grep/read 过，且首次出现带 `path:line`。
- [ ] 函数签名逐字对照过源码。
- [ ] 所有 `void` / 不 await 的 Promise、信号量、互斥、流回调都已切成独立链路。
- [ ] 每次写盘都标了三种类型之一，以及崩溃语义。
- [ ] 每个锁都写了数据结构、存放位置、作用域、获取/释放点。
- [ ] 每个 `catch` 和环境变量分支都列出了。
- [ ] 推断和未读到的内容已标 `【推断】` / `【未验证】`。
- [ ] 没有拟人化表达，没有未定义的自造术语。

---

## 9. 示范案例：对话回合结束后的知识图谱抽取

> 以下行号于 2026-11-06 对照代码核对。使用本案例前**必须重新核对**；代码与本文不一致时以代码为准。

**总览**：回合结束回调里同步判断是否需要抽取；需要时以不等待的 Promise 启动抽取流水线；流水线按 batch 串行执行"抽取 → 审计 → 合并写盘"。

```text
链路 A（同步，回合结束回调内）
  onFinish ─▶ triggerExtraction ─▶ void runExtraction(chatId)   ← 边界：不等待的 Promise
链路 B（异步，脱离回合）
  runExtraction ─▶ for 每个 batch（串行 await）:
      withExtractSlot（信号量，3 个许可）─▶ extract ─▶ runExtractor
      withAuditLock（全局 FIFO 互斥）   ─▶ audit ─▶ runAuditor ─▶ mergeFindings（写盘）
```

### 链路 A：回合结束回调中的触发判断

**阶段一：触发入口与输入**
- 入口：`onFinish: (turnMessages, isAborted) => { … }`（`src/server/chat-handler.ts:613`），在回合流被读尽时调用（注释见 `src/server/chat-handler.ts:143-145`）。该回调与客户端 HTTP 连接关闭的先后关系：【未验证】。
- 被调函数签名（`src/server/turn-service.ts:109`）：
  ```ts
  triggerExtraction(
    deps: { chatStore: ChatStore; graphStore: GraphStore },
    extraction: ExtractionPipeline,
    chatId: string,
    chunkTokens: number,
  ): void
  ```
- 调用处（`src/server/chat-handler.ts:657`）：`triggerExtraction(stores, extraction, chatId, effective.graph.extractionChunkTokens)`。

**阶段二：前置守卫与内存状态**
- 调用条件（`src/server/chat-handler.ts:653`）：
  `(!requestCycle || requestCycle.dispatched) && record.kind !== "practice" && extractionEnabled(effective.graph)`
- `triggerExtraction` 内部早退（均为静默 `return`，无返回值）：
  - `process.env.NODE_ENV === "test"`（`src/server/turn-service.ts:115`）
  - `deps.chatStore.getChat(chatId)` 返回空（`:117-118`）
  - `covered.uncoveredTokens < chunkTokens`（`:120`）
- 锁：N/A — 本链路不获取锁，单飞锁在链路 B 中检查。

**阶段三：调用链与数据变换**
1. `deps.chatStore.getChat(chatId)` → `ChatRecord`。
2. `deps.graphStore.readCoverage()`（`src/store/graph.ts:161`）→ `CoverageEntry[]`，读取 `coverage.jsonl`。
3. `coverageOf(record.messages, coverageEntries, chatId)`（`src/core/coverage.ts:115`）→ `covered`，本链路只用到 `covered.uncoveredTokens: number`。
4. `void extraction.runExtraction(chatId).catch(…)`（`src/server/turn-service.ts:121`）—— **边界**，进入链路 B。

**阶段四：写盘与副作用**
- N/A — 本链路只读 `coverage.jsonl`，不写盘。

**阶段五：返回与资源释放**
- `triggerExtraction` 同步返回 `void`。`onFinish` 继续执行 `applyParkedDismissal()`（`src/server/chat-handler.ts:665`）和 `endTurn(chatId)`（`:668`），不等待链路 B。

**衔接机制 A → B**
- 链路 B 返回的 `Promise<EmissionStats>` 被 `void` 丢弃；只有 rejection 被 `.catch` 处理（`src/server/turn-service.ts:121-135`）：
  - `ModelsNotConfiguredError` → `console.info`，吞掉；
  - `ProviderKeyMissingError` → `console.info`，吞掉；
  - 其他 → `console.error`，吞掉。
- 同步段抛出的异常由外层 `try/catch` 记录（`:136-138`）。

### 链路 B：抽取流水线（异步执行）

**阶段一：触发入口与输入**
- `runExtraction(chatId: string): Promise<EmissionStats>`（`src/agent/subagents/extraction.ts:1113`），定义在工厂函数 `createExtractionPipeline(deps)`（`src/agent/subagents/extraction.ts:803`）的闭包内。

**阶段二：前置守卫与内存状态**
- 单飞锁：
  | 项 | 内容 |
  |---|---|
  | 数据结构 | `Set<string>`，键为 `chatId` |
  | 存放位置 | `globalThis.__lhExtractionRuns.inFlight`，由 `runs()` 惰性创建（`src/agent/subagents/extraction.ts:693-696`） |
  | 作用域 | 单进程 RAM；放在 `globalThis` 是为了让 Next dev 下各路由的模块实例共享同一份（注释 `:685-692`）；进程重启后丢失 |
  | 获取 / 释放 | `inFlight.has(chatId)` 为真时 `return { nodes: 0, chains: 0 }`，否则 `inFlight.add(chatId)`（`:1114-1115`）；在 `finally` 中 `inFlight.delete(chatId)`（`:1245`） |
- 守卫（`try` 块内，按顺序）：
  - `chatStore.getChat(chatId)` 为空 → `throw new Error("Chat not found: …")`（`:1126`）。
  - `refuseIfStagesUnready()`（`:816`）：extractor 或 auditor 未配置引擎 → `throw new ModelsNotConfiguredError([...missing])`（`:825`）；provider key 缺失 → `throw new ProviderKeyMissingError(…)`（`:834`）。
  - `covered.uncovered.length === 0` → `return { nodes: 0, chains: 0 }`（`:1134-1137`）。

**阶段三：调用链与数据变换**
1. `batchRuns(covered.slots, covered.uncovered, chunkTokens)`（`src/core/coverage.ts:159`）→ `CoverageSlot[][]`。
2. `for (const [batchIndex, batch] of batches.entries())` + `await runJob(…)`（`src/agent/subagents/extraction.ts:1157-1162`）—— **batch 之间串行**。
   - `runJob(source, body)`（`:1060`）：`jobKey` 为 `chatId`，或多 batch 时为 `` `${chatId}#${i}` ``（`:1064`）。
3. 每个 batch 内：
   1. `proseView(messages, record.title, failedOutputCalls)`（`:135`）：`LhMessage[]` → `string`（只保留 TEACHER 文本，每段以 `TEACHER [messageId]` 标注）。
   2. 构造 `batchIds: Set<string>` = 本 batch 中能产出视图行的消息 id（`:1175-1177`）。
   3. `setPhase(jobKey, "queued", …)`（`:844`）：写入 `runningExtractions: Map<string, RunningExtraction>`，并 `emit("activity-changed", {})`。
   4. **边界：信号量。** `withExtractSlot()`（`:1020`）→ `withBgLlmSlot(signal, critical)`（`src/agent/subagents/bg-llm-semaphore.ts:52`）。许可池为 `globalThis.__lhLlmSlots: { active: number; queue: … }`，`PERMIT_COUNT = 3`（`:30`），进程内所有后台 LLM 任务共享。
   5. `extract(jobKey, chatId, view, batchIds)`（`src/agent/subagents/extraction.ts:925`）：`getGraph(graphStore)` → `sourceDigest(graph, sourceId)` → `prompt`：`digest` 为空时等于 `view`，否则为 `digest + "\n\n" + view`（`:939-941`）。
   6. **LLM 调用：`runExtractor()`**（`:493`）→ `runSubmitAgent<SessionFindingsSubmit>()`（`src/agent/subagents/submit-agent.ts:48`）：
      | 项 | 内容 |
      |---|---|
      | 输入 | `systemPrompt: EXTRACTOR_INSTRUCTIONS`（`extraction.ts:437`），`prompt` 为上一步的字符串，tool `submit_findings`，schema `sessionFindingsSchema` |
      | 输出 | `SessionFindings`：`{ propositions: { id, name, statement, aliases, messageId? }[]; chains: { premises: string[]; conclusion: string }[] }`（经 `asSessionFindings`，`extraction.ts:356`） |
      | 校验 | `validateSessionAnchors(value, batchIds) ?? validateFindingsChains(value, existingIds)`（`extraction.ts:515`）；`validateSessionAnchors`（`:338`）在 `messageId` 为空或不在 `batchIds` 中时返回错误字符串 |
      | 失败处理 | 校验返回字符串 → `invalidInputResult()` 作为 tool 错误结果回给模型重试（`submit-agent.ts:102-103`），轮数上限 `maxTurns ?? 4`（`:114`）；始终未成功提交 → `throw new Error("the extractor never submitted findings")`（`:132`） |
   7. **边界：全局互斥。** `withAuditLock(jobKey, "chat", undefined, critical)`（`extraction.ts:896`）：`globalThis.__lhAuditLock: { tail: Promise<void> }`，FIFO promise 链；`setPhase(…, "waiting")`；在 `finally` 中 `release()`（`:921`）；等待期间中止 → `Error`，`name = "AbortError"`（`:908-909`）。
   8. `audit(jobKey, chatId, findings)`（`:964`）：`prepareAuditorReview()` 生成初始候选；prompt 为 JSON：`propositions` 只保留 `{ id, name, statement, aliases }`（**删除 `messageId`**），加上 `review.initialCandidates`（`:984-997`）。
   9. **LLM 调用：`runAuditor()`**（`:588`）→ `runSubmitAgent()`：
      | 项 | 内容 |
      |---|---|
      | 输入 | `systemPrompt: AUDITOR_INSTRUCTIONS`（`:560`），tool `submit_review`，schema `auditSchema`，额外 tools 为 `review.tools` |
      | 输出 | `AuditVerdicts`：`{ links: { id, linkTo }[] }`（`fillAudit`，`:366`） |
      | 校验 | N/A — 未传 `validate` |
      | 失败处理 | `maxTurns: 16`（`:611`）；未提交 → `throw new Error("the auditor never submitted a review")` |
   10. 会话删除守卫：`!chatStore.getChat(chatId)` → 抛出 `name = "AbortError"` 的 `Error`（`:1196-1200`）。
   11. `mergeFindings(chatId, findings, auditResult, { chatStore, graphStore }, { foldedAt, coverage })`（`src/core/graph.ts:149`），`coverage` 为本 batch 中 `tokens > 0` 的 slot 映射成的 `{ chatId, fp, tokens, foldedAt }[]`（`extraction.ts:1206-1211`）。
       - 步骤 1：`linkOf = new Map(verdicts.links.map(l => [l.id, l.linkTo]))`（`graph.ts:169`）。逐个 proposition：`linkTo` 存在于已有节点 id → 以该 id 追加一行 link 记录（`:189`）；否则 `newGraphNodeId()`（`:80`）生成新 id 并追加（`:198-206`）。结果写入 `mapping: Map<string, string>`（本地 id → 图节点 id）。
       - 步骤 2：经 `mapping` 解析 chain 端点，去重后 `appendChain()`（`:251`）。
       - 步骤 2b：`simplifyChains(allChains)`；条数变化时 `rewriteLedgers({ chains: keptChains })`（`:271-276`）。
       - 步骤 3：`source.coverage !== undefined`（chat 路径）→ 逐条 `appendCoverage()`（`:285`）；否则（notes 路径）`appendCheckpoint()`（`:287`）。
   12. `settleGraphLayout(graphStore)`（`src/core/layout-settle.ts:26`）→ `graphStore.writePositions(…)`。
4. `aggregateJobs(chatId, settled)`（`extraction.ts:1083`）汇总各 batch 的 `EmissionStats`。

**阶段四：写盘与副作用**（按执行顺序；路径根为 `PATHS.graph = path.join(DATA_ROOT, "graph")`，`config.ts:28`）

| 顺序 | 调用 | 目标文件（常量定义处） | fs 方法 | 类型 |
|---|---|---|---|---|
| 1 | `appendNode()`（`src/store/graph.ts:132`）→ `appendLine()`（`:53`） | `nodes.jsonl`（`config.ts:63`） | `fs.appendFileSync` | 追加 |
| 2 | `appendChain()`（`src/store/graph.ts:144`） | `chains.jsonl`（`config.ts:64`） | `fs.appendFileSync` | 追加 |
| 3 | `rewriteLedgers({ chains })`（`src/store/graph.ts:217`），仅当简化删除了 chain | `chains.jsonl` | `writeFileSync(tmp)` + `renameSync`（`:237-238`） | 原子替换 |
| 4 | `appendCoverage()`（`src/store/graph.ts:158`） | `coverage.jsonl`（`config.ts:69`） | `fs.appendFileSync` | 追加 |
| 5 | `writePositionMap()`（`src/store/graph.ts:276`） | `positions.json`（`config.ts:83`） | `writeFileSync(tmp)` + `renameSync`（`:283-284`） | 原子替换 |
| 6 | `persistRunUsage()`（`extraction.ts:1029`）→ `chatStore.appendExtractionUsage()` | 【未验证】 | 【未验证】 | 【未验证】 |

- 崩溃语义：
  - 读取端 `readRawLines()` 会跳过无法解析的行（`src/store/graph.ts:73-75`），所以追加时被截断的最后一行在读取时被忽略。
  - coverage 在 node/chain 之后才追加（`src/core/graph.ts:278-288` 注释）。【推断】若进程在第 1~2 步之后、第 4 步之前崩溃，已追加的 node/chain 行保留，而该 batch 的消息仍是未覆盖状态，下一次触发会重新抽取该 batch。
- 其他副作用：每次 `setPhase()` 和 `finishExtraction()` 都会 `emit("activity-changed", {})`（`extraction.ts:866`、`:874`）。

**阶段五：返回与资源释放**
- 每个 batch：`runJob` 的 `finally` 调用 `finishExtraction(jobKey)`，即 `runningExtractions.delete(jobKey)`（`extraction.ts:1073-1075`、`:872-874`）。
- batch 失败：在 `:1222-1229` 捕获并记为 `rejected`，其他 batch 继续；`err.name === "AbortError"` 时 `break`，跳过剩余 batch。
- 整体：返回 `EmissionStats { nodes, chains, droppedChains? }`；`finally` 中 `inFlight.delete(chatId)` 和 `finishExtraction(chatId)`（`:1244-1247`）。
- 返回值被链路 A 的 `void` 丢弃；`try` 中 batch 循环之前的异常会在 `:1242` 记录后重新抛出，由链路 A 的 `.catch` 处理。

**测试佐证**
- `triggerExtraction` 在 `NODE_ENV === "test"` 时早退，所以对话流测试不会经过链路 B；流水线由 mock 模型直接测试（注释 `src/server/turn-service.ts:105-107`）。对应测试文件：【未验证】，使用前应 grep `tests/` 中对 `createExtractionPipeline` 的引用。
