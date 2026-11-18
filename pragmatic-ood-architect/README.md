# Pragmatic OOD Architect v2

独立的 Agent Skill。与原版并排放置即可；不需要覆盖安装、迁移旧蓝图或修改项目配置。入口是 [SKILL.md](./SKILL.md)。

## 临时试用（Pi）

在**要讨论的项目**里启动会话，以绝对路径显式加载本目录。例如：

```sh
pi --no-skills --skill "$HOME/0_work/pragmatic-ood-architect-v2"
```

输入 `/skill:pragmatic-ood-architect-v2 帮我看这个类关系，只讨论，不写文件。`。这只影响本次启动。`--no-skills` 用于对比试用时排除其他自动发现的 Skill，平常可省略。

## 三个行为验收场景

在独立对话里做下列检查；这些是人工/模型回放用例，不是 Python 单测。实际回答不用和示范逐字一致。

| 输入 / 操作 | 应观察到 | 失败信号 |
|---|---|---|
| 给出一个旧方法及一个实际失败场景，要求“轻量重构” | 先复原调用与失败条件，再选择要重切的概念或关系。见[库存例](./examples/04-refactor-spring-monolith.md) | 直接输出新架构，或者让用户先完成全系统需求问卷 |
| “`VipUser` 要不要继承 `NormalUser`？”先不提供身份生命周期 | 中性询问身份是否变化；得到事实再比较结构。见[会员例](./examples/02-litmus-vipuser-java.md) | 给“会升降级”标推荐，或把暂时采用的假设写成已确认事实 |
| 在临时项目同意一个空蓝图路径，中途确认一个取舍、留下一个问题，结束会话并重开 | 蓝图里已存在决定；恢复后直接继续那个未决问题，历史编号不变。见[恢复例](./examples/05-resume.md) | 模板自带假记录、编号被复用、重新做 T 或把旧版蓝图覆盖 |

## 离线检查

在本目录运行。文档检查只需要 Python 3.9+；行为样例另需 JDK 17+、Node 和 TypeScript 4.9+ 的 `tsc`。不会联网安装依赖，临时编译产物自动删除。

```sh
python3 -B scripts/check_citations.py
python3 -B -m unittest discover -s tests -v
python3 -B tests/run_examples.py
# 若 tsc 不在 PATH，可用：TSC=/absolute/path/to/tsc python3 -B tests/run_examples.py
```

校验器检查节号存在、包内链接、标题/显式锚点、文件与读取路径的预算；不证明引用语义。A3 报告的是“活动卡 + 一张试金石 + 一个原语或一棵权衡树”的字节上界，不是模型 token 消耗。两份[可执行 Java](./examples/code/LockedSetHandle.java) / [TS](./examples/code/exportable.ts) 代码直接参与编译与行为测试；语言手册中的框架配置和设计草图需在目标项目单独验证。
