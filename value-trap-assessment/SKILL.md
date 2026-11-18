---
name: value-trap-assessment
description: >-
  评估个股是否为"价值陷阱"(低估值但基本面结构性恶化)。按路由(一般 / 周期 / 金融 / REIT / 公用事业)
  计算估值成因、资本回报、盈余质量(Sloan、C-Score、M-Score)、边际动量(F-Score)、生存能力(Altman Z、杠杆、现金跑道)
  和股息可持续性六类指标,并标注证据等级,输出结构化评估报告。
  适用场景:用户问某只股票"是不是价值陷阱""便宜是否有原因""高股息能否持续""破净股能不能买""低 PE 是不是周期顶点"。
  不适用:给出买卖建议或目标价、预测短期股价。
---

# 个股价值陷阱评估

本 skill 依据《终版裁决报告:价值陷阱》修订后的框架。核心原则:**低估值 ≠ 低估;陷阱无法凭指标事前确认,只能做风险诊断。**

## 不可违反的原则

1. **除生存硬约束外,不做一票否决。** 只有两种情况可以单独判定"高陷阱风险":审计意见含持续经营疑虑;现金跑道 < 6 个月且 18 个月到期债务超过可用流动性。其余指标只参与分类聚合。
2. **不编造数据。** 查不到就标"n/a"并说明,不估算、不填 0。每个数字都必须注明来源和访问日期。
3. **先核对口径再计算**(这三类错误都在原文中出现过):
   - 单位:1 crore = 1000 万,₹1,297 crore = 129.7 亿卢比。
   - EPS:法定口径和调整后口径都要列出。
   - FCF:用 CFO − CapEx;使用公司自定义口径时须标明。只用年度或 TTM 数据,不用单季度。
4. **先定路由。** 周期股走专用通道,F-Score、营收下滑、单期 ROE < r 不作否决依据;金融业豁免现金流类指标、Altman Z、F-Score。详见 [routing.md](references/routing.md)。
5. **Sloan 比率只做单向使用。** 高正应计是红旗;大幅负值只提示核查 CFI。
6. **每条结论都标证据等级**(A 一手来源 / B 可复算 / D 学术模型 / E 启发式),并在报告中声明:阈值未经样本外校准,没有已知的事前命中率。
7. **"低陷阱风险"不等于"低估",更不是买入建议。** 报告必须包含反方论证。
8. 引用研究时按 [thresholds.md](references/thresholds.md) 末尾的"已更正的常见引用错误"表述,例如 Piotroski 23% 是多空组合收益,Z″ 阈值为 1.1 / 2.6。

## 工作流程

### 第 1 步:明确对象
确认股票代码、上市地、报告币种,以及用户的关注点(破净、高股息、低 PE、周期等)。信息不清楚时先问用户。

### 第 2 步:采集数据
- 数据来源优先级:年报 / 10-K / 20-F 等法定披露 > 交易所公告 > 公司投资者关系页面 > 数据商。可以使用联网搜索,但每个数字都要保留来源。
- 需要的字段及最少期数见 [input_schema.md](references/input_schema.md):两期完整报表、t-2 期总资产、≥5 年 EPS、≥3 年 ROE / ROIC / 营收。
- 权益成本 r 和增长率 g 必须写明取值依据(例如无风险利率 + β × 风险溢价)。
- 在 `<appDataDir>/brain/<conversation-id>/scratch/` 或用户工作区建立 `<ticker>_input.json`,格式照 [sample_input.json](examples/sample_input.json)。

### 第 3 步:运行脚本
```
python <skill_dir>/scripts/value_trap_metrics.py <ticker>_input.json
python <skill_dir>/scripts/value_trap_metrics.py <ticker>_input.json --json
```
`<skill_dir>` 为本文件所在目录。Windows 下脚本已自行处理 UTF-8 输出。

**验证:**
- 输出顶部若有"口径警告",逐条处理后重跑;
- 缺失率 > 40% 时脚本会判"证据不足",此时应补数据,不要下结论;
- 抽查一个数值(如派息率、Z 值)手工复算,确认输入单位无误。

修改脚本后须运行测试:`python -m unittest discover -s <skill_dir>/scripts -p "test_*.py"`

### 第 4 步:人工判断
脚本只覆盖可量化部分。还须完成:
- 路由对应的人工补充检查([routing.md](references/routing.md));
- 定性检查:技术或渠道替代、资本配置记录、治理、可验证的催化剂;
- 反方论证:用最强的论据说明为什么它**不是**陷阱,以及体系可能误杀它的原因(周期底部、无形资产费用化、一次性减值)。

可以推翻脚本初判,但必须写明理由。

### 第 5 步:输出报告
按 [report_template.md](resources/report_template.md) 输出,必须包括:
1. 结论(高陷阱风险 / 需深挖 / 低陷阱风险 / 证据不足)及置信度;
2. 两句证伪练习:为什么便宜、什么会让它不再便宜;出现什么数据就证明判断错误;
3. 口径核对表与数据来源;
4. 六类诊断,附证据等级;
5. 反方论证;
6. 局限与复查时点。

报告较长时写入 artifact 文件,对话中只给出结论和关键风险。

## 结论聚合规则(脚本内置,启发式)

- 类别:≥2 个红,或触发硬约束 → 红;1 个红或至少 1 个橙 → 橙;只有绿 → 绿。
- 总体:触发硬约束 → 高陷阱风险;缺失率 > 40% → 证据不足;≥2 个红色类别 → 高陷阱风险;1 个红色类别或 ≥3 个橙色类别 → 需深挖;其他 → 低陷阱风险。
- 时机信号(200 日线、内部人交易、盈利预测趋势)只报告,不参与聚合。

## 文件索引

| 文件 | 用途 |
|---|---|
| [scripts/value_trap_metrics.py](scripts/value_trap_metrics.py) | 指标计算与聚合(纯标准库) |
| [scripts/test_value_trap_metrics.py](scripts/test_value_trap_metrics.py) | 单元测试,期望值均为手工复算 |
| [examples/sample_input.json](examples/sample_input.json) | 虚构公司示例输入 |
| [references/input_schema.md](references/input_schema.md) | 输入字段说明 |
| [references/routing.md](references/routing.md) | 路由、指标豁免矩阵、周期股通道 |
| [references/thresholds.md](references/thresholds.md) | 公式出处、阈值、证据等级、引用勘误 |
| [resources/report_template.md](resources/report_template.md) | 报告模板 |
