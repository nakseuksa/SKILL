# TypeScript 服务端（Next.js App Router / Node）OOD 惯用法与边界指南

> **适用范围**：单进程（单体/模块化单体）服务端 TypeScript 应用（含 Next.js 服务端与 Node 后端框架）。标记 `[§x.y]` 为原文原则，`[扩展]` 为 TS / Next.js 生态适配。

以下内联片段是**设计草图**，可能依赖项目类型与配置；可执行示例单列源码。

---

## 1. 语言特性与 OOD 缺口对照 `[扩展]`

| 语言机制 | TypeScript 服务端语义与缺口 | OOD 架构对策 |
|---|---|---|
| **结构化类型（Structural Typing）** | 形状兼容即视为子类型，可能发生**意外的隐式转换与 `is-a` 混用** | 对核心值类型/ID 使用 **Branded Type**（品牌类型）或私有属性 `readonly #brand`（P08/P09） |
| **接口运行时擦除** | `interface` / `type` 编译后完全消失，**无法在运行期对其使用 `instanceof`** | 运行期能力查询（P17）必须依赖**判别属性（`kind`）**、自定义类型守卫（`x is T`）或 `class` 实例 |
| **无包私有（Package-private）** | 只有文件级 `export` 与类内 `private`/`protected`，缺乏天然组件内可见性 | 用**每个组件单一 `index.ts` 导出入口** + **`eslint-plugin-boundaries` / `dependency-cruiser`** 封锁深层导入（P01/P04） |
| **无 `final` 关键字** | 无法在语法层面禁止类被继承或方法被子类覆盖 | 开启 `noImplicitOverride: true`；在 TS 中优先用**函数/策略注入（P15）**或闭包替代深层继承树（P14） |
| **`private` vs `#private`** | TS `private` 仅编译期检查（运行期可反射访问）；ES `#private` 为运行期硬私有 | 核心领域状态或安全敏感句柄优先用 `#private` 或模块闭包；常规字段用 `private readonly` |
| **循环 `import` 陷阱** | 模块环可能暴露 CJS 的未完成导出或触发 ESM 初始化前访问；不是每个环都会在运行时崩溃 | 纯类型引用强制使用 `import type`（`verbatimModuleSyntax: true`），并用工具强保模块依赖图为 DAG（P03） |

---

## 2. 原语落地速查（P01–P21 TypeScript 严格模式范式）

### P01–P05 & P08 · 模块局部化、Branded Type 与纯名字依赖 `[§24.3.6, §24.4 · 扩展]`
```ts
// src/modules/ordering/domain/money.ts (内部实现文件，外部仅能通过 ../index.ts 访问 P01)
declare const CurrencyBrand: unique symbol;
export type CurrencyCode = string & { readonly [CurrencyBrand]: typeof CurrencyBrand }; // P08: Branded Type

export function asCurrency(code: string): CurrencyCode { // P08: 显式命名转换函数
  if (!/^[A-Z]{3}$/.test(code)) throw new Error(`Invalid currency: ${code}`);
  return code as CurrencyCode;
}

class AuditTrail { constructor(readonly note: string) {} } // P02: 不加 export，局部化在模块内部
```

### P06–P07 & P20 · 不可变具体类型、断言函数不变式与独立辅助函数 `[§23.4.3.2, §24.3.7.1 · 扩展]`
```ts
function assertInvariant(cond: boolean, msg: string): asserts cond { // P20: TS asserts 契约断言函数
  if (!cond) throw new Error(`Invariant violation: ${msg}`);
}

export class Money { // 角色1: 具体类型 (P05: #cents 支持同类跨实例访问)
  readonly #cents: number;
  readonly currency: CurrencyCode;
  constructor(cents: number, currency: CurrencyCode) {
    assertInvariant(Number.isSafeInteger(cents) && cents >= 0, "cents must be a non-negative safe integer");
    this.#cents = cents;
    this.currency = currency;
  }
  get cents(): number { return this.#cents; } // P06: 探查操作 (Inspector)
  add(other: Money): Money { // P06: 返回新实例，维护不变式
    assertInvariant(this.currency === other.currency, "currency mismatch");
    return new Money(this.#cents + other.#cents, this.currency);
  }
}

export function sumMoney(items: readonly Money[], currency: CurrencyCode): Money { // P07: 非成员协助函数
  return items.reduce((acc, item) => acc.add(item), new Money(0, currency));
}
```

### P10–P15 · 组合委托、只读视图与装配期策略注入 `[§24.3.4, §24.4.1 · 扩展]`
```ts
export interface PricingPolicy { readonly calculateDiscount: (subtotal: Money) => Money; } // P15: 策略契约

export class Order {
  readonly #items: Money[] = []; // P11: 独占内聚包容
  readonly #policy: PricingPolicy; // P12/P15: 构造注入的策略引用
  constructor(policy: PricingPolicy) { this.#policy = policy; }
  addItem(price: Money): void { this.#items.push(price); }
  get items(): readonly Money[] { return this.#items.slice(); } // P06: 数组快照；readonly 本身只是静态约束
  discountFor(currency: CurrencyCode): Money { return this.#policy.calculateDiscount(sumMoney(this.#items, currency)); }
}
```

### P16–P19 · 类型守卫与切面句柄 `[§24.4.3, §25.7.1 · 扩展]`
**可执行示例**：[exportable.ts](../examples/code/exportable.ts)。从 `unknown` 识别运行时能力要同时查标签和可调用方法；守卫不证明返回值是字符串，`readCsv` 在边界再校验结果。已知的判别联合和外部 `unknown` 不可混为一谈。

句柄草图：
```ts
export class AuditedOrderHandle { // P19: 句柄/包装类在修改操作前后织入横切逻辑
  readonly #rep: Order;
  readonly #logs: string[] = [];
  constructor(rep: Order) { this.#rep = rep; }
  addItemWithAudit(price: Money): void {
    this.#logs.push(`before:${price.cents}`);
    this.#rep.addItem(price);
  }
}
```

### P21 · 判别联合（Discriminated Union）与 `never` 穷尽检查 `[§24.3.4.1 · 扩展]`
```ts
export type PaymentSpec =
  | { readonly kind: "card"; readonly last4: string; readonly feeRateBps: number }
  | { readonly kind: "wallet"; readonly provider: string };

export function computeFeeCents(spec: PaymentSpec, amountCents: number): number {
  switch (spec.kind) {
    case "card": return Math.floor((amountCents * spec.feeRateBps) / 10_000);
    case "wallet": return 0;
    default: {
      const _exhaustive: never = spec; // P21: 新增变体分支但漏写 case 时，编译期直接报错
      return _exhaustive;
    }
  }
}
```

---

## 3. 组件边界与无环工具（将 P01/P03 转化为静态检查）`[扩展]`

### 3.1 目录规范与 Barrel（`index.ts`）收口
```text
src/
├── app/                          # Next.js 路由与页面层（仅做薄适配，不含业务规则）
└── modules/
    └── ordering/
        ├── index.ts              # P01: 组件唯一公开界面（仅导出公共类型与用例入口）
        ├── domain/               # 核心领域概念、值对象、领域规则（零框架依赖）
        └── internal/             # P01 X_impl: 数据访问实现、外部 SDK 适配器（严禁跨模块直接导入）
```

### 3.2 `dependency-cruiser` 架构规则草稿（A5 产出物 `.dependency-cruiser.cjs`）
```js
module.exports = {
  forbidden: [
    { name: "no-circular", severity: "error", from: {}, to: { circular: true } }, // P03: 严禁循环依赖
    { name: "ordering-public-entry", severity: "error", // P01: 其他组件和 app 只能访问 ordering/index.ts
      from: { pathNot: "^src/modules/ordering/" },
      to: { path: "^src/modules/ordering/", pathNot: "^src/modules/ordering/index\\.ts$" } },
    { name: "domain-no-framework", severity: "error", // 框架引力防线：domain 不得依赖 next 或 ORM
      from: { path: "^src/modules/[^/]+/domain/" },
      to: { path: "(?:^|/node_modules/)(?:next|@prisma/client|drizzle-orm)(?:/|$)" } }
  ]
};
```

---

上例只为 `ordering` 示范入口规则，其他组件要分别配置。按项目的别名和依赖解析方式，用“从外部导入 index 应通过、深层导入应失败”两个 fixture 验证。文件级无环也不自动证明组件级无环，要另查聚合后的组件图。

## 4. Next.js 服务端架构纪律与框架引力检查 `[扩展]`

### 4.1 四条核心隔离纪律（版本中立）
1. **领域代码移出 `app/`**：组件与领域模型统一放在 `src/modules/<component>/`，`app/` 仅负责路由组织、UI 渲染与协议转换。
2. **服务端边界锁定**：在包含数据库凭据或核心服务端逻辑的模块入口添加 `import 'server-only'`，防止被客户端组件误打包泄露。
3. **Server Actions 与 Route Handlers 只做“薄界面类（角色 5）”**：
   - **重要安全基线**：Server Action 本质上是公开暴露的 HTTP 端点！在任何受保护的读写或副作用之前，验证会话（认证）、输入结构与范围，并按当前用户和目标资源检查权限（授权）；不要把客户端传来的用户 ID 当作身份。然后调用 `src/modules/*/index.ts` 的公开方法。
4. **数据访问集中收口**：查询与持久化逻辑集中在组件内部的数据访问层（Repository / Query），禁止在页面组件或 Server Action 中直接拼装复杂事务。

### 4.2 框架引力检查表（R0 逆向与 A4 审查必查）

| 腐化信号（坏味道） | 违反原语/试金石 | 修正方案 |
|---|---|---|
| 领域类 `import { cookies, headers } from 'next/headers'` | L4 双实现检验 / L8 同一抽象层次 | 将所需的用户身份/区域提取为纯领域参数传入，使领域组件可在脱离 Next.js 的单测或 CLI 中独立运行 |
| 几百行库存扣减与计费逻辑直接写在 Server Action 内 | `[§24.2.1]` 忽视类（退化为过程式脚本） | 提炼领域类与组件服务，Server Action 保持 ≤ 15 行（校验 + 鉴权 + 调组件 + 返回结果） |
| 直接把 Prisma / Drizzle 生成的表记录类型作为组件公开返回值 | P01 实现泄漏 / P08 映射方向反转 | **轻量档**可在单模块内使用只读投影类型；**标准/严格档**在组件边界映射为领域类型或契约 DTO |
