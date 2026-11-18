# 单点设计：Java 17 支付方式与类型码

**用户**：在设计支付模块，`PaymentInfo` 打算放一个类型码和四种支付方式的可空字段。手续费按类型切分。只要建议。

**助手 · A3**：这个草案能表示“电子钱包却填银行卡授权码”等非法组合。决定用封闭变体还是开放实现的关键不是今天恰好有四种，而是谁能增加新变体（L7 `[§24.3.4.1 · 扩展]`）。新支付方式都随主程序发布，还是插件可以独立接入？

**用户**：全都跟主程序发。我们固定 Java 17，不开预览。

**助手**：推荐 `sealed interface` 加各自的 `record`：每个变体只保存自己需要的数据，新方法不能拿到一袋互相矛盾的字段。若以后允许插件独立接入，改为开放接口更合适。

```text
设计签名（非完整 Java 源码）
PaymentMethod = Card(last4, authCode) | Wallet(walletId) | Transfer(receiptNo) | Points(count)
PaymentMethod.feeFor(amount): Money
```

Java 17 非预览可用 `sealed`、`record` 和接口方法分派，不要生成 Java 21 才正式支持的模式 `switch`。如果未来常加的是独立操作而非变体，可再评估 Visitor `[扩展]`。目前不需要先为这个问题设计整个支付系统。
