# “人与组织（Party）”领域通用数据模型范式与反例库
> **知识源**：《数据模型资源手册（第 1 卷）》第 2 章“人与组织”（2.1~2.9 节，图 2-1 ~ 图 2-14，表 2-1 ~ 表 2-13）及附录 A 人力职位/资质扩展。

本文档是 `universal-data-model-designer` 技能的**核心领域知识库**，专门服务于“人与组织（客户、供应商、内部组织、部门、雇员、签约人、联系人、家庭、地址与联系方式、物理场所设施、沟通事件与客诉案例、职位与资质技能）”设计域的数据建模。

---

## 一、 “人与组织”建模必须回答的四大核心业务问题（第 2 章导言）

任何涉及人与组织的系统数据模型，都必须能够准确、可信赖、无冗余地回答以下四个核心问题：
1. **主体本质与分类特征**：在办理业务过程中涉及到的人和组织的属性或特点是什么？他们属于哪些人口统计或行业/规模类别？
2. **角色与关系网络**：每个人或组织在企业上下文中扮演什么角色？在不同的人之间、不同的组织之间以及人和组织之间存在哪些关系？关系处于什么状态和优先级？
3. **联系机制与物理场所**：人、组织以及物理设施（大楼/仓库/办公室）的地址、电话号码和电子联系方式是什么？每个联系方式用于什么目的（如总部、账单、收货、办公、私人）？是否免推销？怎样才能同他们取得联系？
4. **通信事件与后续行动闭环**：在各种当事人之间发生了哪些类型的通信或联络（电话、面谈、邮件、会议）？围绕特定问题（案例 `CASE`）进行了哪些沟通？为了加强通信的后续工作，触发了哪些工作计划（`WORK_EFFORT`）？

---

## 二、 传统建模的四大结构性陷阱与原书经典反例（用于第 2 阶段边界拷问）

### 陷阱 1：将“组织/人员的角色”建成彼此孤立的实体表
* **错误做法**：订单系统建 `CUSTOMER`（客户表），采购系统建 `SUPPLIER`（供应商表），HR 系统建 `EMPLOYEE`（雇员表）和 `DEPARTMENT`（部门表），CRM 建 `CONTACT`（联系人表）。
* **原书反例 A（组织多重角色 —— 2.1 节）**：
  * 在大公司中，内部组织之间存在销售活动：“资产管理科”可能是“产品销售科”的一个**供应商**，同时也是“产品销售科”的一个**客户**。
  * 外部公司“ACME 公司”（`PARTY_ID = 700`）既是本企业的**客户**，又是本企业的**供应商**（表 2-4）。
  * 如果客户、供应商、部门分表存储，当组织地址或名称变更时，往往只更新了一个系统，导致企业内部信息不一致，连生成正确的邮件列表都会出错。
* **原书反例 B（人员角色随时间流转 —— 2.2 节 John Smith 案例）**：
  * John Smith（`PARTY_ID = 5000`）最初是 ABC 公司的优秀**客户联络员**；后来同 ABC 公司签订劳务合同成为**签约人（Contractor）**；最后被聘为正式**雇员（Employee）**，同时在家里是**父亲**，在车间是**组长**和**师傅**（表 2-4）。
  * 分表设计会为 John Smith 存储多条记录，导致姓名、性别、出生日期、社保号等不变信息冗余且不一致。
* **原书反例 C（人员同时兼具多重角色 —— 2.2 节 Shirley Jones 案例）**：
  * Shirley Jones（`PARTY_ID = 5500`）是运输科的**雇员**和**项目经理**，同时她是供应科的**客户**，又是出版科的**供应商**（负责传递目录）。不应为她存储三条冗余记录，而应只维护一条人员本质记录（`PERSON`）+ 多条角色记录（`PARTY_ROLE`）。

### 陷阱 2：只建角色，不建《当事人关系（`PARTY_RELATIONSHIP`）》，或把关系属性挂在人/组织上
* **错误做法**：在 `CONTACT`（联络员）或 `CUSTOMER`（客户）表上直接设置 `status`（状态）、`priority`（优先级）、`sales_rep_id`（跟进销售）、`start_date`、`comment`（备注）。
* **原书反例 A（多销售对接同一联络员的状态冲突 —— 2.5 节 Marc Martinez 案例）**：
  * ACME 公司的客户联络员 Marc Martinez（`PARTY_ID = 5300`）同时与本公司销售不同产品线的**三个销售商**打交道。
  * 销售商 1 为 Marc 销售了大量商品，关系状态是**“非常积极”**；销售商 2 长时间没有生意，关系状态是**“消极”**。
  * 如果状态、优先级、备注只绑定在“联络员（Marc）”身上，不同销售商就会根据自己的关系互相改写覆盖他人的信息！因为**状态、优先级、备注、起止日期根本不属于“联络员”本身，而是属于“某个销售代表角色 ↔ 某个客户联络员角色”之间的《当事人关系》（`PARTY_RELATIONSHIP`）**。
* **原书反例 B（客户/供应商/雇员究竟归属哪个内部组织 —— 2.5.1 节 表 2-5 & 2-6）**：
  * 说“ACME 公司是客户”或“John Smith 是雇员”是不完整的：ACME 公司究竟是 **ABC 母公司**的客户，还是 **ABC 分公司**的客户，抑或是某个具体业务科的客户？
  * 表 2-5 与表 2-6 明确展示：ACME 公司（角色：客户）与 ABC 分公司（角色：内部组织）建立 `客户关系`；Fantastic 供应公司（角色：供应商）与 ABC 分公司建立 `供应商关系`（若它是整个集团的供应商，则目标当事人应为 ABC 母公司）；John Smith（角色：雇员）与 ABC 分公司（角色：雇主）建立 `雇用关系`。

### 陷阱 3：把电话、地址、邮箱硬编码为人员/组织表的列（`address1`, `phone1`, `office_phone`, `email`）
* **错误做法**：在 `PARTY` 或 `CUSTOMER` 表内直接加固定字段 `office_phone`、`home_phone`、`fax`、`billing_address`、`shipping_address`。
* **原书反例 A（多主体共享同一物理地址与方位说明冗余 —— 2.6.1 节 表 2-9 & 2-10）**：
  * 地址编号 `2300`（纽约 Main 大街 100 号 101 房间）同时被 **ABC 公司**和 **ABC 分公司**使用（例如集团总部与子公司同楼办公，或同一办公楼内住着多名员工）。
  * 地址本身带有 `DIRECTIONS`（方位说明：走哪条路、在哪里转弯到达该地址）。如果地址不独立为实体 `POSTAL_ADDRESS`，方位说明和地址文本会被重复存储多次且极易不一致。
* **原书反例 B（同一联系方式具有多重用途 + 数量无上限 —— 2.6.4 节 表 2-11）**：
  * ABC 公司的 `Main 大街 100 号` 既是**“总部”**地址，又是**“账单查询”**地址；同时它还是 ABC 分公司的**“服务地址”**。
  * Barry Goldstein 有两个办公电话（常用办公电话、第二办公电话）、两个邮箱（办公邮箱、私人邮箱）和家庭住址。
  * 如果直接把“联系用途（`CONTACT_MECHANISM_PURPOSE_TYPE`）”放进 `PARTY_CONTACT_MECHANISM` 作主键，那么当同一地址兼作“邮寄、总部、服务”三个用途时，`PARTY_CONTACT_MECHANISM` 会重复生成三条实例，导致只跟“当事人+联系方式”相关的属性（如 `NON-SOLICITATION_INDICATOR` 免推销标志、`EXTENSION` 分机号）发生冗余！因此必须拆分为 `PARTY_CONTACT_MECHANISM` 与 `PARTY_CONTACT_MECHANISM_PURPOSE` 两张表。

### 陷阱 4：沟通记录不关联关系上下文，或缺乏案例（`CASE`）与后续工作计划（`WORK_EFFORT`）闭环
* **原书反例 A（同一对当事人先后存在不同关系 —— 2.8 节）**：
  * Marc Martinez 起初是 John Smith 所在公司的**客户联络员**，双方发生多次销售沟通；后来 Marc 跳槽到 John Smith 的公司（ABC 分公司）工作并受他领导（**上下级雇员关系**）。
  * 因此，`COMMUNICATION_EVENT`（通信事件）必须挂载在具体的 `PARTY_RELATIONSHIP`（当事人关系）上下文中，才能区分哪些沟通是作为“客户联络”发生的，哪些是作为“内部汇报”发生的。
* **原书反例 B（技术支持呼叫闭环 —— 2.8 节 表 2-13 案例 105）**：
  * 客户 Joe Schmoe 因软件持续崩溃致电技术方案组长 Jerry Red（通信事件 `3010`），质量保证经理 Larry Assure 全程关注。
  * 这三次通信（`3010` 电话报修 → `3098` 邮件发送补丁 → `3120` 电话回访确认解决）必须通过 `CASE`（事例 `105`）归集，通过 `CASE_ROLE` 明确客户、负责人、质检经理各自的角色，并通过 `COMMUNICATION_EVENT_WORK_EFFORT` 关联到具体执行动作 `WORK_EFFORT`（工作计划 `1029`：给用户发送软件补丁）。

---

## 三、 “人与组织”八大核心子模型标准结构（对标第 2 章图 2-1 ~ 图 2-14 及附录 A）

### 子模型 1：组织模型（2.1 节 图 2-1 & 表 2-1）
* `ORGANIZATION`（组织，含属性 `NAME`）分为两个互斥子类：
  1. `LEGAL_ORGANIZATION`（法定组织）：唯一可以充当**合同当事人**的组织，拥有属性 `FEDERAL_TAX_ID_NUM`（联邦税务登记号/统一社会信用代码）。子类包括：
     - `CORPORATION`（公司，如表 2-1 中的 ABC 公司、ABC 分公司、ACME 公司、Fantastic 供应公司、Hughs 货运公司）
     - `GOVERNMENT_AGENCY`（政府机构，如政府质量委员会）
  2. `INFORMAL_ORGANIZATION`（非正式组织）：不能独立签署法定合同，但可被赋予角色、责任并被人管理。子类包括：
     - `TEAM`（团队，如客户支持组）
     - `FAMILY`（家庭，如 Smith 一家，用于记录家庭关系与人口统计信息）
     - `OTHER_INFORMAL_ORGANIZATION`（其他非正式组织，如企业内部的财务科、信息系统部、客户服务科等未独立注册法人的内部科室）

### 子模型 2：人员模型 —— 基础模型 vs 备选高阶模型（2.2 节 图 2-2a & 图 2-2b）
* **方案 A：基础人员模型（图 2-2a，适用于一般企业应用）**
  * 单个 `PERSON` 实体存放自然人属性：`CURRENT_LAST_NAME`（现姓）、`CURRENT_FIRST_NAME`（现名）、`CURRENT_MIDDLE_NAME`（现中间名）、`CURRENT_PERSONAL_TITLE`（现个人头衔，如先生/博士）、`CURRENT_SUFFIX`（现称号，如小/三世）、`CURRENT_NICKNAME`（现别名）、`GENDER`（性别）、`BIRTH_DATE`（出生日期）、`HEIGHT`（身高）、`WEIGHT`（体重）、`MOTHER'S_MAIDEN_NAME`（娘家姓）、`MARITAL_STATUS`（婚姻状况）、`SOCIAL_SECURITY_NUMBER`（社保号/身份证号）、`CURRENT_PASSPORT_NUMBER`（现护照号）、`CURRENT_PASSPORT_EXPIRE_DATE`（现护照有效期）、`TOTAL_YEARS_WORK_EXPERIENCE`（总工作经验年限）、`COMMENT`（备注）。
* **方案 B：人员备选模型（图 2-2b，适用于医疗、司法、跨国差旅、高合规 HR 等需追踪多值与变更历史的场景）**
  * 将可能随时间变化或同时存在多个值的属性从 `PERSON` 剥离为独立时效实体：
    1. **姓名与外号历史**：`PERSON_NAME`（主键：`PARTY_ID` + `PERSON_NAME_TYPE_ID` + `NAME_SEQ_ID`，含 `FROM_DATE`, `THRU_DATE`, `NAME`）+ `PERSON_NAME_TYPE`（姓、名、曾用名、别名/外号）。*注：也可混合使用，在 `PERSON` 保留“现姓/现名”用于高频查询，用 `PERSON_NAME` 存历史。*
    2. **婚姻状况历史**：`MARITAL_STATUS`（主键：`PARTY_ID` + `MARITAL_STATUS_TYPE_ID` + `FROM_DATE`，含 `THRU_DATE`）+ `MARITAL_STATUS_TYPE`（单身、已婚、离异、寡居）。
    3. **体格特征历史**：`PHYSICAL_CHARACTERISTIC`（主键：`PARTY_ID` + `PHYSICAL_CHAR_TYPE_ID` + `FROM_DATE`，含 `THRU_DATE`, 字符/数值型 `VALUE`）+ `PHYSICAL_CHARACTERISTIC_TYPE`（身高、体重、血压等）。
    4. **国籍与多本护照**：`CITIZENSHIP`（公民身份，关联 `PERSON` 与 `COUNTRY`，含 `FROM_DATE`, `THRU_DATE`）→ `PASSPORT`（护照，含 `PASSPORT_ID`, `PASSPORT_NUMBER`, `ISSUE_DATE`, `EXPIRE_DATE`）。
    5. **性别分类与历史**：`GENDER_TYPE`（男、女、从男到女、从女到男、未提供），若需历史可设关联实体 `PERSON_GENDER`。

### 子模型 3：当事人超类与多维分类模型（2.3 节 图 2-3 & 表 2-3）
* **超类抽象**：`PARTY`（主键 `PARTY_ID`）作为 `PERSON` 和 `ORGANIZATION` 的超类，使所有业务关系、联系方式、角色指派统一指向 `PARTY_ID`，彻底消除互斥弧（XOR）。
* **多维动态分类**：
  * 同一个当事人可同时属于多个统计分类（如 ACME 公司同时属于“妇女企业”、“邮购公司”、“大型组织”；Marc Martinez 同时属于“西班牙裔”和“年收入 5万~25万美元”）。
  * 结构：`PARTY` (1) ↔ (N) `PARTY_CLASSIFICATION`（复合主键：`PARTY_ID` + `PARTY_TYPE_ID` + `FROM_DATE`，属性：`THRU_DATE`）(N) ↔ (1) `PARTY_TYPE`。
  * 分类子类型包括：`ORGANIZATION_CLASSIFICATION`（`MINORITY_CLASSIFICATION` 少数民族/妇女/8A 企业、`INDUSTRY_CLASSIFICATION` 行业类别、`SIZE_CLASSIFICATION` 规模类别）与 `PERSON_CLASSIFICATION`（`EEOC_CLASSIFICATION`、`INCOME_CLASSIFICATION` 收入类别）。
  * *业务价值*：用于市场细分、特定人群/行业差异化定价策略或特殊合同条款匹配，且通过起止日期保留企业规模升级等历史。

### 子模型 4：当事人角色与外部事务接入契约（2.4 节 图 2-4 & 表 2-4）
* **核心职责**：`PARTY` 定义“他本质上是谁（不变特征）”，`PARTY_TYPE` 定义“他属于什么统计分类”，而 `PARTY_ROLE` 定义“他在企业具体环境中如何行为/扮演什么身份”。特定于角色的属性（如客户的信用等级）或关系（如雇员的雇用期）只挂载在对应角色上。
* **标准结构**：
  * `PARTY_ROLE`（主键：`PARTY_ID` + `ROLE_TYPE_ID`，可选代理键 `PARTY_ROLE_ID`；含可选属性 `FROM_DATE`, `THRU_DATE` 用于“公证人”、“医生”等独立于关系的角色有效期）。
  * `ROLE_TYPE`（角色类型顶层超类，`ROLE_TYPE_ID` + `DESCRIPTION`）→ 子类 `PARTY_ROLE_TYPE`。
* **三大角色族群（图 2-4）**：
  1. **人员专属角色（`PERSON_ROLE`）**：`EMPLOYEE`（雇员）、`CONTRACTOR`（签约人）、`FAMILY_MEMBER`（家庭成员）、`CONTACT`（联络员）、`MANAGER`（管理者）、`WORKER`（工作者）。
  2. **组织专属角色（`ORGANIZATION_ROLE`）**：
     - `INTERNAL_ORGANIZATION`（内部组织：建模目标企业自身的各分子公司/部门）
     - `ORGANIZATION_UNIT`（组织单位：`PARENT_ORGANIZATION` 上级组织、`SUBSIDIARY` 分公司/子公司、`DIVISION` 分支机构、`DEPARTMENT` 部门、`OTHER_ORGANIZATION_UNIT`）
     - `DISTRIBUTION_CHANNEL`（分销渠道：`AGENT` 代理商［不买断产品］、`DISTRIBUTOR` 分销商［先买断再销售］）
     - `SUPPLIER`（供应商）、`PARTNER`（合作伙伴）、`COMPETITOR`（竞争对手）、`REGULATORY_AGENCY`（管理机构）、`ASSOCIATION`（协会）、`HOUSEHOLD`（住户）、`UNION`（工会）、`CARRIER`（承运人）。
  3. **人或组织通用角色**：
     - `CUSTOMER`（客户，进一步细分为 `BILL_TO_CUSTOMER` 付款客户、`SHIP_TO_CUSTOMER` 装运目标客户、`END_USER_CUSTOMER` 最终用户客户）
     - `PROSPECT`（潜在客户：尚无任何交易事务，但需预先标记角色）
     - `SHAREHOLDER`（股东）。
* **外部业务事务接入契约（2.4.3 & 2.4.5 节）**：
  * 当外部域（订单 `ORDER`、协议 `AGREEMENT`、发票 `INVOICE`、需求 `REQUIREMENT`、报价 `QUOTE`、预算 `BUDGET`）需要关联“人与组织”时，遵循统一的**事务角色模式**：
  * `<TRANSACTION>_ROLE`（复合主键：`<TRANSACTION>_ID` + `PARTY_ID` + `ROLE_TYPE_ID`），其角色类型 `<TRANSACTION>_ROLE_TYPE` 同样继承自超类 `ROLE_TYPE`（例如订单中的下单人、收单人、审批人）。

### 子模型 5：当事人关系及状态/优先级模型（2.5 节 图 2-5 ~ 图 2-7 & 表 2-5 ~ 表 2-8）
* **核心定理**：大多数角色（如客户、供应商、雇员、子公司、联络员）只有在**相对于另一个当事人角色**的上下文中才有完整意义！
* **通用结构（图 2-6a & 图 2-7）**：
  * `PARTY_RELATIONSHIP`：
    - 主键：`PARTY_ID_FROM`（源当事人）+ `PARTY_ID_TO`（目标当事人）+ `ROLE_TYPE_ID_FROM`（源角色类型）+ `ROLE_TYPE_ID_TO`（目标角色类型）+ `FROM_DATE`（起始日期）*（若同一角色对可对应多种关系类型，可将 `PARTY_RELATIONSHIP_TYPE_ID` 纳入主键）*。
    - 属性：`THRU_DATE`（终止日期）、`STATUS_TYPE_ID`（关联 `PARTY_RELATIONSHIP_STATUS_TYPE`，如“活跃”、“不活跃”、“谋求更多参与”）、`PRIORITY_TYPE_ID`（关联 `PRIORITY_TYPE`，如“很高”、“高”、“中等”、“低”）、`PARTY_RELATIONSHIP_TYPE_ID`、`COMMENT`（备注）。
  * `PARTY_RELATIONSHIP_TYPE`：定义关系类型名称与描述，并通过 `ROLE_TYPE_ID_VALID_FROM` 和 `ROLE_TYPE_ID_VALID_TO` 约束该关系允许连接的合法源角色与目标角色对。
* **三类典型关系实例（表 2-5 ~ 表 2-7）**：
  1. **组织 ↔ 组织关系（表 2-5）**：`ORGANIZATION_ROLLUP`（组织隶属关系：ABC 分公司 → 母公司 ABC 公司；客户服务分支机构 → ABC 分公司，支持跨期架构调整）、`CUSTOMER_RELATIONSHIP`（客户关系：ACME 公司［客户］→ ABC 分公司［内部组织］）、`SUPPLIER_RELATIONSHIP`（供应商关系）、`DISTRIBUTION_CHANNEL_RELATIONSHIP`（代理关系）、`PARTNERSHIP`（合作关系）。
  2. **人员 ↔ 组织关系（表 2-6）**：`EMPLOYMENT`（雇用关系：John Smith［雇员］→ ABC 分公司［雇主］，含离职原因 `TERMINATION_REASON_ID` 与离职类型 `TERMINATION_TYPE_ID`）、`ORGANIZATION_CONTACT_RELATIONSHIP`（组织联络员关系：Marc Martinez［客户代表］→ ACME 公司［客户］；Nancy Barry［供应商代表］→ Fantastic 供应公司［供应商］）、签约人关系。
  3. **人员 ↔ 人员关系（表 2-7）**：客户联络员关系（William Jones［ABC 分公司账户管理员］↔ Marc Martinez［客户联络员］）、供应商联络员关系（John Smith［供应商协调员］↔ Nancy Barry［供应服务联络员］）、师徒关系（师傅 ↔ 学徒）、家庭关系（父亲 ↔ 女儿）。

### 子模型 6：联系机制、邮政地址与地理范围模型（2.6 节 图 2-8 ~ 图 2-10 & 表 2-9 ~ 表 2-11）
* **完整扩展架构（图 2-10 + 图 2-8）**：
  1. `CONTACT_MECHANISM`（联系机制超类，主键 `CONTACT_MECHANISM_ID`，含 `CONTACT_MECHANISM_TYPE_ID`）：
     - 子类 1：`POSTAL_ADDRESS`（邮政地址：`ADDRESS1`, `ADDRESS2`, `DIRECTIONS` 路线方位说明）。
     - 子类 2：`TELECOMMUNICATIONS_NUMBER`（电信号码：`COUNTRY_CODE` 国家代码, `AREA_CODE` 区号, `CONTACT_NUMBER` 联系号码）。
     - 子类 3：`ELECTRONIC_ADDRESS`（电子地址：`ELECTRONIC_ADDRESS_STRING`，存储电子邮件、Web 网址、即时通讯号等）。
  2. `CONTACT_MECHANISM_LINK`（联系机制链接，自关联递归表：`CONTACT_MECHANISM_ID_FROM` → `CONTACT_MECHANISM_ID`）：表示占线自动转呼手机/呼机，或传真自动转电子邮件。
  3. `PARTY_CONTACT_MECHANISM`（当事人联系机制关联表）：
     - 主键：`PARTY_ID` + `CONTACT_MECHANISM_ID` + `FROM_DATE`。
     - 属性：`THRU_DATE`、`ROLE_TYPE_ID`（可选，限定该联系方式仅在当事人扮演某特定角色如“客户”时有效）、`NON-SOLICITATION_INDICATOR`（免推销标志）、`EXTENSION`（分机号）、`COMMENT`（备注，如最佳联系时间）。
  4. `PARTY_CONTACT_MECHANISM_PURPOSE`（当事人联系机制用途表）：
     - 主键：`PARTY_ID` + `CONTACT_MECHANISM_ID` + `CONTACT_MECHANISM_PURPOSE_ID` + `FROM_DATE`，属性 `THRU_DATE`。
     - 关联 `CONTACT_MECHANISM_PURPOSE_TYPE`（常用电话、主要传真、第二传真、总部地址、账单查询地址、服务地址、销售办公室、常用家庭地址、常用办公地址、办公邮箱、私人邮箱等）。
  5. `GEOGRAPHIC_BOUNDARY`（地理范围，图 2-8）：
     - 统一管理行政区划（`COUNTRY` 国家、`STATE` 州、`PROVINCE` 省、`COUNTY` 县、`CITY` 城市、`POSTAL_CODE` 邮政编码）与业务区域（`REGION` 地区、`SALES_TERRITORY` 销售区域、`SERVICE_TERRITORY` 服务区域）。
     - 通过 `GEOGRAPHIC_BOUNDARY_ASSOCIATION` 实现区域多对多层级包含（如将某几个城市/省份划入某销售大区）；通过 `POSTAL_ADDRESS_BOUNDARY` 将邮政地址与所属地理范围关联。

### 子模型 7：物理设施与联系机制模型（2.7 节 图 2-11）
* **为什么设施（`FACILITY`）不是地址也不是组织？**
  * 物理场所（如某栋办公大楼、某个车间、某个仓库、某个楼层或房间）有其自身的物理属性（如 `SQUARE_FOOTAGE` 平方面积）和物理包含层级（大楼包含多个楼层，楼层包含多个房间 `FACILITY` 自关联），且多个车间可能共用一个地址，一个仓库也可能有多个地址（实际街道地址 + 邮政信箱）。
* **核心结构**：
  * `FACILITY`（主键 `FACILITY_ID`，属性 `FACILITY_TYPE_ID`, `FACILITY_NAME`, `DESCRIPTION`, `SQUARE_FOOTAGE`；子类：`BUILDING` 建筑物、`FLOOR` 楼层、`ROOM` 房间、`OFFICE` 办公室、`WAREHOUSE` 仓库、`PLANT` 厂房）。
  * `PARTY_FACILITY`（原文图 2-11 亦称设施角色）：记录哪个 `PARTY` 对哪个 `FACILITY` 扮演什么 `FACILITY_ROLE_TYPE`（如拥有者、承租人、出租人、使用者、管理员）。
  * `FACILITY_CONTACT_MECHANISM`：建立设施与联系机制（如工厂总机电话、大楼收发室地址）的多对多关系。

### 子模型 8：当事人通信事件与后续追踪模型（2.8 节 图 2-12 ~ 图 2-13 & 表 2-12 ~ 表 2-13）
* **通信事件核心（图 2-12）**：
  * `COMMUNICATION_EVENT`：
    - 主键：`COMMUNICATION_EVENT_ID`。
    - 外键上下文：关联 `PARTY_RELATIONSHIP`（`PARTY_ID_FROM`, `PARTY_ID_TO`, `ROLE_TYPE_ID_FROM`, `ROLE_TYPE_ID_TO`, `FROM_DATE`）、`CONTACT_MECHANISM_TYPE_ID`（唯一通信机制类型）、`STATUS_TYPE_ID`（关联 `COMMUNICATION_EVENT_STATUS_TYPE`：已安排、正在进行、已完成、等待解决）、`CASE_ID`（所属案例）。
    - 时间与内容：`DATETIME_STARTED`（开始时间）、`DATETIME_ENDED`（结束时间）、`NOTE`（沟通纪要/备注）。
    - 子类：`PHONE_COMMUNICATION`、`FAX_COMMUNICATION`、`EMAIL_COMMUNICATION`、`FACE_TO_FACE_COMMUNICATION`、`LETTER_CORRESPONDENCE`、`WEB_SITE_COMMUNICATION`。
  * `COMMUNICATION_EVENT_PURPOSE`（通信事件目的，支持一次沟通有多个目的）：关联 `COMMUNICATION_EVENT_PURPOSE_TYPE`（子类：`SUPPORT_CALL` 技术支持呼叫、`CUSTOMER_SERVICE_CALL` 客户服务呼叫、`SALES_FOLLOW_UP` 售后跟踪、`INQUIRY` 问询、`MEETING` 会见、`CONFERENCE` 会议、`SEMINAR` 研讨会、`ACTIVITY_REQUEST` 活动邀请），含特定意图说明 `DESCRIPTION`。
  * `COMMUNICATION_EVENT_ROLE`（多人通信角色）：对于会议、研讨会或多方通话，记录每个参与 `PARTY` 的 `COMMUNICATION_EVENT_ROLE_TYPE`（呼叫者、接听者、协办人、参与者、记录员），并由 `VALID_CONTACT_MECHANISM_ROLE` 校验该通信方式下的合法角色。
* **案例归集与工作计划追踪（图 2-13）**：
  * `CASE`（事例/案例：`CASE_ID`, `STATUS_TYPE_ID`, `START_DATETIME`, `DESCRIPTION`）将围绕同一问题（如“客户软件持续崩溃”）的多次通信事件串联起来。
  * `CASE_ROLE`：记录谁对案例负责（技术方案组长）、谁是案例中的客户、谁负责质量保证（QA 经理）。
  * `COMMUNICATION_EVENT_WORK_EFFORT`：将通信事件与触发的后续行动 `WORK_EFFORT`（工作计划：程序、项目、阶段、任务、活动）进行多对多绑定（一次呼叫可产生多个待办任务，一个待办任务也可被多次跟进通信引用）。

### 子模型 9（附录 A 可选扩展）：职位体系、资质证书与技能模型
当用户的“人/组织”需求涉及精细化组织定岗定编、矩阵式汇报或人才技能/资质管理时，启用附录 A 扩展模块：
1. **职位与人岗分离（`POSITION`）**：
   * `POSITION_TYPE`（职位类型，如高级架构师、销售经理，关联薪资标准 `POSITION_TYPE_RATE` 与职责规范 `VALID_RESPONSIBILITY`）→ `POSITION`（具体设定的岗位编制实例，含全职/兼职/临时标志、预算关联）。
   * `POSITION_REPORTING_STRUCTURE`（职位汇报结构：`POSITION_ID_REPORTING_TO` ↔ `POSITION_ID_MANAGED_BY` + `FROM_DATE` + `PRIMARY_FLAG`）：汇报线建在“职位”之间而非“自然人”之间，支持主汇报线与虚线汇报，人员轮岗时组织汇报树无需重构。
   * `POSITION_FULFILLMENT`（职位履行）：记录具体 `PARTY_ID` 在某时段（`FROM_DATE` ~ `THRU_DATE`）担任哪个 `POSITION_ID`。
2. **资质、技能、培训与薪酬历史**：
   * `PARTY_QUALIFICATION`（当事人资格，子类 `DEGREE` 学位、`CERTIFICATION` 证书）+ `QUALIFICATION_TYPE`。
   * `PARTY_SKILL`（当事人技能：含 `YEARS_EXPERIENCE` 经验年限、`RATING` 评级、`SKILL_LEVEL` 技能水平、`STARTED_USING_DATE`）+ `SKILL_TYPE`。
   * `PERSON_TRAINING` + `TRAINING_CLASS_TYPE`、`RESUME`（简历）。
   * `PAY_HISTORY`（支付/薪资历史，直接挂载在 `EMPLOYMENT` 雇用关系的 5 元复合主键之上，关联 `PAY_GRADE` 工资级别与 `SALARY_STEP` 工资档位）。
