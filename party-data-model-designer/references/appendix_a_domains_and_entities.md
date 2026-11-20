# 附录 A：“人与组织（Party）”设计域标准定义域与逻辑数据模型实体属性字典

本文档严格依据《数据模型资源手册（第 1 卷）》附录 A（表 A-1、表 A-2）及第 2 章正文整理，专门收录**“人与组织”设计域全集（第 2 章全部模块）+ 附录 A 职位/资质/技能扩展模块 + 外部事务角色接入契约**的完整实体和属性定义。

---

## 一、 附录 A 标准定义域规范（表 A-1）

在生成“人与组织”逻辑数据模型属性字典时，每个属性必须严格指定以下定义域（Domain）之一：

| 定义域名称 (Domain) | 原书数据类型 | 原书建议长度 | 推荐现代物理类型 (PostgreSQL / MySQL) | 用途说明 |
| :--- | :--- | :--- | :--- | :--- |
| **ID** (标识) | 数值 | 10 | `BIGINT` / `VARCHAR(36)` | 顺序号或唯一标识，用于保证实体唯一性及外键关联 |
| **Name** (名称) | Varchar | 40 | `VARCHAR(64)` | 用于记录姓名、组织名称、设施名称、关系名称、职位名称等 |
| **Short Varchar** | Varchar | 40 | `VARCHAR(64)` | 用于记录较短的字符串值（如电话号码 `CONTACT_NUMBER`、地理编码 `GEO_CODE`、缩写） |
| **Description** (描述) | Varchar | 255 | `VARCHAR(255)` | 用于保存实体或类型字典（`*_TYPE`）的描述性信息 |
| **Comment** (备注) | Varchar | 255 | `VARCHAR(500)` | 用于存储格式自由的备注文本以对实体实例进行描述 |
| **Long Varchar** | Varchar | 255 | `VARCHAR(500)` / `TEXT` | 用于需要较长字符串值的属性（如地址行 `ADDRESS1`/`2`、方位说明 `DIRECTIONS`、电子地址串 `ELECTRONIC_ADDRESS_STRING`） |
| **Very Long** | Varchar | 2000 | `TEXT` | 用于需要非常长的字符串值的属性（如简历长文本等） |
| **Very Short** | Varchar | 10 | `VARCHAR(16)` | 用于非常短的字符串值（如电话分机号 `EXTENSION`） |
| **Indicator** (标志) | 字符 | 1 | `CHAR(1)` / `BOOLEAN` | 单字符标志或指示属性，如免推销标志 `NON-SOLICITATION_INDICATOR`（Y/N）、性别 `GENDER`、婚姻状况 `MARITAL_STATUS`、全职标志 `FULLTIME_FLAG` |
| **Numeric** (无小数数值) | 数值 | 无小数点 | `INTEGER` / `BIGINT` | 无小数点数值（如身高、体重、社保号、税务号、国家/地区代码、面积、工作年限） |
| **Currency Amount** (金额) | 数值或金额 | 9位数字+2位小数 | `DECIMAL(18, 2)` | 保存货币金额值，精确到分（如薪资金额、当事人费率、允许耗费资金） |
| **Floating point** (浮点数) | Float | 9位数字+4位小数 | `DECIMAL(12, 4)` | 记录百分比、费率或需要多位小数的属性（如雇主支付福利百分比） |
| **Datetime** (日期时间) | Date | - | `DATE` / `TIMESTAMPTZ` | 保存任意日期或时间戳属性（如 `BIRTH_DATE`, `FROM_DATE`, `THRU_DATE`, `DATETIME_STARTED`） |
| **Blob** (二进制大型对象) | Blob | - | `BYTEA` / `LONGBLOB` / URI | 图像、图形、二进制数据和存储数字对象信息的属性 |

---

## 二、 “人与组织”核心实体与属性完整字典（表 A-2 逐字段对齐）

### 模块 1：当事人超类、组织、人员（含图 2-2b 备选模型）与当事人类别（2.1 ~ 2.3 节）

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **PARTY (当事人)** | `PARTY_ID` | 当事人标识 | 是 | 否 | ID | 人员与组织的顶层超类主键 |
| **ORGANIZATION (组织)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `PARTY` |
| | `NAME` | 名称 | 否 | 否 | Name | 组织名称（如 ABC 公司、财务科、Smith 一家） |
| **LEGAL_ORGANIZATION (法定组织)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `ORGANIZATION`；唯一可作为合同当事人的组织 |
| | `FEDERAL_TAX_ID_NUM` | 联邦税务标识号 | 否 | 否 | Numeric | 税务登记号 / 统一社会信用代码 |
| **CORPORATION (公司)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `LEGAL_ORGANIZATION` |
| **GOVERNMENT_AGENCY (政府机构)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `LEGAL_ORGANIZATION` |
| **INFORMAL_ORGANIZATION (非正式组织)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `ORGANIZATION` |
| **TEAM (团队)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `INFORMAL_ORGANIZATION` |
| **FAMILY (家庭)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `INFORMAL_ORGANIZATION` |
| **OTHER_INFORMAL_ORGANIZATION (其他非正式组织)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `INFORMAL_ORGANIZATION`（如内部科室/小组） |
| **PERSON (人员 —— 基础模型 图 2-2a)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 继承自 `PARTY` |
| | `CURRENT_LAST_NAME` | 现姓 | 否 | 否 | Name | |
| | `CURRENT_FIRST_NAME` | 现名 | 否 | 否 | Name | |
| | `CURRENT_MIDDLE_NAME` | 现中间名 | 否 | 否 | Name | |
| | `CURRENT_PERSONAL_TITLE` | 现个人头衔 | 否 | 否 | Name | 如先生、女士、博士 |
| | `CURRENT_SUFFIX` | 现称号 | 否 | 否 | Name | 如大、小、三世 |
| | `CURRENT_NICKNAME` | 现别名 | 否 | 否 | Name | 现绰号/外号 |
| | `GENDER` | 性别 | 否 | 否 | Indicator | |
| | `BIRTH_DATE` | 出生日期 | 否 | 否 | Datetime | |
| | `HEIGHT` | 身高 | 否 | 否 | Numeric | |
| | `WEIGHT` | 体重 | 否 | 否 | Numeric | |
| | `MOTHER'S_MAIDEN_NAME` | 娘家姓 | 否 | 否 | Name | 常用于安全校验问题 |
| | `MARITAL_STATUS` | 婚姻状况 | 否 | 否 | Indicator | |
| | `SOCIAL_SECURITY_NUMBER` | 社会保险号 | 否 | 否 | Numeric | 社保号 / 身份证件号 |
| | `CURRENT_PASSPORT_NUMBER` | 当前护照号码 | 否 | 否 | Numeric | |
| | `CURRENT_PASSPORT_EXPIRE_DATE` | 当前护照有效期限 | 否 | 否 | Datetime | |
| | `TOTAL_YEARS_WORK_EXPERIENCE` | 总工作年限 | 否 | 否 | Numeric | |
| | `COMMENT` | 备注 | 否 | 否 | Comment | |
| **人员备选模型扩展实体（第 2.2 节 图 2-2b，按需启用）** | `PERSON_NAME` (人员名字) | 名字序列编号 `#NAME_SEQ_ID` [PK]、`PARTY_ID` [PK, FK]、`PERSON_NAME_TYPE_ID` [PK, FK]、`FROM_DATE` (起始日期)、`THRU_DATE` (终止日期)、`NAME` (名字) | - | - | - | 关联 `PERSON_NAME_TYPE` (`#PERSON_NAME_TYPE_ID`, `DESCRIPTION`：姓/名/别名等)，追踪改名与多外号历史 |
| | `MARITAL_STATUS` (婚姻状况历史) | `PARTY_ID` [PK, FK]、`MARITAL_STATUS_TYPE_ID` [PK, FK]、`#FROM_DATE` [PK]、`THRU_DATE` | - | - | - | 关联 `MARITAL_STATUS_TYPE` (`#MARITAL_STATUS_TYPE_ID`, `DESCRIPTION`：单身/已婚/离异/寡居) |
| | `PHYSICAL_CHARACTERISTIC` (体格特征历史) | `PARTY_ID` [PK, FK]、`PHYSICAL_CHAR_TYPE_ID` [PK, FK]、`#FROM_DATE` [PK]、`THRU_DATE`、`VALUE` (评值，字符/数值型) | - | - | - | 关联 `PHYSICAL_CHARACTERISTIC_TYPE` (`#PHYSICAL_CHAR_TYPE_ID`, `DESCRIPTION`：身高/体重/血压) |
| | `CITIZENSHIP` (公民身份) & `PASSPORT` (护照) | `CITIZENSHIP` (`PARTY_ID` [PK, FK], `GEO_ID/COUNTRY` [PK, FK], `#FROM_DATE` [PK], `THRU_DATE`)；`PASSPORT` (`#PASSPORT_ID` [PK], `PASSPORT_NUMBER`, `ISSUE_DATE`, `EXPIRE_DATE`) | - | - | - | 支持多国籍与多本历史护照追踪 |
| **PARTY_TYPE (当事人类型)** | `PARTY_TYPE_ID` | 当事人类型标识 | 是 | 否 | ID | 存储人口统计、行业、规模等分类字典 |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如少数民族企业、制造业、大型组织、西班牙裔等 |
| **PARTY_CLASSIFICATION (当事人分类)** | `FROM_DATE` | 起始日期 | 是 | 否 | Datetime | 分类生效日期 |
| | `PARTY_TYPE_ID` | 当事人类型标识 | 是 | 是 | ID | 关联 `PARTY_TYPE` |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY` |
| | `THRU_DATE` | 终止日期 | 否 | 否 | Datetime | 分类失效日期 |
| **当事人类别子类（均共享主键 `FROM_DATE` [PK, FK] + `PARTY_TYPE_ID` [PK, FK] + `PARTY_ID` [PK, FK]）** | `ORGANIZATION_CLASSIFICATION` (组织分类)、`MINORITY_CLASSIFICATION` (少数派分类)、`INDUSTRY_CLASSIFICATION` (行业分类)、`SIZE_CLASSIFICATION` (规模分类)、`PERSON_CLASSIFICATION` (人员分类)、`EEOC_CLASSIFICATION` (均等就业机会委员会分类)、`INCOME_CLASSIFICATION` (收入分类) | 同 `PARTY_CLASSIFICATION` 三元复合主键 | 是 | 是 | Datetime / ID | 图 2-3 当事人类别子类型层次 |

---

### 模块 2：当事人角色与角色类型（2.4 节）

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **ROLE_TYPE (角色类型)** | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 否 | ID | 所有角色类型（当事人角色、订单角色、案例角色等）的超类 |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 角色名称/描述（如雇员、客户、供应商、内部组织、公证人） |
| **PARTY_ROLE_TYPE (当事人角色类型)** | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 继承自 `ROLE_TYPE` |
| **PARTY_ROLE (当事人角色)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY` |
| | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 关联 `PARTY_ROLE_TYPE` |
| | `PARTY_ROLE_ID` | 当事人角色标识 | 否 | 否 | ID | 可选单列标识（注：图 2-4 中还包含可选属性 `FROM_DATE` 起始日期、`THRU_DATE` 终止日期，用于独立于关系的角色如“公证人”、“医生”） |
| **INTERNAL_ORGANIZATION (内部组织)** | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY_ROLE` |
| | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 关联 `PARTY_ROLE` |
| | `INTERNAL_ORGANIZATION_ID` | 内部组织标识 | 是 | 否 | ID | 建模企业自身的内部组织（总公司、分公司、内部部门） |
| **CUSTOMER (客户)** | `CUSTOMER_ID` | 客户标识 | 是 | 否 | ID | 客户专属角色标识 |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY_ROLE`（既可以是人也可以是组织） |
| | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 关联 `PARTY_ROLE` |
| **客户角色子类（均含 `CUSTOMER_ID` [PK, FK] + `PARTY_ID` [PK, FK] + `ROLE_TYPE_ID` [PK, FK]）** | `BILL_TO_CUSTOMER` (付款客户)、`SHIP_TO_CUSTOMER` (装运目标客户)、`END_USER_CUSTOMER` (最终用户客户) | 同 `CUSTOMER` 三元主键 | 是 | 是 | ID | 区分下单/付款/收货/最终使用四方客户角色 |
| **人员角色子类（均含 `PARTY_ID` [PK, FK] + `ROLE_TYPE_ID` [PK, FK]）** | `PERSON_ROLE` (人员角色)、`EMPLOYEE` (雇员)、`CONTRACTOR` (签约人)、`FAMILY_MEMBER` (家庭成员)、`CONTACT` (联络员)、`MANAGER` (管理者)、`WORKER` (工作者) | `PARTY_ID`, `ROLE_TYPE_ID` | 是 | 是 | ID | 图 2-4 人员专属角色子类 |
| **组织角色与组织单位子类（均含 `PARTY_ID` [PK, FK] + `ROLE_TYPE_ID` [PK, FK]）** | - `ORGANIZATION_ROLE` (组织角色)<br>- 分销渠道：`DISTRIBUTION_CHANNEL` (分销渠道)、`AGENT` (代理)、`DISTRIBUTOR` (分销人)<br>- 外部伙伴与机构：`SUPPLIER` (供应商)、`PARTNER` (合作伙伴)、`COMPETITOR` (竞争对手)、`REGULATORY_AGENCY` (管理机构)、`ASSOCIATION` (行业协会)、`HOUSEHOLD` (住户)、`UNION` (工会)、`CARRIER` (运送人)<br>- 组织单位：`ORGANIZATION_UNIT` (组织单位)、`PARENT_ORGANIZATION` (上级组织)、`SUBSIDIARY` (子公司/分公司)、`DIVISION` (分支机构)、`DEPARTMENT` (部门)、`OTHER_ORGANIZATION_UNIT` (其他组织单位)<br>- 通用角色：`PROSPECT` (潜在客户)、`SHAREHOLDER` (股东) | `PARTY_ID`, `ROLE_TYPE_ID` | 是 | 是 | ID | 图 2-4 组织与通用角色子类 |

---

### 模块 3：当事人关系、关系状态与优先级（2.5 节）

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **PARTY_RELATIONSHIP_TYPE (当事人关系类型)** | `PARTY_RELATIONSHIP_TYPE_ID` | 当事人关系类型标识 | 是 | 否 | ID | |
| | `ROLE_TYPE_ID_VALID_FROM` | 角色类型标识有效自 | 否 | 是 | ID | 约束合法的源 `PARTY_ROLE_TYPE` |
| | `ROLE_TYPE_ID_VALID_TO` | 角色类型标识有效至 | 否 | 是 | ID | 约束合法的目标 `PARTY_ROLE_TYPE` |
| | `NAME` | 名称 | 否 | 否 | Name | 如客户关系、雇用关系、组织隶属关系、师徒关系 |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 关系的详细业务定义 |
| **PARTY_RELATIONSHIP (当事人关系)** | `PARTY_ID_FROM` | 源当事人标识 | 是 | 是 | ID | 关联源 `PARTY_ROLE.PARTY_ID` |
| | `PARTY_ID_TO` | 目标当事人标识 | 是 | 是 | ID | 关联目标 `PARTY_ROLE.PARTY_ID` |
| | `ROLE_TYPE_ID_FROM` | 源角色类型标识 | 是 | 是 | ID | 关联源 `PARTY_ROLE.ROLE_TYPE_ID` |
| | `ROLE_TYPE_ID_TO` | 目标角色类型标识 | 是 | 是 | ID | 关联目标 `PARTY_ROLE.ROLE_TYPE_ID` |
| | `FROM_DATE` | 起始日期 | 是 | 否 | Datetime | 关系建立生效日期 |
| | `THRU_DATE` | 终止日期 | 否 | 否 | Datetime | 关系结束日期（为空表示当前有效） |
| | `STATUS_TYPE_ID` | 状态类型标识 | 否 | 是 | ID | 关联 `PARTY_RELATIONSHIP_STATUS_TYPE` |
| | `PRIORITY_TYPE_ID` | 优先权类型标识 | 否 | 是 | ID | 关联 `PRIORITY_TYPE` |
| | `PARTY_RELATIONSHIP_TYPE_ID` | 当事人关系类型标识 | 否 | 是 | ID | 关联 `PARTY_RELATIONSHIP_TYPE`（注：若同一角色对可存在多种关系，可将该列升为主键的一部分） |
| | `COMMENT` | 备注 | 否 | 否 | Comment | 针对该特定关系的评价或跟进备注 |
| **EMPLOYMENT (雇用关系)** | `PARTY_ID_FROM` | 源当事人标识 | 是 | 是 | ID | 雇员 `PARTY_ID` |
| | `PARTY_ID_TO` | 目标当事人标识 | 是 | 是 | ID | 内部组织（雇主）`PARTY_ID` |
| | `FROM_DATE` | 起始日期 | 是 | 是 | Datetime | 入职/雇用开始日期 |
| | `ROLE_TYPE_ID_TO` | 目标角色类型标识 | 是 | 是 | ID | 内部组织/雇主角色 |
| | `ROLE_TYPE_ID_FROM` | 源角色类型标识 | 是 | 是 | ID | 雇员角色 |
| | `TERMINATION_REASON_ID` | 终止原因标识 | 否 | 是 | ID | 关联 `TERMINATION_REASON` |
| | `TERMINATION_TYPE_ID` | 终止类型标识 | 否 | 是 | ID | 关联 `TERMINATION_TYPE` |
| **TERMINATION_REASON (终止原因)** | `TERMINATION_REASON_ID` [PK] (ID), `DESCRIPTION` (Description) | 离职/关系终止原因字典 | - | - | - | |
| **TERMINATION_TYPE (终止类型)** | `TERMINATION_TYPE_ID` [PK] (ID), `DESCRIPTION` (Description) | 离职/关系终止类型字典（主动辞职/解雇/退休等） | - | - | - | |
| **其他特定当事人关系子类（均共享 5 元复合主键 `PARTY_ID_FROM` + `PARTY_ID_TO` + `ROLE_TYPE_ID_FROM` + `ROLE_TYPE_ID_TO` + `FROM_DATE`）** | `CUSTOMER_RELATIONSHIP` (客户关系)、`SUPPLIER_RELATIONSHIP` (供应商关系)、`ORGANIZATION_ROLLUP` (组织隶属关系)、`ORGANIZATION_CONTACT_RELATIONSHIP` (组织联络员关系)、`DISTRIBUTION_CHANNEL_RELATIONSHIP` (分销渠道关系)、`PARTNERSHIP` (合作关系) | 5 元复合主键 | 是 | 是 | ID / Datetime | 图 2-5 与图 2-6a 特定当事人关系子类 |
| **PRIORITY_TYPE (优先权类型)** | `PRIORITY_TYPE_ID` | 优先权类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如很高、高、中等、低 |
| **STATUS_TYPE (状态类型)** | `STATUS_TYPE_ID` | 状态类型标识 | 是 | 否 | ID | 状态类型顶层超类 |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | |
| **PARTY_RELATIONSHIP_STATUS_TYPE (当事人关系状态类型)** | `STATUS_TYPE_ID` | 状态类型标识 | 是 | 是 | ID | 继承自 `STATUS_TYPE`（如活跃、不活跃、谋求更多参与） |

---

### 模块 4：当事人联系机制、邮政地址与地理范围（2.6 节）

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **CONTACT_MECHANISM_TYPE (联系机制类型)** | `CONTACT_MECHANISM_TYPE_ID` | 联系机制类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如电话、手机、传真、邮政地址、电子邮件、Web 地址 |
| **CONTACT_MECHANISM (联系机制)** | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 否 | ID | 所有联系方式的顶层超类 |
| | `CONTACT_MECHANISM_TYPE_ID` | 联系机制类型标识 | 否 | 是 | ID | 关联 `CONTACT_MECHANISM_TYPE` |
| **POSTAL_ADDRESS (邮政地址)** | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 继承自 `CONTACT_MECHANISM` |
| | `ADDRESS1` | 地址 1 | 否 | 否 | Long varchar | 街道门牌号等第一行地址 |
| | `ADDRESS2` | 地址 2 | 否 | 否 | Long varchar | 楼层房间号等第二行地址 |
| | `DIRECTIONS` | 方位 | 否 | 否 | Long varchar | 路线指引与方位说明（只存一次，多主体共享不冗余） |
| **TELECOMMUNICATIONS_NUMBER (电信号码)** | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 继承自 `CONTACT_MECHANISM` |
| | `COUNTRY_CODE` | 国家代码 | 否 | 否 | Numeric | 国际区号 |
| | `AREA_CODE` | 地区代码 | 否 | 否 | Numeric | 城市/地区区号 |
| | `CONTACT_NUMBER` | 联系号码 | 否 | 否 | Short varchar | 电话/传真/手机号码串 |
| **ELECTRONIC_ADDRESS (电子地址)** | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 继承自 `CONTACT_MECHANISM` |
| | `ELECTRONIC_ADDRESS_STRING` | 电子地址串 | 否 | 否 | Long varchar | 邮箱地址、Web 域名或即时通讯账号 |
| **CONTACT_MECHANISM_LINK (联系机制连接)** | `CONTACT_MECHANISM_ID_FROM` | 源联系机制标识 | 是 | 是 | ID | 如主办公电话 |
| | `CONTACT_MECHANISM_ID` | 目标联系机制标识 | 是 | 是 | ID | 如占线转接的手机/呼机，或传真转接的电子邮箱 |
| **PARTY_CONTACT_MECHANISM (当事人联系机制)** | `FROM_DATE` | 起始日期 | 是 | 否 | Datetime | 联系方式启用日期 |
| | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 关联 `CONTACT_MECHANISM` |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY` |
| | `ROLE_TYPE_ID` | 角色类型标识 | 否 | 是 | ID | 可选：限定仅在该当事人扮演特定角色（如客户）时使用 |
| | `THRU_DATE` | 终止日期 | 否 | 否 | Datetime | 联系方式停用日期 |
| | `NON-SOLICITATION_INDICATOR` | 免推销标志 | 否 | 否 | Indicator | 标记该号码/地址是否拒绝营销推销打扰 |
| | `EXTENSION` | 扩展 | 否 | 否 | Very short | 电话分机号 |
| | `COMMENT` | 备注 | 否 | 否 | Comment | 如“仅工作日 9:00-17:00 联系” |
| **PARTY_POSTAL_ADDRESS (当事人邮政地址 —— 图 2-8 独立地址模式)** | `FROM_DATE` [PK], `PARTY_ID` [PK, FK], `CONTACT_MECHANISM_ID` [PK, FK], `THRU_DATE`, `COMMENT` | 当邮政地址未并入 `CONTACT_MECHANISM` 时使用的关联表（若采用图 2-10 扩展模型则由 `PARTY_CONTACT_MECHANISM` 统一承担） | - | - | - | |
| **CONTACT_MECHANISM_PURPOSE_TYPE (联系机制目的类型)** | `CONTACT_MECHANISM_PURPOSE_TYPE_ID` | 联系机制目的类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如总部地址、账单查询地址、服务地址、销售办公室、常用办公电话、私人邮箱 |
| **PARTY_CONTACT_MECHANISM_PURPOSE (当事人联系机制目的)** | `FROM_DATE` | 起始日期 | 是 | 是 | Datetime | 关联 `PARTY_CONTACT_MECHANISM` |
| | `CONTACT_MECHANISM_PURPOSE_ID` | 联系机制目的标识 | 是 | 是 | ID | 关联 `CONTACT_MECHANISM_PURPOSE_TYPE` |
| | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 关联 `PARTY_CONTACT_MECHANISM` |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY_CONTACT_MECHANISM` |
| | `THRU_DATE` | 终止日期 | 否 | 否 | Datetime | 该用途失效日期 |
| **GEOGRAPHIC_BOUNDARY_TYPE (地理范围类型)** | `GEO_BOUNDARY_TYPE_ID` | 地理范围类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如国家、省、州、市、县、邮编、销售区域、服务区域 |
| **GEOGRAPHIC_BOUNDARY (地理范围)** | `GEO_ID` | 地理范围标识 | 是 | 是 | ID | |
| | `GEO_BOUNDARY_TYPE_ID` | 地理范围类型标识 | 否 | 是 | ID | 关联 `GEOGRAPHIC_BOUNDARY_TYPE` |
| | `NAME` | 名称 | 否 | 否 | Name | 如纽约、波特兰、华东销售大区 |
| | `GEO_CODE` | 地理范围代码 | 否 | 否 | Short varchar | 行政区划码 / 邮政编码值 |
| | `ABBREVIATION` | 缩写 | 否 | 否 | Short varchar | 简称/缩写 |
| **地理范围子类（主键均为 `GEO_ID` [PK, FK]，其中 `POSTAL_CODE` 列名为 `ID` [PK, FK]）** | `COUNTRY` (国家)、`STATE` (州)、`PROVINCE` (省)、`COUNTY` (县)、`COUNTY_CITY` (县城)、`CITY` (城市)、`POSTAL_CODE` (邮政编码)、`REGION` (地区)、`TERRITORY` (区域)、`SALES_TERRITORY` (销售区域)、`SERVICE_TERRITORY` (服务区域) | `GEO_ID` | 是 | 是 | ID | 图 2-8 地理范围子类型 |
| **GEOGRAPHIC_BOUNDARY_ASSOCIATION (地理范围联系)** | `GEO_ID` (父地理范围标识, [PK, FK], ID), `GEO_ID` (子地理范围标识, [PK, FK], ID) | 递归多对多关联（如省包含市，销售区域包含多个省/市） | 是 | 是 | ID | |
| **POSTAL_ADDRESS_BOUNDARY (邮政地址范围)** | `GEO_ID` | 地理范围标识 | 是 | 是 | ID | 关联 `GEOGRAPHIC_BOUNDARY` |
| | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 关联 `POSTAL_ADDRESS` |

---

### 模块 5：物理设施与联系机制（2.7 节）

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **FACILITY_TYPE (设施类型)** | `FACILITY_TYPE_ID` | 设施类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如建筑物、楼层、房间、办公室、仓库、车间厂房 |
| **FACILITY (设施)** | `FACILITY_ID` | 设施标识 | 是 | 否 | ID | 物理空间实体（可自关联表示大楼→楼层→房间层级） |
| | `FACILITY_TYPE_ID` | 设施类型标识 | 否 | 是 | ID | 关联 `FACILITY_TYPE` |
| | `FACILITY_NAME` | 设施名称 | 否 | 否 | Name | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | |
| | `SQUARE_FOOTAGE` | 面积 | 否 | 否 | Numeric | 平方面积 |
| **物理设施子类（主键均为 `FACILITY_ID` [PK, FK]）** | `BUILDING` (建筑物)、`FLOOR` (楼层)、`ROOM` (房间)、`OFFICE` (办公室)、`WAREHOUSE` (仓库)、`PLANT` (厂房) | `FACILITY_ID` | 是 | 是 | ID | 图 2-11 设施子类 |
| **FACILITY_ROLE_TYPE (设施角色类型)** | `FACILITY_ROLE_TYPE_ID` | 设施角色类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如拥有者、租用者、出租者、使用者、管理员 |
| **PARTY_FACILITY (当事人设施 / 设施角色)** | `FACILITY_ID` | 设施标识 | 是 | 是 | ID | 关联 `FACILITY` |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY` |
| | `FACILITY_ROLE_TYPE_ID` | 设施角色类型标识 | 否 | 是 | ID | 关联 `FACILITY_ROLE_TYPE` |
| **FACILITY_CONTACT_MECHANISM (设施联系机制)** | `FACILITY_ID` | 设施标识 | 是 | 是 | ID | 关联 `FACILITY` |
| | `CONTACT_MECHANISM_ID` | 联系机制标识 | 是 | 是 | ID | 关联 `CONTACT_MECHANISM`（如工厂电话、仓库收货地址） |

---

### 模块 6：当事人通信事件、案例与后续工作计划追踪（2.8 节）

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **COMMUNICATION_EVENT (通信事件)** | `COMMUNICATION_EVENT_ID` | 通信事件标识 | 是 | 否 | ID | |
| | `STATUS_TYPE_ID` | 状态类型标识 | 否 | 是 | ID | 关联 `COMMUNICATION_EVENT_STATUS_TYPE` |
| | `CASE_ID` | 案例标识 | 否 | 是 | ID | 关联 `CASE`（将同一问题的多次通信归集到同一案例） |
| | `CONTACT_MECHANISM_TYPE_ID` | 联系机制类型标识 | 否 | 是 | ID | 关联 `CONTACT_MECHANISM_TYPE` |
| | `PARTY_ID_FROM` | 源当事人标识 | 否 | 是 | ID | 关联所属 `PARTY_RELATIONSHIP` |
| | `PARTY_ID_TO` | 目标当事人标识 | 否 | 是 | ID | 关联所属 `PARTY_RELATIONSHIP` |
| | `ROLE_TYPE_ID_FROM` | 源角色类型标识 | 否 | 是 | ID | 关联所属 `PARTY_RELATIONSHIP` |
| | `ROLE_TYPE_ID_TO` | 目标角色类型标识 | 否 | 是 | ID | 关联所属 `PARTY_RELATIONSHIP` |
| | `FROM_DATE` | 起始日期 | 否 | 是 | Datetime | 关联所属 `PARTY_RELATIONSHIP.FROM_DATE` |
| | `DATETIME_STARTED` | 开始时间 | 否 | 否 | Datetime | 本次通信开始时间戳 |
| | `DATETIME_ENDED` | 结束时间 | 否 | 否 | Datetime | 本次通信结束时间戳 |
| | `NOTE` | 注释 | 否 | 否 | Comment | 沟通内容摘要与纪要 |
| **通信事件子类（主键均为 `COMMUNICATION_EVENT_ID` [PK, FK]）** | `PHONE_COMMUNICATION` (电话通信)、`EMAIL_COMMUNICATION` (电子邮件通信)、`FAX_COMMUNICATION` (传真通信)、`FACE_TO_FACE_COMMUNICATION` (面对面交流)、`LETTER_CORRESPONDENCE` (信件通信)、`WEB_SITE_COMMUNICATION` (网站通信) | `COMMUNICATION_EVENT_ID` | 是 | 是 | ID | 图 2-12 通信事件方式子类 |
| **COMMUNICATION_EVENT_STATUS_TYPE (通信事件状态类型)** | `STATUS_TYPE_ID` | 状态类型标识 | 是 | 是 | ID | 继承自 `STATUS_TYPE`（如已安排、正在进行、已完成、等待解决） |
| **COMMUNICATION_EVENT_PURPOSE_TYPE (通信事件目的类型)** | `COMMUNICATION_EVENT_PRP_TYP_ID` | 通信事件目的类型标识 | 是 | 否 | ID | |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | |
| **COMMUNICATION_EVENT_PURPOSE (通信事件目的)** | `COMMUNICATION_EVENT_PRP_TYP_ID` | 通信事件目的类型标识 | 是 | 是 | ID | 关联 `COMMUNICATION_EVENT_PURPOSE_TYPE` |
| | `COMMUNICATION_EVENT_ID` | 通信事件标识 | 是 | 是 | ID | 关联 `COMMUNICATION_EVENT` |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 针对本次通信该目的的具体说明 |
| **通信事件目的子类（共享复合主键 `COMMUNICATION_EVENT_PRP_TYP_ID` [PK, FK] + `COMMUNICATION_EVENT_ID` [PK, FK]）** | `SUPPORT_CALL` (支持呼叫)、`CUSTOMER_SERVICE_CALL` (客户服务呼叫)、`SALES_FOLLOW_UP` (售后跟踪调查)、`INQUIRY` (问询)、`MEETING` (会议/会见)、`CONFERENCE` (会议)、`SEMINAR` (研讨会)、`ACTIVITY_REQUEST` (活动邀请) | 双元复合主键 | 是 | 是 | ID | 图 2-12 通信事件目的子类 |
| **COMMUNICATION_EVENT_ROLE_TYPE (通信事件角色类型)** | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 继承自 `ROLE_TYPE`（呼叫者、接听者、协办人、参与者、记录员） |
| **VALID_CONTACT_MECHANISM_ROLE (有效通信机制角色)** | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 关联 `COMMUNICATION_EVENT_ROLE_TYPE` |
| | `CONTACT_MECHANISM_TYPE_ID` | 联系机制类型标识 | 是 | 是 | ID | 关联 `CONTACT_MECHANISM_TYPE`（约束某通信方式下允许的角色） |
| **COMMUNICATION_EVENT_ROLE (通信事件角色)** | `COMMUNICATION_EVENT_ID` | 通信事件标识 | 是 | 是 | ID | 关联 `COMMUNICATION_EVENT` |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY` |
| | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 关联 `COMMUNICATION_EVENT_ROLE_TYPE` |
| **CASE (案例/事例)** | `CASE_ID` | 案例标识 | 是 | 否 | ID | 归集围绕同一问题/事件的一系列通信 |
| | `STATUS_TYPE_ID` | 状态类型标识 | 否 | 是 | ID | 关联 `CASE_STATUS_TYPE` |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如“客户技术支持——软件持续崩溃” |
| | `START_DATETIME` | 开始时间 | 否 | 否 | Datetime | 案例创建时间 |
| **CASE_STATUS_TYPE (案例状态类型)** | `STATUS_TYPE_ID` | 状态类型标识 | 是 | 是 | ID | 继承自 `STATUS_TYPE` |
| **CASE_ROLE_TYPE (案例角色类型)** | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 继承自 `ROLE_TYPE`（如技术方案组长、客户、质量保证经理） |
| **CASE_ROLE (案例角色)** | `CASE_ID` | 案例标识 | 是 | 是 | ID | 关联 `CASE` |
| | `PARTY_ID` | 当事人标识 | 是 | 是 | ID | 关联 `PARTY` |
| | `ROLE_TYPE_ID` | 角色类型标识 | 是 | 是 | ID | 关联 `CASE_ROLE_TYPE` |
| **COMMUNICATION_EVENT_WORK_EFFORT (通信事件工作计划)** | `WORK_EFFORT_ID` | 工作计划标识 | 是 | 是 | ID | 关联后续行动 `WORK_EFFORT` |
| | `COMMUNICATION_EVENT_ID` | 通信事件标识 | 是 | 是 | ID | 关联 `COMMUNICATION_EVENT` |
| | `DESCRIPTION` | 描述 | 否 | 否 | Description | 如“需要给用户发送一个软件补丁” |
| **WORK_EFFORT (工作计划 —— 图 2-13 追踪接口实体)** | `WORK_EFFORT_ID` [PK] (ID), `NAME` (Name), `DESCRIPTION` (Description), `SCHEDULED_START_DATE` (Datetime), `SCHEDULED_COMPLETION_DATE` (Datetime), `TOTAL_DOLLARS_ALLOWED` (Currency amount), `TOTAL_HOURS_ALLOWED` (Numeric), `ESTIMATED_HOURS` (Numeric) | 作为通信事件后续处理行动的接口实体（子类：`PROGRAM` 计划、`PROJECT` 项目、`PHASE` 阶段、`TASK` 任务、`ACTIVITY` 活动） | - | - | - | |

---

### 模块 7：附录 A 人力与资质可选扩展模块（职位体系、资质证书、技能与雇佣薪酬）

当业务场景需要深挖内部组织定岗定编、职位汇报线、员工/专家资质证书与技能标签时，按需选用以下附录 A 实体：

| 实体名称 | 属性名称 | 属性译名 | 主键? | 外键? | 定义域 | 建模说明 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **POSITION_TYPE (职位类型)** | `POSITION_TYPE_ID` [PK] (ID), `PARTY_ID` [FK] (ID), `ROLE_TYPE_ID` [FK] (ID), `DESCRIPTION` (Description) | 定义标准岗位类型（如客户服务代表、高级工程师） | - | - | - | |
| **POSITION (职位)** | `POSITION_ID` [PK] (ID), `STATUS_TYPE_ID` [FK], `PARTY_ID` [FK] (所属内部组织), `POSITION_TYPE_ID` [FK], `BUDGET_ID` [FK], `BUDGET_ITEM_SEQ_ID` [FK], `BUDGET_TYPE_ID` [FK], `ESTIMATED_FROM_DATE`, `ESTIMATED_THRU_DATE`, `ACTUAL_FROM_DATE`, `ACTUAL_THRU_DATE`, `SALARY_FLAG` (Indicator), `EXEMPT_FLAG` (Indicator), `FULLTIME_FLAG` (Indicator), `TEMPORARY_FLAG` (Indicator) | 组织内的具体岗位编制实例（独立于具体任职人员） | - | - | - | |
| **POSITION_FULFILLMENT (职位履行)** | `FROM_DATE` [PK] (Datetime), `PARTY_ID` [PK, FK] (任职人员), `POSITION_ID` [PK, FK] (职位), `THRU_DATE` (Datetime), `COMMENT` (Comment) | 人岗匹配历史（谁在什么时间担任什么职位） | - | - | - | |
| **POSITION_REPORTING_STRUCTURE (职位报告结构)** | `POSITION_ID_REPORTING_TO` [PK, FK] (上级职位), `POSITION_ID_MANAGED_BY` [PK, FK] (下级职位), `FROM_DATE` [PK] (Datetime), `THRU_DATE` (Datetime), `PRIMARY_FLAG` (首要汇报标志, Indicator), `COMMENT` (Comment) | 职位间的汇报树（支持实线/虚线双汇报及历史变更） | - | - | - | |
| **RESPONSIBILITY_TYPE / POSITION_RESPONSIBILITY / VALID_RESPONSIBILITY** | `RESPONSIBILITY_TYPE` (`RESPONSIBILITY_TYPE_ID` [PK], `DESCRIPTION`)；`POSITION_RESPONSIBILITY` (`FROM_DATE` [PK], `POSITION_ID` [PK, FK], `RESPONSIBILITY_TYPE_ID` [PK, FK], `THRU_DATE`, `COMMENT`)；`VALID_RESPONSIBILITY` (`FROM_DATE` [PK], `POSITION_TYPE_ID` [PK, FK], `RESPONSIBILITY_TYPE_ID` [PK, FK], `THRU_DATE`, `COMMENT`) | 职位职责定义与分配 | - | - | - | |
| **QUALIFICATION_TYPE & PARTY_QUALIFICATION (资格类型与当事人资格)** | `QUALIFICATION_TYPE` (`QUAL_TYPE_ID` [PK], `DESCRIPTION`)；`PARTY_QUALIFICATION` (`QUAL_TYPE_ID` [PK, FK], `PARTY_ID` [PK, FK], `FROM_DATE`, `THRU_DATE`)；子类：`DEGREE` (学位)、`CERTIFICATION` (证书) | 人员或组织的资质认证与学历学位 | - | - | - | |
| **SKILL_TYPE & PARTY_SKILL (技能类型与当事人技能)** | `SKILL_TYPE` (`SKILL_TYPE_ID` [PK], `DESCRIPTION`)；`PARTY_SKILL` (`PARTY_ID` [PK, FK], `SKILL_TYPE_ID` [PK, FK], `YEARS_EXPERIENCE` 工作经验年限, `RATING` 等级, `SKILL_LEVEL` 技能水平, `STARTED_USING_DATE` 开始使用日期) | 当事人技能标签与熟练度评估 | - | - | - | |
| **TRAINING_CLASS_TYPE & PERSON_TRAINING & RESUME** | `TRAINING_CLASS_TYPE` (`TRAINING_CLASS_TYPE_ID` [PK], `DESCRIPTION`)；`PERSON_TRAINING` (`TRAINING_CLASS_TYPE_ID` [PK, FK], `PARTY_ID` [PK, FK], `FROM_DATE`, `THRU_DATE`)；`RESUME` (`PARTY_ID` [PK, FK], `RESUME_ID` [PK], `RESUME_DATE`, `RESUME_TEXT`) | 培训记录与简历存储 | - | - | - | |
| **PAY_GRADE / SALARY_STEP / PAY_HISTORY / PARTY_BENEFIT** | `PAY_GRADE` (`PAY_GRADE_ID` [PK], `NAME`, `COMMENT`)；`SALARY_STEP` (`SALARY_STEP_SEQ_ID` [PK], `PAY_GRADE_ID` [PK, FK], `AMOUNT`, `DATE_MODIFIED`)；`PAY_HISTORY` (继承 `EMPLOYMENT` 5 元主键, 含 `PAY_GRADE_ID`, `SALARY_STEP_SEQ_ID`, `PERIOD_TYPE_ID`, `THRU_DATE`, `AMOUNT`, `COMMENT`)；`PARTY_BENEFIT` (继承 `EMPLOYMENT` 5 元主键 + `BENEFIT_TYPE_ID` [PK, FK]) | 基于雇用关系的薪资演进与福利历史 | - | - | - | |

---

### 模块 8：外部业务单据消费“人/组织”模型的标准接入契约（参照 2.4.3 / 2.4.5 节）

当外部业务域（如订单、协议、发票、账单、工作计划）需要接入本“人/组织”模型时，**严禁在外部单据上硬编码多个人员/组织字段或复制姓名电话**，统一提供以下两类标准接入契约：

1. **契约模式 A：多方事务角色桥接表（`<TRANSACTION>_ROLE`，推荐标准）**
   - 适用于一张业务单据涉及多个不同角色的当事人（例如：一张订单同时有下单客户、付款客户、收货客户、录入员、销售代表；一份合同有甲方、乙方、公证方）。
   - 标准结构（对齐附录 A）：
     - `<TRANSACTION>_ROLE_TYPE`：继承自 `ROLE_TYPE`（`ROLE_TYPE_ID` [PK, FK]）。
     - `<TRANSACTION>_ROLE`：复合主键 `<TRANSACTION>_ID` [PK, FK] + `PARTY_ID` [PK, FK] + `ROLE_TYPE_ID` [PK, FK]（可选附加 `FROM_DATE`, `THRU_DATE` 或 `PERCENTAGE` 分成比例，如 `INVOICE_ROLE`）。
   - 附录 A 原生实例：`ORDER_ROLE`、`AGREEMENT_ROLE`、`INVOICE_ROLE`、`BILLING_ACCOUNT_ROLE`、`FINANCIAL_ACCOUNT_ROLE`、`BUDGET_ROLE`、`REQUEST_ROLE`、`QUOTE_ROLE`、`REQUIREMENT_ROLE`、`WORK_EFFORT_PARTY_ASSIGNMENT`。
2. **契约模式 B：单据直接挂载当事人关系或联系机制（Relationship / Contact Mechanism 绑定）**
   - 当单据发生在特定当事人关系上下文中（如 `AGREEMENT` 协议），直接外键引用 `PARTY_RELATIONSHIP` 的复合键（`PARTY_ID_FROM`, `PARTY_ID_TO`, `ROLE_TYPE_ID_FROM`, `ROLE_TYPE_ID_TO`, `FROM_DATE`）。
   - 当单据需要指定收货地址、账单地址或联系电话（如 `ORDER_CONTACT_MECHANISM`、`INVOICE`、`SHIPMENT`），直接外键关联 `CONTACT_MECHANISM_ID`（及 `CONTACT_MECHANISM_PURPOSE_TYPE_ID`），而绝不在单据表内冗余拷贝地址文本字符串（除非作不可变历史快照归档）。
