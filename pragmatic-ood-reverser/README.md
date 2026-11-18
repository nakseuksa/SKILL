# pragmatic-ood-reverser

用于接手或修改既存 **Java 17+/Spring Boot**、**服务端 TypeScript/Next.js/Node** 单体的逆向 OOD Skill。执行协议和加载入口在 [SKILL.md](./SKILL.md)；三个可复核的示例在 `examples/`，对应的最小源码在 `examples/fixtures/`。默认只读；地图是可选交付物，不是分析的前提。

## 本地检查

从本仓库根运行（Python 3.9+，仅标准库）：

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/check_citations.py
python3 -B scripts/scan_topology.py examples/fixtures/ts
python3 -B scripts/scan_topology.py examples/fixtures/java
```

扫描器只读目标并输出 Markdown。路径相对于传入的扫描根；混合目录按语言分别报告，亦可传 `--language java17` 或 `--language ts-server`。未解析不是无依赖，分组强连通也不等于存在文件级运行时调用环。校验器检查原文章节编号、仓库内文档路由以及各阶段加载的 Markdown 字节数，不判断书中原则在目标项目里是否成立。

## 行为验收（在临时工作区使用 Skill）

| 提示 / 条件 | 应观察到的结果 |
|---|---|
| 对 TS 样本说“快速摸底，只 review” | 能指出声明环及未解析的 `@shop/money`；不声称存在运行时环，无新增地图。 |
| 对 Java 样本说“评估部分退款，不要落盘” | 定位 `RefundService.refund` 与 `Order.markRefunded`；标明幂等/持久化未验证，工作区不变。 |
| 给出旧地图，修改焦点源码后说“深度解剖，只读” | 对比基线、重读当前符号；不采信已过时行号，不刷新旧地图。 |
| 依次说“保存评估”→ 确认路径 → “继续看下一条链路” | 只在路径不明时问一次，后续只更新已核实章节并保留人工笔记。 |
| 说“不用问，直接生成地图并保存” | 在默认或指定路径交付；列明精读样本与未覆盖范围，不把抽样写成全量验证。 |

上表用于检查宿主中模型的实际表现；单元测试覆盖脚本与文档契约，不代替真实会话验收。
