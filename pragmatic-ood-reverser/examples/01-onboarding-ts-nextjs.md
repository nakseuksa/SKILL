# 速览：类型环是不是运行时环？

这是 Next.js 服务端模块的最小示意，不含框架启动代码。将 `examples/fixtures/ts` 视为目标仓库根；以下路径都相对于它。可复跑 `python3 scripts/scan_topology.py examples/fixtures/ts`（从 Skill 根执行）。

**用户**：刚接手，先只看服务端订单和发票模块，不写地图。

**答复（`onboarding`，只读）**：先读 `amount`，再看两个数据类型；暂时不用追一条“运行时循环调用”。

| 层级 | 证据与结论 |
|---|---|
| 已观察 | `src/modules/ordering/order.ts:L1` 和 `src/modules/billing/invoice.ts:L1` 的导入都是 `import type`。含类型的物理分组图有环，值候选图的已解析跨组边中未发现环 `[§24.4.2 · 扩展]`。 |
| 已观察 | `amount` 在 `src/modules/ordering/order.ts:L6-L8` 调用 `cents`；它来自同文件 L2 的 `@shop/money`，样本没有可解析的映射。 |
| 推断 | `Order`、`Invoice` 共享类型契约；这两条纯类型边不导致模块运行时互相加载。源码没展示 HTTP 入口，不能据此宣称这是整个下单调用链。 |
| 待验证 | 提供真实项目时先看该别名的构建配置与调用 `amount` 的服务端入口，再判断金额转换和边界。 |

**若用户随后说**“不用问，直接生成地图并保存”：才使用默认 `docs/architecture/ood-system-map.md`；把这两个文件列为精读样本，未提供路由、别名目标列为未检查。不把抽样写成全系统覆盖。此示例本身不创建地图。
