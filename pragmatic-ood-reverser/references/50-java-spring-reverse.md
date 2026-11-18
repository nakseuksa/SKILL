# Java 17+ / Spring Boot 存量系统逆向降噪与解剖指南

> **适用范围**：存量 Java 17+（含 Spring Boot 2.x / 3.x、JPA/Hibernate、MyBatis）单体或模块化单体仓库。标记 `[§x.y]` 为原文原则，`[扩展]` 为 Spring 生态逆向技巧。

---

<a id="boundaries"></a>

## 1. 框架降噪与边界识别

在 S1 活动中，面对成百上千个 Java 类，按原文 `[§24.3.1]` 的**三个抽象层次**将代码快速分流，剥离 Spring 样板噪音以显影核心业务模型：

| 抽象层次 `[§24.3.1]` | Spring / Java 存量代码中的典型载体 | 逆向处理策略（折叠 vs 放大） |
|---|---|---|
| **① 应用层概念与推广**<br/>`[1+2]`（核心目标） | 领域实体、值对象（`record` / `Money`）、业务策略接口、核心领域服务、领域事件、业务状态枚举 | **🔍 重点放大（进入 S2/S3）**：还原概念词典、7 类角色与隐式不变式 |
| **② 系统与机器资源层**<br/>`[3+4]`（边界与契约） | `@RestController`、`@Scheduled`、`@KafkaListener` / `@RabbitListener`、`FeignClient`、Spring Security 过滤器链 | **📌 提取入口与出口（用于 S3 逆向 CRC 走查）**：将其视为界面类（角色 5 `[§25.6]`）或句柄代理（角色 6 `[§25.7]`），先记录触发的业务方法；若结论依赖路由、装配、事务或鉴权，再核对对应配置 |
| **③ 底层语言与实现层**<br/>`[5+6]`（降噪折叠） | `@Configuration`、`*AutoConfiguration`、`*Properties`、MyBatis `*Mapper.xml`/生成类、JPA `*Specification` 拼装工具、通用 `Result/Page` 包装器 | **🙈 默认折叠忽略**：除非怀疑此处藏有隐式业务规则或性能瓶颈，否则不在架构地图中展开 |

### 识别物理包结构的真实形态（P01 `[§24.4 · 扩展]`）
1. **按技术水平分包型（`controller / service / dao / entity`）**：
   - 跨包调用可能增加 `public` 类型；抽查哪些成员被外包实际使用，不把可见性计数直接当作封装失效的证明。
   - **S1 还原法**：不要按物理目录画组件图！通过 `OrderController -> OrderService -> OrderMapper` 的**命名前缀聚类**与数据表归属，逆向还原出逻辑上的**隐式业务组件**（如 `ordering`、`inventory`），并检查不同前缀的 Service 之间是否存在交叉注入或双向环路（RL1 `[§24.4.2]`）。
2. **按业务特性分包 / 多 Maven/Gradle 子模块型**：
   - 检查 `pom.xml` / `build.gradle` 依赖关系与 `scan_topology.py` 输出；核查是否存在 `common` / `core` 包沦为“万金油垃圾桶”（什么业务类都往里塞，造成高入度中心耦合 RL2 `[§23.4.3.5]`）。

---

<a id="implicit"></a>

## 2. 穿透 Spring “隐式控制流与切面魔法”（S2 / S3 必查）`[§25.7 · 扩展]`

Spring 大量使用运行时动态代理（角色 6 句柄类 `[§25.7]`）和事件反射，纯看静态方法调用链会漏掉关键行为。逆向追踪主链路（S3）时必须排查以下 5 类隐式链路：

| 隐式机制 | 静态阅读容易漏掉的真相 | 逆向勘探 `grep` 命令与检查点 |
|---|---|---|
| **1. `@Transactional` 代理边界** | 事务提交/回滚发生在代理外壳出口（P19 `[§25.7.1]`）；默认代理模式下，同类自调用不会经过被调方法的代理拦截；外层已有事务仍可能有效。需核实代理模式、传播配置与调用方向 | 搜索 `@Transactional`：标出事务边界覆盖的实体修改范围；检查是否存在同类方法自调用或大事务中夹杂远程 RPC 调用（一级性能隐患 `[§23.4.7]`） |
| **2. `@EventListener` / `@TransactionalEventListener`** | `publisher.publishEvent(new OrderPaidEvent(...))` 看似只发了个对象，实则同步或异步触发了其他模块的监听器（隐式动作类 `[§25.5]`） | 搜索 `publishEvent` 与 `@EventListener` / `ApplicationListener`：将“事件发布者 → 事件类型 → 监听者”补全到 S1 组件依赖图与 S3 走查链中 |
| **3. 自定义 AOP `@Aspect` 与拦截器** | 权限校验、租户隔离（ThreadLocal）、幂等锁、审计日志往往藏在 `@Around` / `@Before` 切面或 `HandlerInterceptor` 中 | 搜索 `@Aspect`、`@Around`、`ThreadLocal`：还原调用链入口被悄悄注入的前置条件与上下文状态（防 RL10 时序耦合踩坑） |
| **4. JPA 脏检查（Dirty Checking）与级联** | 在 `@Transactional` 方法内调用 `entity.setXxx()` 后，可能在 flush 时生成 `UPDATE` 而不显式调用 `save`；要核实是否受管、事务和字段映射 | 对 JPA 实体：区分它是受管态（Managed）还是游离态；检查 `@OneToMany(cascade = ...)` 是否会在删除/修改主表时引发意外的级联写操作 |
| **5. Bean 多实现注入与 `@Primary` / `@Qualifier`** | 接口 `PaymentGateway` 被注入为 `List<PaymentGateway>` 或 `Map<String, PaymentGateway>` 做运行时路由 | 搜索接口的所有 `implements` 类及 `@ConditionalOnProperty`：还原装配期策略（P15）与运行期路由表（`[§25.4.1]`） |

---

## 3. Java / Spring 存量项目三类常见风险解剖指南 `[扩展]`

### 雷区 1：贫血 JPA/MyBatis 实体 + 3000 行过程式 Service（RL3 / RL4）
- **现状特征**：`OrderEntity` 只有字段与 Lombok `@Data`（自动生成全字段 `public setter` 及包含可变关联的 `equals/hashCode`）；`OrderServiceImpl` 注入 12 个依赖，包含几十个百行事务脚本 `[§24.2.1]`。
- **逆向解剖动作**：
  1. 在 IDE / 终端搜索 `order.setStatus(` 等核心修改方法的所有调用点，绘制**实际状态流转图**；
  2. 对 `OrderServiceImpl` 执行 **`21-invariant-mining.md` 的“方法 × 依赖/字段”矩阵聚类**，找出隐藏在其中的 3–4 个独立业务子概念。

### 雷区 2：Lombok `@Data` / `@Builder` 破坏类不变式（RL10）
- **现状特征**：类上随手贴了 `@Data` `@Builder` `@NoArgsConstructor`。
- **风险揭示**：检查构造器可见性、builder 最终调用哪个构造器、是否有校验或默认值，再判断是否存在非法状态入口 `[§24.3.7.1 · 扩展]`。对双向实体关联，核查生成的 `toString/hashCode` 是否包含该字段及其加载时机，不能只凭 `@Data` 判定运行时故障。

### 雷区 3：`common` 包与 `XxxUtil` 静态状态耦合（RL1 / RL2）
- **现状特征**：业务模块通过 `SpringContextHolder.getBean(...)` 静态方法在任意角落抓取其他模块的 Service，逃避构造器依赖声明。
- **风险揭示**：这是隐藏得最深的依赖欺骗！静态 `import` 扫描甚至可能漏掉它。逆向时务必 `grep` `getBean` / `ApplicationContext`，找到 bean 名称、装配与调用方后再补边；无法定位的注册项列为待验证。

---

## 4. 向 `pragmatic-ood-architect` 移交时的 Java 专项清单（S4 产出）

当用户在 S4 决定对某模块启动重构时，在对话或已授权的地图第 10 节列出候选项及验证条件：
1. **建议收回 `setter` 的核心实体与必须保护的隐式不变式列表**（准备改为 `record` 或带校验构造器的充血领域类 P06/P20）；
2. **建议从上帝 Service 中按字段/依赖聚类拆出的新概念清单**（输入给 `architect` 的 A2）；
3. **需要用 ArchUnit 封锁的包依赖环路列表**（输入给 `architect` 的 A4/A5）。
