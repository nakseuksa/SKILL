# TypeScript 服务端（Next.js / Node）存量系统逆向降噪与解剖指南

> **适用范围**：存量服务端 TypeScript 应用（Next.js App Router / Pages Router、Node / NestJS / Express、Prisma / Drizzle）单体或 Monorepo 仓库。标记 `[§x.y]` 为原文原则，`[扩展]` 为 TS / Next.js 生态逆向技巧。

---

<a id="boundaries"></a>

## 1. 框架降噪与边界识别

面对 Next.js 全栈仓库或 Node 服务端项目，在 S1 活动中按原文 `[§24.3.1]` 的**三个抽象层次**剥离前后端与路由噪音，定位真正的服务端业务模型：

| 抽象层次 `[§24.3.1]` | TS / Next.js 存量代码中的典型载体 | 逆向处理策略（折叠 vs 放大） |
|---|---|---|
| **① 应用层概念与推广**<br/>`[1+2]`（核心目标） | `src/modules/*`、`src/core/*`、`src/domain/*`、`src/server/*` 下的业务类、判别联合类型（P21）、领域函数、`zod` 业务规则 Schema | **🔍 重点放大（进入 S2/S3）**：还原概念词典、7 类角色、判别联合变体与隐式不变式 |
| **② 系统与机器资源层**<br/>`[3+4]`（边界与契约） | `app/**/route.ts`（Route Handlers）、`"use server"`（Server Actions）、`middleware.ts`、外部 SDK 客户端、队列 Worker | **📌 提取入口与边界契约（用于 S3 逆向 CRC 走查）**：将其视为界面类（角色 5 `[§25.6]`），重点检查其是否完成了鉴权、输入校验与业务转发 |
| **③ 底层与纯客户端视图**<br/>`[5+6]`（降噪折叠） | `"use client"` 纯 UI 组件、Tailwind/CSS 样式、React Hooks 状态、Next.js `layout.tsx/loading.tsx`、ORM 自动生成类型文件 | **🙈 默认折叠忽略**：除非发现有人把核心服务端业务规则错写进了客户端组件或页面文件（触发 RL9 跨层混杂预警） |

### 识别 TS 项目的真实模块边界（P01 `[§24.4 · 扩展]`）
1. **标准模块化结构（`src/modules/<name>/index.ts`）**：
   - 从脚本给出的导入位置抽查实际目标，结合搜索判断调用方是否通过约定的 `index.ts`（Barrel）导入，还是存在跨模块直接深层导入 `../ordering/internal/helper` 的越权行为（RL1）。
2. **扁平 `lib/ + utils/ + app/` 混杂结构**：
   - 许多 Next.js 存量项目没有划分业务模块，所有服务端逻辑散落在 `src/lib/`、`src/actions/` 和 `app/api/` 中。
   - **S1 还原法**：根据操作的核心数据模型（如 Prisma 表分组或核心领域对象）将散落的文件按**业务主题聚类**为逻辑组件，并检查 `lib/` 下是否存在被全库到处引用的“万金油巨型文件”（RL2 `[§23.4.3.5]`）。

---

<a id="implicit"></a>

## 2. 穿透 TS / Next.js “隐式耦合与运行时陷阱”（S2 / S3 必查）`[扩展]`

TypeScript 的类型系统在编译后完全擦除，且 Next.js 混合了服务端与客户端执行环境。逆向勘探时必须重点排查以下 5 类隐式机制：

| 隐式机制 / 陷阱 | 静态看代码容易漏掉的真相 | 逆向勘探 `grep` 命令与检查点 |
|---|---|---|
| **1. Barrel (`index.ts`) 引发的隐藏循环依赖** | 模块 A 导入 `modules/B/index.ts`，而 `B/index.ts` 重导出了 `B/service.ts`，后者又导入了模块 A——只有形成实际值依赖且求值顺序相关时才有初始化风险（P03 `[§24.4.2 · 扩展]`） | 对照两张导入图，检查编译设置与模块顶层读取；`import type` 不会引入运行时加载，值候选边也未必保留在编译产物中 |
| **2. `"use server"` 的信任边界** | 将可达的 Server Action 当作外部输入边界；指令本身不能证明函数在当前构建中可达，也不能证明授权与参数校验已生效 | 搜索 `"use server"`：逐一核查每个导出函数入口是否有会话鉴权（AuthZ）与运行时 Schema 校验（如 `zod.parse`，对应 P16/P20） |
| **3. 结构化类型导致的“意外兼容”** | TS 中两个毫无关系的 `interface` 只要属性形状相同（如 `UserId` 与 `OrderId` 都是 `string`，或两个配置对象字段重合），就能静默互相赋值（P08/P09 `[§24.3.6]`） | 检查核心领域函数参数：是否全部用原始 `string/number` 或宽泛接口传递关键 ID 与金额？标出容易传反参数的危险调用点 |
| **4. 服务端模块被客户端组件误导入** | 若存放数据库或密钥逻辑的文件未加 `import "server-only"`，一旦被 `"use client"` 组件间接导入，会导致构建报错或敏感逻辑泄漏 | 搜索 `"use client"` 文件的 `import` 链，核实值导入、编译端与构建行为；只看到类型引用不等于代码出现在客户端 |
| **5. 运行时类型守卫缺失（`as SomeType` 欺骗）** | 代码中用 `JSON.parse(str) as OrderPayload` 或 `req.json() as Xxx` 做类型断言——这只欺骗了编译器，运行时没有任何校验 `[§24.2.3]`！ | 搜索 ` as ` 与 `any`：凡在外部 I/O、数据库 JSON 列或第三方 API 返回处仅用 `as` 强转而无运行时守卫（P16/P17）的位置，继续追查上游解析和输入来源；仅当可达路径确实缺少约束时再标出风险 |

---

## 3. TS / Next.js 存量项目三类常见风险解剖指南 `[扩展]`

### 雷区 1：Server Action / Route Handler 沦为百行事务脚本（RL3 / RL9）
- **现状特征**：`app/api/checkout/route.ts` 或 `actions/order.ts` 长达 400 行，从读取 `cookies()`、查 Prisma 表、算优惠券折扣、扣减库存到发邮件全写在一个函数里 `[§24.2.1, §23.4.3.4]`。
- **逆向解剖动作**：
  1. 在 S3 走查时，将该函数按 `[§24.3.1]` 拆解标注为三段：`[机器资源层：请求解析与鉴权]` $\rightarrow$ `[应用概念层：核心业务规则与状态不变式]` $\rightarrow$ `[实现层：Prisma 事务落库与副作用]`；
  2. 提取其中暗含的业务不变式（如库存非负、状态流转条件）记入地图第 5 节。

### 雷区 2：用可选属性拼盘代替判别联合（RL4 / RL8）
- **现状特征**：定义 `interface Task { status: string; resultUrl?: string; errorCode?: number; retryCount?: number; ... }`，所有分支字段全加 `?` 可选符 `[§23.4.3.5]`。
- **风险揭示**：编译器无法阻止 `status === "SUCCESS"` 时 `resultUrl` 为 `undefined` 的非法状态组合 `[§24.3.7.1]`，导致业务代码里到处是 `task.resultUrl!` 非空感叹号强行断言。

### 雷区 3：ORM 生成类型穿透全栈（RL5）
- **现状特征**：直接把 Prisma 生成的包含全表字段（甚至含 `passwordHash` 或内部标志位）的类型直接从数据层一路返回给组件公开界面乃至前端页面（违反 P01/P04 `[§24.4.2]`）。

---

## 4. 向 `pragmatic-ood-architect` 移交时的 TS 专项清单（S4 产出）

当用户在 S4 决定启动重构时，在对话或已授权的地图第 10 节列出候选项及验证条件：
1. **需从 `app/` 路由或 Server Action 中剥离到 `src/modules/<name>/domain/` 的核心业务概念清单**；
2. **需将“多可选属性拼盘接口”改造为 P21 判别联合（Discriminated Union + `never`）或具体值类型（`Money` 等）的清单**；
3. **需消灭的 `as` 裸断言及需要补齐 `zod` 边界校验的公开入口清单**。
