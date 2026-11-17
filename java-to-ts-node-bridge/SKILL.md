---
name: java-to-ts-node-bridge
description: 面向具有 Java Web（Spring Boot / JVM 多线程 / JDBC 事务 / 名义类型 OOP）经验的开发者，以运行时物理实现与编译期契约视角，对比拆解本工作区（learnharness）的 TypeScript 类型系统、Node.js 单线程事件循环与 globalThis 锁/信号量、六边形端口与函数式闭包依赖注入、Next.js 16 双端模块边界及 Web Streams 流式 I/O。每条结论必须先用 grep/read 取证并带 path:line 出处。
---

# SKILL: Java → TS/Node/Next.js 心智迁移拆解 (Java-to-TS/Node Mental Model Bridge)

## 0. 目标与适用范围

帮助具有 Java Web 开发经验的读者**从代码与运行时物理层级理解工作区项目（`learnharness`）中的 TypeScript / Node.js / Next.js 16 机制**：通过精准对标 Java/Spring 参照系，消除因“语法看似相近但运行时语义截然不同”导致的误判。

- 适用：
  - TypeScript 结构化类型、可辨识联合类型（Discriminated Unions）、模块声明合并（`declare module`）、TypeBox/Zod 运行时 Schema 校验。
  - Node.js 单线程事件循环下的并发控制：`globalThis` 进程级状态池、Promise 链 FIFO 互斥锁、异步信号量、`AbortController` 取消传播。
  - 无 IoC 容器的函数式依赖注入：六边形端口接口（`src/core/ports.ts`）、唯一组合根（`src/server/stores.ts`）、高阶工厂函数与闭包捕获、`eslint.config.mjs` 强制模块红线。
  - Next.js 16 App Router 服务端/客户端同构边界、Barrel（`src/core/index.ts` / `src/server/index.ts`）打包隔离。
  - Web `ReadableStream` / `AsyncGenerator` SSE 流式传输与同步 `fs` 写盘的崩溃语义。
- 不适用：
  - 单条端到端 HTTP 业务调用链的逐行步骤追踪（交 `code-execution-trace`）。
  - 系统提示词工程与教学法设计意图分析（交 `agent-harness-dissector`）。

核心原则只有一条：**对比必须落在物理机制上，而不是落在名词类比上。** 一句笼统的“这相当于 Spring 的 Singleton Bean”而不指出 `globalThis` 在 Next dev 多模块实例下的生命周期差异，比不对比危害更大。

---

## 1. 证据规则（最高优先级，先于一切格式要求）

1. **先取证，后叙述。** 写出本仓库任何函数、常量、类型、文件、环境变量或 ESLint 规则之前，必须已经用 `grep` / `glob` / `read` 在本次会话中确认其存在。
2. **出处格式统一为 `path:line`**（相对仓库根目录），在该标识符**首次出现**时附上。例：`withBgLlmSlot()`（`src/agent/subagents/bg-llm-semaphore.ts:52`）。
3. **三级置信标记**，凡不是“读到代码原文”的内容都必须标注：
   - 无标记 = 已读到代码原文，直接陈述。
   - `【推断】` = 由已读代码的顺序/事件循环机制推出，但没有直接读到对应代码或测试（例：两个并发请求在某个 `await` 挂起点交错时的内存状态）。
   - `【未验证】` = 没有读到相关代码（例：某个第三方库内部的流缓冲实现未打开看）。
4. **禁止为满足格式而补写。** 模板中的某一项在当前机制中不存在时，写 `N/A — <原因>`，不得虚构机制。
5. **签名照抄。** TypeScript 类型定义、接口字段、函数参数列表与返回类型以源码为准逐字抄写，不得凭记忆“简化”成伪代码。
6. **框架行为不凭记忆。** 涉及 Next.js 16 的路由、缓存、Server/Client Component 边界时，按 `AGENTS.md` 要求先读 `node_modules/next/dist/docs/` 中对应文档；读不到则标 `【未验证】`。

---

## 2. 表达规则

### 2.1 禁止
- **浅层名词替换**：只写“相当于 `@Autowired` / `synchronized` / `@Transactional`”，不交代底层执行差异。
- **混淆编译期与运行时**：把 TypeScript 的 `interface` / `type` 当成运行时存在的类或反射元数据。
- **混淆阻塞线程与挂起协程**：把 `await promise` 说成“阻塞线程”，或把 `fs.writeFileSync` 说成“异步非阻塞”。
- **未解释的自造术语**：任何既不是本仓库代码标识符、也不是标准 Java/Node 规范术语的名词。

### 2.2 允许（并鼓励）
- **精确的 Java 标准库/框架参照物**：如 `java.util.concurrent.Semaphore`、`ReentrantLock`、`ThreadLocal`、Spring `ApplicationContext`、Jackson `@JsonTypeInfo`、Servlet `AsyncContext`。
- **开头 ≤3 行的总览**，用于快速定位机制类别与核心差异。
- **Mermaid 内存布局图 / 事件循环交错时序图**：图中每个本仓库节点必须是真实文件、函数或变量名。

### 2.3 Java vs. TS/Node 机制对比的标准四行表
凡进行机制对比，必须包含以下四行：

| 对比维度 | Java Web 机制（参照系） | 本仓库 TS/Node/Next.js 实现（带 `path:line`） | 核心差异与迁移陷阱 |
|---|---|---|---|
| **编译期 vs. 运行时存在性** | 如：字节码保留类型，运行期可反射 / `instanceof` | 如：TS 类型擦除；运行期靠判别字段 `role` / `customType` 或 TypeBox/Zod 校验 | ... |
| **内存作用域与生命周期** | 如：JVM 堆内 Spring Singleton Bean | 如：`globalThis.__lhLlmSlots`（跨 Next dev 路由模块实例共享，进程重启清空） | ... |
| **调度与并发交错边界** | 如：OS 线程任意指令抢占，需 `synchronized` 保护临界区 | 如：单线程事件循环，同步代码段天然原子，唯 `await` 处让出执行权 | ... |
| **异常与取消传播** | 如：`Thread.interrupt()` / `InterruptedException` / 事务回滚 | 如：`AbortSignal` 事件监听 + `Promise.race` 抛出 `err.name = "AbortError"` | ... |

---

## 3. 工作流程

1. **定位目标代码**：`grep` / `read` 用户指定的模块、类型、锁、端口或配置，确认 `path:line`。
2. **识别映射域（见第 4 节）**：判定目标属于 M1（类型系统）、M2（DI 与架构边界）、M3（单线程并发与锁）、M4（Next.js 同构与打包边界）、M5（流与 I/O 语义）中的哪一类或哪几类。
3. **追踪上下游契约**：
   - 若是类型：找到定义处、构造处、以及消费处的类型收窄（Type Narrowing）或 Schema 校验处。
   - 若是 DI/端口：找到接口定义（`src/core/ports.ts`）、适配器实现（`src/store/`）、组合根装配（`src/server/stores.ts`）与闭包注入点。
   - 若是并发原语：找到 `globalThis` 挂载点、入队/获取点、`await` 挂起点、`finally` 释放点及 `AbortSignal` 处理点。
4. **套用 5 维拆解模板（第 5 节）**，并应用第 6 节专项规则。
5. **补充测试佐证**：`grep` `tests/` 中对该机制的单元测试（`tests/xxx.test.ts:line`），对照 JUnit/Mockito 说明本仓库如何做无容器确定性测试。
6. **执行第 8 节自检清单**，修正后再输出。

---

## 4. 五大心智迁移域切分法则

拆解前必须先将问题归入以下 5 个正交域之一（复合模块按域分节展开）：

| 域编号 | 域名称 | 代码特征 | 必查的核心问题 |
|---|---|---|---|
| **M1** | **类型系统与运行时校验** | `type A = B \| C`、`declare module`、`Type.Object`（TypeBox）、`z.object`（Zod）、类型谓词 `x is Y` | 编译擦除后 JS 对象长什么样？靠哪个判别属性做分支收窄？进程边界（HTTP / LLM Tool）靠什么做运行时校验？ |
| **M2** | **六边形 DI 与模块红线** | `ports.ts` 接口、`stores.ts` 装配、`createXxx(deps)` 工厂闭包、`eslint.config.mjs` 的 `zones` | 为什么不用 `@Autowired`？依赖如何通过函数闭包传递？违反哪条 ESLint zone 会导致 CI 报错？ |
| **M3** | **事件循环并发与内存协调** | `globalThis.__lh*`、`async/await`、`new Promise` 队列、`Set`/`Map` 注册表、`AbortController` | 同步段为何不需要锁？哪个 `await` 会让出控制权导致竞态？为什么必须挂 `globalThis` 而非模块顶层 `const`？ |
| **M4** | **Next.js 16 同构与 Barrel 隔离** | `app/**/page.tsx`、`app/api/**/route.ts`、`"use client"`、`src/core/index.ts`、`src/server/index.ts` | 该文件在 Node 还是浏览器执行？为什么 `src/core/index.ts` 刻意排除含 `node:crypto` / 重依赖的模块？ |
| **M5** | **Web Streams 与同步文件 I/O** | `ReadableStream`、`async function*`、`fs.writeFileSync`、`fs.appendFileSync`、`fs.renameSync` | 为什么用同步 `fs` 而不是异步 `fs.promises`？无数据库事务时如何靠写入顺序与读取端容错保证崩溃一致性？ |

---

## 5. 单机制 5 维拆解模板

每个目标机制按顺序展开以下 5 个维度。**不存在的维度写 `N/A — <原因>`。**

### 维度一：源码定位与签名原貌
- 入口文件与标识符 `path:line`，以及它在系统分层（`app` / `components` / `server` / `agent` / `core` / `store`）中的位置。
- 逐字抄写核心类型定义或函数签名。

### 维度二：Java Web 对标参照（同构点 vs. 异构点）
- 指出最贴近的 Java/Spring 概念。
- 填写 **第 2.3 节标准四行对比表**（编译期 vs. 运行时、内存作用域与生命周期、调度与并发交错边界、异常与取消传播）。

### 维度三：物理运行机制拆解
- 按所处域（M1~M5）展开物理实现细节（见第 6 节专项规则）：
  - **状态存放位置與结构**（如 `globalThis` 上的字段名与类型）。
  - **执行与挂起序列**：标出同步原子段与每一个 `await` 挂起点。
  - **类型/数据在内存中的实际形态**。

### 维度四：Java 惯性反模式与防坑守则
- 列出 2~3 条若按 Java Web 习惯修改此处代码会引发的**具体工程事故**（必须写明触发的编译器错误、ESLint 规则名、运行时死锁或竞态现象）。

### 维度五：确定性测试验证对照（`node:test` vs. JUnit/Mockito）
- 引用 `tests/*.test.ts:line` 中的真实测试代码，说明本仓库如何不借助 Spring TestContext 或字节码 Mock 框架，仅靠函数参数/接口注入完成隔离测试。

---

## 6. 专项规则

### 6.1 分析并发原语（域 M3）：必须标出「同步原子段」与「`await` 交错窗」
Node.js 在单个事件循环线程中运行 JS 代码。拆解任何锁、信号量或注册表时，必须明确区分：
1. **同步检查并置位（Check-Then-Act）**：若 `if (!inFlight.has(id)) inFlight.add(id)` 之间**没有任何 `await`**，则在单进程内天然互斥，无需 Java 的 `synchronized` 或 `ConcurrentHashMap.putIfAbsent`。
2. **`await` 交错窗（Interleaving Window）**：一旦遇到 `await`，当前协程挂起，事件循环可立即执行其他 HTTP 请求或定时器回调。必须指明：`await` 恢复后，哪些内存状态或磁盘文件可能已被其他协程修改（例如为何必须在 `await` 锁之后重新读取权威记录或检查 `signal?.throwIfAborted()`）。
3. **为什么挂 `globalThis`**：必须说明 Next.js 开发模式下按路由入口独立编译模块实例的机制——模块顶层 `const map = new Map()` 在不同路由中会分裂成多个实例，唯有挂在 `globalThis` 上才能实现单进程全局单例。

### 6.2 分析依赖注入与架构红线（域 M2）：必须对照 `eslint.config.mjs` 四条铁律
凡涉及模块引用或 DI 设计，必须核对 `eslint.config.mjs:41-70` 定义的四个 `import/no-restricted-paths` 区域：
- **Zone 1（`:42-49`）**：`./components` 导入 `./src` 时，仅允许 `./core/index.ts`（即 `@/src/core`）。
- **Zone 2（`:50-56`）**：`./app` 导入 `./src` 时，仅允许 `./core/index.ts` 与 `./server/index.ts`。
- **Zone 3（`:57-62`）**：`./src/core` 严禁导入 `./src/agent`、`./src/server`、`./src/store`。
- **Zone 4（`:63-68`）**：`./src/agent` 严禁导入 `./src/server`、`./src/store`。

### 6.3 分析类型系统（域 M1）：必须区分「编译期窄化」与「运行时校验」
- 说明联合类型（如 `LhMessage`）在编译期如何通过 `if (m.role === "custom")` 触发 TypeScript 控制流类型收窄（Control Flow Narrowing）。
- 说明外部输入（HTTP body、磁盘 JSON、LLM tool arguments）进入系统时，TypeScript 类型完全擦除，必须指出具体的运行时校验函数或 Schema（如 `Type.Object` / `zod` / 手写形状守卫函数 `path:line`）。

---

## 7. 负面约束

1. **严禁伪造 Java 映射。** 如果某个机制（如浏览器端纯 TS 投影或 React/Next 特有机制）在后端 Java 中无直接对应，如实写明差异，不得强行附会。
2. **路径不可悬空。** 任何本仓库标识符首次出现都带 `path:line`。
3. **严禁忽略 `await` 边界。** 分析异步函数时，漏掉 `await` 带来的状态交错可能性属于严重错误。
4. **严禁把同步 `fs` 当成异步。** 本仓库 `src/store/` 大量刻意使用 `fs.readFileSync` / `fs.writeFileSync` / `fs.appendFileSync` 以保证单事件循环 tick 内读-改-写不交错，必须如实说明这一设计取舍。
5. **不得为填模板而编造。** 不存在就写 `N/A`，不确定就标 `【推断】` 或 `【未验证】`。

---

## 8. 输出前自检清单

- [ ] 每个本仓库函数、常量、类型、文件都在本次会话中 `grep` / `read` 过，且首次出现带 `path:line`。
- [ ] 函数签名与类型定义逐字对照过源码。
- [ ] 已包含第 2.3 节的标准四行对比表（编译期 vs. 运行时、内存生命周期、调度边界、异常与取消）。
- [ ] 若涉及并发/锁，已标出同步原子段、`await` 挂起点、`globalThis` 挂载原因及 `finally` 释放逻辑。
- [ ] 若涉及模块依赖/DI，已核对 `eslint.config.mjs` 的具体 Zone。
- [ ] 已列出 Java 惯性反模式及 `tests/` 中的真实测试佐证 `path:line`。
- [ ] 推断和未读到的内容已标 `【推断】` / `【未验证】`。

---

## 9. 示范案例：后台 LLM 并发控制（异步信号量 + FIFO Promise 互斥锁）与无容器 DI

> 以下行号于 2026-11-09 对照代码核对。使用本案例前**必须重新核对**；代码与本文不一致时以代码为准。

**总览**：拆解本仓库知识图谱抽取流水线如何不依赖 JVM 多线程锁与 Spring IoC 容器，在 Node.js 单线程事件循环上用 `withBgLlmSlot`（3 许可异步信号量）、`withAuditLock`（FIFO Promise 链互斥锁）与函数式闭包注入实现并发控流与临界区保护（映射域：**M3 并发模型 + M2 依赖注入**）。

### 维度一：源码定位与签名原貌

1. **进程级 3 许可异步信号量**（位于 `src/agent/subagents/bg-llm-semaphore.ts`，智能体子任务层）：
   - 常量与状态类型（`src/agent/subagents/bg-llm-semaphore.ts:30-35`）：
     ```ts
     const PERMIT_COUNT = 3;

     export interface LlmSlots {
     	active: number;
     	queue: { resolve: () => void; dead: boolean }[];
     }
     ```
   - 信号量获取与执行函数签名（`src/agent/subagents/bg-llm-semaphore.ts:52-55`）：
     ```ts
     export async function withBgLlmSlot<T>(
     	signal: AbortSignal | undefined,
     	critical: () => Promise<T>,
     ): Promise<T>
     ```
2. **审计 + 合并全局 FIFO 互斥锁**（位于 `src/agent/subagents/extraction.ts`，定义在工厂函数 `createExtractionPipeline(deps: ExtractionDeps)`（`src/agent/subagents/extraction.ts:803`）闭包内）：
   - 全局锁类型声明（`src/agent/subagents/extraction.ts:678`）：
     ```ts
     __lhAuditLock?: { tail: Promise<void> };
     ```
   - 互斥包装函数签名（`src/agent/subagents/extraction.ts:896`）：
     ```ts
     async function withAuditLock<T>(jobKey: string, kind: "chat" | "notes", label: string | undefined, critical: () => Promise<T>): Promise<T>
     ```
3. **存储组合根与端口契约**（位于 `src/core/ports.ts` 与 `src/server/stores.ts`）：
   - 端口定义：`export interface ChatStore`（`src/core/ports.ts:34`）、`export interface GraphStore`（`src/core/ports.ts:79`）。
   - 唯一存储组合根：`export const stores = { chatStore, graphStore, sourceOrganizationStore, jobStore, settingsStore }`（`src/server/stores.ts:17-23`）。

### 维度二：Java Web 对标参照（同构点 vs. 异构点）

- **对应 Java 概念**：
  - `withBgLlmSlot` 对应 `java.util.concurrent.Semaphore(3, true)`（公平模式信号量）。
  - `withAuditLock` 对应 `java.util.concurrent.locks.ReentrantLock(true)`（公平互斥锁，注意本实现**不可重入**）。
  - `createExtractionPipeline(deps)` + `stores.ts` 对应 Spring `@Service` 构造器注入 `@Repository` 接口 + `@Configuration` 装配类。

| 对比维度 | Java Web 机制（参照系） | 本仓库 TS/Node/Next.js 实现（带 `path:line`） | 核心差异与迁移陷阱 |
|---|---|---|---|
| **编译期 vs. 运行时存在性** | `ChatStore`/`GraphStore` 编译为字节码 `interface`，Spring 启动时通过反射/CGLIB 扫描装入容器 | `ChatStore`/`GraphStore`（`src/core/ports.ts:34,79`）在编译为 JS 后**完全擦除**；`stores`（`src/server/stores.ts:17`）只是普通对象字面量，靠结构化类型匹配（Structural Typing）传入 `createExtractionPipeline` | TS 中无法写 `if (obj instanceof GraphStore)`；也不存在运行期按类型自动注入的容器 |
| **内存作用域与生命周期** | 锁与信号量作为字段存放在 Spring Singleton Bean 实例中，随 `ApplicationContext` 存活 | 状态挂在 `globalThis.__lhLlmSlots`（`bg-llm-semaphore.ts:46`）与 `globalThis.__lhAuditLock`（`extraction.ts:899`），由惰性初始化函数 `??=` 创建 | Next.js `next dev` 会把每个 API 路由编译为独立模块实例（见注释 `bg-llm-semaphore.ts:41-43`）；若像 Java `private static final` 那样写成模块顶层 `const`，不同路由会拿到各自的信号量副本导致限流失效 |
| **调度与并发交错边界** | 多 OS 线程抢占执行，`active++` 或队列入队必须用 CAS / AQS 锁保护，否则发生竞态 | 单线程事件循环：`if (slots.active >= PERMIT_COUNT)` 到 `slots.queue.push(ticket)`（`bg-llm-semaphore.ts:58-62`）之间**无 `await`**，天然原子执行；唯有 `await new Promise(...)`（`:60`）和 `await critical()`（`:76`）让出控制权 | 同步代码块内绝对不会发生多线程穿插；但一旦跨过 `await`，内存中其他变量可能已被别的请求修改 |
| **异常与取消传播** | 阻塞在 `semaphore.acquireInterruptibly()` 的线程收到 `Thread.interrupt()` 抛出 `InterruptedException`，AQS 自动清理等待节点 | 传入 `AbortSignal`：排队期间 abort 触发监听器将 `ticket.dead = true` 并 `reject(AbortError)`（`bg-llm-semaphore.ts:64-69`）；`withAuditLock` 则用 `await Promise.race([prev, aborted])`（`extraction.ts:916`）并在唤醒瞬间调 `signal?.throwIfAborted()`（`:917`） | JS Promise 一旦创建无法从外部强制销毁其链条，必须靠显式标记 `ticket.dead = true` 让释放方跳过死票据（`:87`），或让被取消的节点在 `finally` 中照常 `release()`（`extraction.ts:921`）以免后续排队者永久挂起 |

### 维度三：物理运行机制拆解

```mermaid
sequenceDiagram
    participant C1 as 协程 1 (Batch 1)
    participant C2 as 协程 2 (Batch 4, 需排队)
    participant Pool as globalThis.__lhLlmSlots
    participant Lock as globalThis.__lhAuditLock

    Note over C1,Pool: 1. 信号量获取（同步原子段，无 await）
    C1->>Pool: bgLlmSlots() -> active < 3 (freshTake = true)
    C1->>Pool: slots.active++ (bg-llm-semaphore.ts:74)
    C1->>C1: await critical() [挂起点：发起 LLM 抽取请求]

    Note over C2,Pool: 2. 满额排队与许可直接移交（Handoff）
    C2->>Pool: active >= 3 (freshTake = false)
    C2->>Pool: slots.queue.push(ticket) (:62)，随后 await Promise 挂起
    C1->>Pool: finally 块 (:77-91)：shift() 取出 C2 的非 dead 票据
    C1->>C2: next.resolve() (:88) —— 注意：active 不减也不加！
    C2->>C2: 从 await 恢复，因 freshTake=false 不再 active++，直接继承许可

    Note over C1,Lock: 3. Promise 链 FIFO 互斥锁（withAuditLock）
    C1->>Lock: prev = lock.tail; lock.tail = new Promise(r => release = r) (extraction.ts:900-902)
    C1->>C1: await Promise.race([prev, aborted]) (:916) [挂起点]
    C1->>C1: signal?.throwIfAborted() (:917) -> await critical() (:918)
    C1->>Lock: finally: release() (:921) 唤醒链上下一个尾节点
```

1. **信号量为什么区分 `freshTake` 与直接移交（Handoff）**：
   - 在 `withBgLlmSlot`（`src/agent/subagents/bg-llm-semaphore.ts:57-91`）中，当 `slots.active < PERMIT_COUNT` 时，`freshTake = true`，同步执行 `slots.active++`（`:74`）。
   - 当 `slots.active >= PERMIT_COUNT` 时，`freshTake = false`（`:59`），协程挂起在 `await new Promise(...)`（`:60`）。
   - 当前持有者在 `finally`（`:77-91`）退出时，从 `slots.queue.shift()` 取出排队的 `next`：若存在有效等待者，直接调用 `next.resolve()`（`:88`）而**不执行 `slots.active--`**；被唤醒的协程因为 `freshTake === false` 也**不执行 `slots.active++`**。只有队列为空（或全为 `dead`）时才执行 `slots.active--`（`:84`）。这消除了“释放者减 1、唤醒微任务尚未执行前被新来的同步调用抢走并再次累加”的计数错乱风险（见注释 `:16-20`）。
2. **`withAuditLock` 如何用 4 行代码实现 FIFO 互斥锁**：
   - 在 `withAuditLock`（`src/agent/subagents/extraction.ts:898-902`）中，进入 `await` 之前的同步段完成了「读取旧队尾 `prev = lock.tail` + 将 `lock.tail` 替换为自己控制的 `new Promise`」的原子指针交换（类似 Java AQS 中 `tail.getAndSet(node)`，但因为单线程同步执行，无需 CAS 指令）。
   - 即使等待者在排队期间因 `aborted` 分支提前 `reject` 跳入 `finally`，它的 `release()`（`:921`）依然会被调用，从而将接力棒传给链上的后继者，保证锁链永不断裂（注释 `:893-895`）。
3. **依赖如何遵循模块红线注入**：
   - 按 `eslint.config.mjs:63-68`（Zone 4），`src/agent/**` 严禁直接 `import` `src/server` 或 `src/store`。
   - 因此 `src/agent/subagents/extraction.ts` 只从 `../../core/ports.ts` 导入纯接口 `ChatStore` 与 `GraphStore`，并通过工厂函数 `createExtractionPipeline(deps: ExtractionDeps)`（`extraction.ts:803`）的参数闭包捕获存储实例；真正的组装发生在 `src/server/` 层（将 `src/server/stores.ts:17` 的 `stores` 传入）。

### 维度四：Java 惯性反模式与防坑守则

1. **反模式 1：在 `src/agent/` 下直接导入 `src/store/graph.ts` 单例**
   - **后果**：触发 `eslint.config.mjs:63-68` 的 `import/no-restricted-paths` 错误（*"The agent layer receives its dependencies (storage ports via factories/closures) — it never imports the server layer or store adapters"*），`npm run lint` 与 CI 直接失败。
2. **反模式 2：将信号量写成模块级静态变量 `const slots: LlmSlots = { active: 0, queue: [] }`**
   - **后果**：在 Next.js 开发服务器中，`/api/chat` 路由与 `/api/graph/status` 路由各自加载一份模块实例，导致并发上限变成 `3 × 路由实例数`，且状态监控路由读取到的永远是空队列。必须通过 `globalThis` + `??=`（`bg-llm-semaphore.ts:45-46`）挂载。
3. **反模式 3：像 Java `ReentrantLock` 一样在 `withAuditLock` 的 `critical()` 回调内部再次调用 `withAuditLock`**
   - **后果**：**永久死锁**。`lock.tail` 是单纯的 FIFO Promise 链，没有记录 `ownerThread`（Node 单线程中所有协程共享同一线程，也没有默认绑定 `AsyncLocalStorage` 锁重入计数）。外层 `withAuditLock` 等待内层完成才触发 `release()`，而内层又排在外层未释放的 `prev` 后面。

### 维度五：确定性测试验证对照（`node:test` vs. JUnit/Mockito）

- 在 Java Spring 中，测试抽取流水线通常需要 `@SpringBootTest` 或 `@ExtendWith(MockitoExtension.class)` + `@Mock ChatStore`。
- 在本仓库 `tests/extraction.test.ts:440` 中，直接调用工厂函数传入内存构造的假存储与假模型函数，无需任何容器或字节码代理：
  ```ts
  const pipeline = createExtractionPipeline({ chatStore, graphStore: ledgers, extractor, auditor: submitModel("submit_review", verdict) });
  ```
- 针对未配置模型或缺失 API Key 的拒绝门控测试（`tests/extraction.test.ts:2517-2518`），直接构造不同 `deps` 组合并用原生 `assert.rejects(..., ModelsNotConfiguredError)` 断言，毫秒级完成且完全脱离真实网络与磁盘配置。
