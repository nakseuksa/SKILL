# 输入 JSON 字段说明

完整示例:[sample_input.json](../examples/sample_input.json)。所有金额统一使用 `meta.unit` 声明的单位。**缺失就省略字段,不要填 0 或估算值**:省略的字段会被脚本标为 n/a,填 0 则会被当成真实数据计算。

## meta

| 字段 | 必填 | 说明 |
|---|---|---|
| `name`, `ticker`, `as_of` | 是 | 名称、代码、数据截止日 |
| `route` | 是 | `general` / `cyclical` / `financial` / `reit` / `utility`,见 [routing.md](routing.md) |
| `manufacturing` | 否 | Altman 模型选择。true 用原版 Z,false 用 Z″。默认 general、cyclical 为 true,其余为 false |
| `currency`, `unit` | 是 | 例如 `"INR"`、`"₹ crore"`。**1 crore = 1000 万,1,297 crore = 129.7 亿** |
| `period_basis` | 是 | 只能是 `annual` 或 `ttm`。单季度数据不得用于现金流判断 |
| `eps_basis` | 是 | `gaap`(含 IFRS 等法定口径)或 `adjusted`。若为 adjusted,报告中必须同时给出法定口径盈亏 |
| `price` | 是 | 最新股价 |
| `eps_ttm` | 否 | 不填则用 净利润 / 股本 计算 |
| `forward_eps` | 否 | 一致预期下一财年 EPS |
| `normalized_eps` | 否 | 用户自定的正常化 EPS(周期股派息率会优先使用) |
| `dps`, `price_change_12m` | 否 | 年度每股股息;12 个月涨跌幅,用小数表示(-0.45 即下跌 45%) |
| `going_concern_doubt` | 否 | 审计报告是否含持续经营重大不确定性(true/false) |
| `sources` | 是 | 数据来源列表(文件名、页码或 URL,以及访问日期) |

## assumptions

| 字段 | 说明 |
|---|---|
| `cost_of_equity` | 权益成本 r(小数)。必须在报告中说明取值依据 |
| `growth` | 长期增长率 g(小数),必须小于 r |
| `tax_rate` | 计算 ROIC 用的税率,默认 0.25 |

## periods.t / periods.t1 / periods.t2

t 为最近一期,t1 为上一期,t2 只需要 `total_assets`(供 Piotroski 计算期初资产)。

| 字段 | 说明 |
|---|---|
| `revenue`, `cogs`, `sga` | 营收、营业成本、销售及管理费用 |
| `net_income`, `income_cont_ops` | 净利润(归母)、持续经营利润(M-Score 用,缺失时用净利润) |
| `cfo`, `cfi`, `capex` | 经营现金流、投资现金流(按报表符号填写)、资本开支(正负均可,脚本取绝对值) |
| `depreciation`, `ebit`, `interest_expense` | 折旧摊销、息税前利润、利息支出 |
| `total_assets`, `current_assets`, `current_liabilities` | 总资产、流动资产、流动负债 |
| `cash`, `receivables`, `inventory`, `other_current_assets` | 现金及等价物、应收、存货、其他流动资产 |
| `ppe_net`, `ppe_gross`, `securities` | 固定资产净值、原值、证券投资(M-Score AQI 用,缺失按 0) |
| `long_term_debt`, `total_debt`, `total_liabilities` | 长期债务、有息债务合计、负债合计 |
| `retained_earnings`, `book_equity`, `shares_outstanding` | 留存收益、归母净资产、总股本 |
| `dividends_paid` | 当期已付普通股股息 |
| `debt_due_18m`, `undrawn_credit` | 18 个月内到期债务;已承诺但未提用的授信 |
| `affo` | 仅 REIT:调整后营运资金 |

## history(按时间升序,最近一期放最后)

| 字段 | 最少期数 | 用途 |
|---|---|---|
| `eps` | 5(周期股应覆盖完整周期) | 正常化 P/E |
| `roe` | 3 | 合理 P/B 中的正常化 ROE |
| `roic` | 3 | ROIC 趋势 |
| `revenue` | 3 | 营收是否连续两年下滑 |

## signals(只报告,不参与聚合)

`estimates_trend`(down/flat/up)、`above_200dma`(bool)、`insider_net_buy`(bool)、`catalyst`(文本)。
