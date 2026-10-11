# Requirements Document

## Introduction

将 `astrbot_plugin_w1ndys_rules` 拆成三个独立插件：

| 简称 | 插件名 | 功能 |
|---|---|---|
| rules | `astrbot_plugin_group_manager` | 违禁监控、黑白名单、邀请记录、调试工具 |
| welcome | `astrbot_plugin_group_welcome` | 入群验证、欢迎语、欢迎语管理命令 |
| keyword | `astrbot_plugin_keyword_reply` | 关键词回复 |

原插件由 `astrbot_plugin_w1ndys_rules` 改名为 `astrbot_plugin_group_manager`，原仓库相应更名，另外两个插件新建独立仓库。文档内 `rules` 仅为群管插件的历史简称，不是最终插件名。三个插件各自拥有数据库、配置和 React 控制台，无运行时跨插件导入。五个视觉依赖只属于群管插件。

回归基线更新为 PR #24 与 PR #25 合并后的 `main`（`152076911cb845385218181daf0029053c8467eb`）：70 个测试文件、564 个用例。本轮在 PR #25 提交运行完整单测和ruff均通过，并核对合并提交的business/tests与受测版本无差异。除下面明确批准的拆分变化外，保留这份热修后的业务文案、日志级别、权限、验证状态和处置行为。

1. 配置和页面按三个插件分片。
2. 群名按插件独立，嵌入各自名单表格；拉取只改草稿，配置和群名用一个保存按钮、一个事务提交。
3. **只有违禁监控展开合并转发；关键词回复、欢迎语命令及私聊交码只识别直接文本。**
4. 通知业务处理后再停止事件，保证两个插件都有机会完成业务。
5. 迁移先读源库导入新库，另一个显式清理步骤先备份、再删旧库五个已搬走配置键。

## Glossary

- **直接文本**：本条消息最外层直接发送的文字。引用原文、合并转发节点、卡片字段、OCR 和宿主生成的消息概要不属于直接文本。
- **审核文本**：rules 现有 `resolve_audit_text` 产生的文本，含按当前规则展开的合并转发；图片、视频检测仍走现有独立路径。
- **通知业务**：入群邀请记录、验证创建、退群清理、管理员解禁通过与违禁禁言赦免。
- **通知收尾**：所有本插件集合的通知业务处理器运行后，终止该通知继续传播和进入默认模型。
- **名单并集**：rules 为 `forbidden_groups`、`invite_groups`、`forbidden_block_group_card_groups`；welcome 为 `welcome_groups`、`verify_groups`；keyword 为 `keyword_groups`。
- **群名草稿**：拉取结果与页面名单对应的未保存群名，关闭页面前未保存的数据不进入数据库。
- **迁移冲突**：源库与目标库有相同主键但字段值不同。相同主键且值相同是已迁移，不是冲突。
- **回归等价**：批准的变化之外，保留旧业务断言；不把旧文件数和用例数作为拆分后必须完全相同的指标。

## 已确认决策

- 保留独立 `group_name` 表，但每个插件只访问自己的库，不提供独立群名册页面。
- 一次拉取调用一次 OneBot `get_group_list`，只接纳本插件**当前页面名单草稿**并集内的群。
- 一个保存按钮同时提交名单、其他配置和群名；后端以这次请求中的完整配置为范围依据。
- 新安装空库可按 schema 初始化；已有数据迁移必须在新插件首次启动前完成，避免默认配置与迁移配置冲突。
- 迁移同值跳过、异值中止，既不覆盖目标值，也不把冲突算成功。
- 迁移与清理均由管理员显式运行，插件启动不执行迁移或删旧配置。
- 新版库文件名为 `group_manager.db`、`group_welcome.db`、`keyword_reply.db`；`rules.db` 仅是旧版迁移来源，不再作为新版群管默认库。工具位于群管仓库的 `scripts/migrate_split.py`。
- 插件名、目录名、metadata.name、PLUGIN_NAME、页面路由和新仓库名统一使用上表无个人前缀的名称；GitHub owner、作者署名和本机用户名仍为 w1ndys，不作全局字符串删除。
- 群管改名及数据库改名一并迁移：先对旧 `rules.db` 完成拆分、校验、备份清理，再显式生成并校验新数据目录中的 `group_manager.db`，保留旧库与清理前备份。新旧插件不能同时启用，不能把文件重命名或GitHub重定向当作完整迁移。

## Requirements

### Requirement 1：功能归属唯一

**User Story:** 作为维护者，我要每个插件可独立安装和维护。

#### Acceptance Criteria

1. 插件集合 SHALL 包含 rules、welcome、keyword 三个插件。
2. 每个业务模块和原有测试覆盖 SHALL 有明确归属，共享副本以设计映射为准。
3. 每个插件 SHALL 自持配置、数据库、页面和基础设施副本。
4. 每个插件 SHALL 通过本包、标准库及宿主接口完成运行，兄弟插件缺席时仍能加载。

5. WHEN 原插件更名，群管插件 SHALL 使用 `astrbot_plugin_group_manager` 作为加载标识和页面命名空间，并读取迁移生成的 `group_manager.db`；迁出两插件 SHALL 分别使用 `astrbot_plugin_group_welcome` 与 `astrbot_plugin_keyword_reply`。
### Requirement 2：关键词插件独立运行

**User Story:** 作为群管理员，我要关键词只匹配群员直接发出的文字。

#### Acceptance Criteria

1. WHEN keyword 单独安装，keyword SHALL 在未安装五个视觉依赖的宿主环境中加载。
2. keyword 的 `requirements.txt` SHALL 保持无额外第三方包。
3. WHEN 本群已开启且直接文本完全等于关键词，keyword SHALL 回复预设内容并终止后续事件处理。
4. WHEN 直接文本未命中，keyword SHALL 静默放行该事件。
5. WHEN 本群未开启，keyword SHALL 静默放行该事件。
6. WHEN welcome 已处理一条直接文本管理命令并终止事件，keyword SHALL 由宿主停止派发而跳过；keyword 自身 SHALL 保持无欢迎语前缀黑名单，welcome 缺席时按普通关键词匹配。
7. WHEN 写入关键词以宿主唤醒前缀开头，keyword SHALL 沿用现有校验与提示文案。
8. keyword SHALL 提供关键词页，保留业务字段及 API 后缀，接口前缀改为自己的插件名。

### Requirement 3：入群流程插件独立运行

**User Story:** 作为群管理员，我要验证与欢迎语独立于违禁监控运行。

#### Acceptance Criteria

1. WHEN welcome 单独安装，welcome SHALL 在 rules、keyword 和五个视觉依赖缺席时加载。
2. WHEN 本群开启验证且合法新成员入群，welcome SHALL 沿用现有验证码生成、禁言 2592000 秒和群内提示流程。
3. WHEN pending 成员私聊直接文本包含正确验证码，welcome SHALL 撤回提示、解禁，并按现有逻辑私聊回复通过或本群欢迎语。
4. WHILE 成员仍 pending，welcome SHALL 按现有 120 分钟间隔和北京时间 `[08:00,22:00)` 的窗口提醒。
5. WHEN 成员已提醒 4 次且白天再次到期，welcome SHALL 按现有逻辑踢出。
6. WHEN 验证通过且欢迎语可用，welcome SHALL 按通过路径发送欢迎语：私聊交码与工具通过发私聊，管理员解禁通过发群内。
7. WHEN 本群独立欢迎语为空串，welcome SHALL 保持关闭欢迎语。
8. WHEN 本群不在欢迎语开启名单，welcome SHALL 保持关闭欢迎语。
9. WHEN 开启欢迎语且本群无覆盖文案、全局文案为空，welcome SHALL 使用「欢迎入群~」。
10. WHEN 直接文本满足原 `parse_admin_command` 的精确命令边界，welcome SHALL 按原权限与文案处理。
11. WHEN 入群通知同时需要记录邀请边和创建验证，rules SHALL 先记录邀请边，welcome SHALL 随后处理验证。
12. welcome 的 `requirements.txt` SHALL 保持无额外第三方包。
13. WHEN 新成员入群，welcome SHALL 保持“入群不直接发欢迎语”的现状，欢迎语仅在通过路径发送。

### Requirement 4：rules 保留能力

**User Story:** 作为原插件用户，我要保留审核、名单、邀请和调试能力。

#### Acceptance Criteria

1. WHEN 命中违禁判定，rules SHALL 保留既有处置函数及其实际副作用顺序，不根据概述文字重新排列发送、撤回、日志和通知步骤。
2. WHEN 成员满足现有白名单跳过条件且未被黑名单覆盖，rules SHALL 跳过审核。
3. WHEN 本群通过既有 `forbidden_block_group_card_groups` 开启联系人卡片拦截且命中群名片或推荐好友，rules SHALL 保留直接处置、跳过模型的路径，原因码继续使用 `group_card`。
4. WHEN 本群启用邀请记录且入群数据满足记录条件，rules SHALL 记录邀请边。
5. WHEN 他人管理员解禁成员且有违禁禁言标记，rules SHALL 保留现有赦免、名单与回复处理。
6. WHEN rules 单独安装，rules SHALL 提供审核、邀请、名单和调试能力，并把关键词与验证留给对应插件。
7. rules SHALL 保留 qreader、opencv-contrib-python、zxing-cpp、rapidocr、onnxruntime 依赖。
8. rules SHALL 保留违禁日志页名单按钮，群名从本插件映射读取，日志表结构保持不变。
9. rules SHALL 独占合并转发展开和审核文本消费，其他插件 SHALL 使用 Requirement 11 的直接文本。

### Requirement 5：配置归属与旧配置清理

**User Story:** 作为维护者，我要每个配置键只有一个有效写入方。

#### Acceptance Criteria

1. keyword SHALL 读写 `keyword_groups`。
2. welcome SHALL 读写 `welcome_groups`、`verify_groups`、`welcome_text`、`verify_mute_seconds`。
3. rules SHALL 读写其余 13 键：`forbidden_groups`、`invite_groups`、`forbidden_block_group_card_groups`、`forbidden_guideline`、`forbidden_samples`、`forbidden_remind_text`、`forbidden_feishu_webhook`、`forbidden_mute_seconds` 和五个 `forbidden_trigger_*` 键。
4. WHEN rules 加载旧库，rules SHALL 只把自己的 13 键加载为有效配置，保留尚未显式清理的旧行。
5. 三个 `_conf_schema.json` SHALL 分别声明 13/4/1 键，保留原字段类型与默认值。
6. 迁出的配置 SHALL 保留键名及字符串列表等原编码格式。
7. WHEN 迁移已完成且管理员执行显式清理，清理工具 SHALL 先完成可恢复备份，再在事务中仅删除已搬走的五个配置键。
8. IF 备份失败或五键尚未在对应目标库核对一致，清理工具 SHALL 退出并保持源库不变。
9. WHEN 清理成功且源库原本只有这 18 键，源库 `plugin_setting` SHALL 剩 13 行；其他未知行、业务表和历史群名 SHALL 原样保留。

### Requirement 6：离线迁移

**User Story:** 作为已装用户，我要迁移完整数据且能识别失败和冲突。

#### Acceptance Criteria

1. 三个插件 SHALL 使用各自独立的 SQLite 文件。
2. WHEN 新安装空库首次启动，插件 SHALL 建表并初始化自身默认值；WHEN 迁移已写入配置，插件 SHALL 使用迁移值。
3. 工具 SHALL 接受 `--source`、`--welcome-db`、`--keyword-db` 三个数据库文件路径，迁移以显式 `migrate` 子命令运行。
4. 迁移工具 SHALL 复制 `keyword_reply` 全部业务字段到 keyword 库。
5. 迁移工具 SHALL 复制 `verify_pending`、`welcome_text` 全部字段到 welcome 库，验证码、时间、计数和提示 ID 原样保留。
6. 迁移工具 SHALL 将 `keyword_groups` 复制到 keyword 的配置表。
7. 迁移工具 SHALL 将 welcome 的四键复制到 welcome 的配置表。
8. 迁移工具 SHALL 按源库 welcome 名单并集复制群名到 welcome 库。
9. 迁移工具 SHALL 按源库 keyword 名单复制群名到 keyword 库。
10. `migrate` SHALL 只读源库并保持所有源表、行不变；源库写入仅允许 Requirement 5 的显式 `cleanup` 步骤。
11. IF 同主键同值，迁移工具 SHALL 计为已存在；IF 同主键异值，工具 SHALL 在写入前中止本次迁移并报告冲突位置而非敏感字段值。
12. 迁移工具 SHALL 报告各目标各表写入数、已存在数、冲突数和最终成功/失败状态。
13. IF 源库不存在、必需结构不完整、目标父目录不可写或源/目标路径重合，工具 SHALL 非零退出；WHEN 目标不存在且父目录有效，工具 SHALL 创建目标库和必需表。
14. WHEN 相同源数据重复迁移，工具 SHALL 保持目标值不变并报告零新增；重复运行清理 SHALL 对已删除键报告零删除。
15. 管理员执行迁移与清理时 SHALL 停止三个插件的数据写入，拆分、验证、清理和新版群管库生成校验全部完成后才启用新插件组合。
16. WHEN 管理员执行显式 `finalize-manager --source <rules.db> --manager-db <group_manager.db>`，工具 SHALL 在确认源库五个迁出配置键已清理后，用SQLite backup API生成新版群管库并校验完整性与逻辑数据一致；源库保持不变。
17. IF 新版目标已存在，工具 SHALL 对逻辑数据一致的目标报告已完成，对不同目标中止且保留双方数据；新版库生成失败 SHALL 保留旧库和备份，禁止把未校验目标作为可启动的新库。

### Requirement 7：消息与通知派发

**User Story:** 作为管理员，我要同一条消息的互斥以及通知双侧业务都能正确执行。

#### Acceptance Criteria

1. 联系人卡片拦截（含群名片、推荐好友） SHALL 先于欢迎语管理命令。
2. 欢迎语管理命令 SHALL 先于违禁文本判定。
3. 违禁文本判定 SHALL 先于关键词匹配。
4. WHEN 普通消息被某处理器处理并终止，宿主 SHALL 跳过后续处理器。
5. WHEN 管理员解禁通知同时涉及两插件，welcome 的通过处理 SHALL 先于 rules 的违禁赦免处理。
6. 处理器 SHALL 使用显式 priority 保证相关业务先后，不依赖加载顺序。
7. WHEN 收到已识别的成员通知，普通文本/卡片处理器 SHALL 直接让过，通知业务处理器 SHALL 完成本地业务并让过到收尾阶段。
8. rules 和 welcome SHALL 各带低优先级通知收尾处理器；WHEN 收尾识别入群、退群或他人管理员解禁通知，收尾 SHALL 停止事件且不发送额外消息。
9. WHEN 仅安装 rules 或 welcome，已安装插件的收尾 SHALL 独立生效；关键词插件 SHALL 对通知静默让过。
10. WHEN 收尾触发，其他已安装的本插件集合通知业务 SHALL 已完成；未识别通知和普通消息 SHALL 保持放行。

### Requirement 8：独立控制台

**User Story:** 作为管理员，我要每个插件只显示自己拥有的功能。

#### Acceptance Criteria

1. keyword SHALL 提供全局配置与关键词两个 Tab。
2. welcome SHALL 提供全局配置与欢迎语两个 Tab。
3. rules SHALL 提供全局配置及四个违禁 Tab。
4. 设置 Tab SHALL 只显示本插件的配置字段。
5. 控制台 SHALL 将群名嵌入名单表格，而非独立群名册页面。
6. 每个插件 SHALL 提供独立构建的 `pages/console` 产物。
7. 页面测试 SHALL 校验各自 Tab、资源和接口命名空间，其他插件缺席时仍可使用。

### Requirement 9：回归验收

**User Story:** 作为维护者，我要新增边界有测试，未批准的行为保持原样。

#### Acceptance Criteria

1. 拆分完成后 SHALL 通过三个插件的单测、ruff、前端构建与专项迁移/派发测试。
2. 旧测试 SHALL 按功能迁移，配置分片、页面归属、原子保存、直接文本边界、通知收尾及冲突策略的断言按本次已批准规则更新。
3. 未变业务的回复与日志文案、级别 SHALL 以合并提交 `1520769` 为准：沿用 `[群管]` 前缀、跳过类DEBUG及统一命中INFO，保留 PR #25 的嵌套字符串打码测试；新增迁移、清理、统一保存失败提示 SHALL 明确说明原因。
   - 群管保留 `find_contact_card`、`card_identity` 和100字符身份截断；身份写入违禁日志text与飞书消息。配置键和原因码不重命名。
   - 五条命中线路沿用 `hit_log.log_hit` 的统一输出链；打印payload前执行既有字典/列表、URL参数、JSON字符串、CQ字符串打码。敏感片段匹配口径保持现有实现，其他字段只在既有测试范围内保证保留。拆分不新增原始未打码payload日志，不放宽测试。
4. 三个插件 SHALL 分别通过 `ruff check .`。
5. 跨功能旧测试 SHALL 保留可追溯覆盖去向，跨插件联合测试 SHALL 与独立安装测试区分。

### Requirement 10：群名与配置原子保存

**User Story:** 作为管理员，我要新增群、拉群名后一次保存即可生效。

#### Acceptance Criteria

1. 每个插件 SHALL 自持 `group_name` 表。
2. 设置页 SHALL 提供「拉取群名」动作和一个统一「保存」按钮，统一按钮同时保存配置与群名。
3. WHEN 点击拉取，插件 SHALL 调用一次 `get_group_list`，按当前未保存名单草稿并集过滤结果，仅更新页面草稿。
4. WHEN 点击保存，后端 SHALL 以同一请求的完整配置为准，在一个事务中写入配置与范围内群名；任一失败 SHALL 回滚两部分。
5. 业务页面 SHALL 从本插件已保存群名显示名称，缺行显示空串。
6. WHEN 协议缺群、返回空名字或拉取失败，页面和保存流程 SHALL 保留已有有效名称，禁止意外清空。
7. 每个插件 SHALL 仅写本库；WHEN 提交名单外群名，后端 SHALL 过滤该群名且保留历史已存行。
8. rules SHALL 用历史映射显示日志群名，违禁日志表 SHALL 保持无群名列。
9. WHEN 数据库提交成功，插件 SHALL 一次替换有效配置快照；WHEN 保存失败，内存快照和页面草稿 SHALL 保持保存前/待保存状态。

### Requirement 11：直接文本边界

**User Story:** 作为群管理员，我要转发里的广告被审核，但转发或引用里的指令不被执行。

#### Acceptance Criteria

1. rules SHALL 保留 `resolve_audit_text` 和现有嵌套转发查询；keyword、welcome SHALL 不调用转发展开、引用取文、OCR 或卡片取文。
2. WHEN 本条消息含直接文本段，keyword 和 welcome SHALL 只消费该直接文字；WHEN 仅有非文本内容，两个插件 SHALL 静默让过文本处理。
3. WHEN 引用或转发旁附有群员新写的文字，两个插件 SHALL 只识别新写文字，忽略被引用/转发内容。
4. 欢迎语查询 SHALL 要求规范化后的完整直接文本等于「欢迎语」；设置 SHALL 要求首行是「欢迎语 设置」或其后紧跟空格/Tab；其他相似前缀 SHALL 作为普通文本。
5. WHEN 直接文本读不出可靠来源，两个插件 SHALL 返回空文本，不用消息概要或嵌套内容补齐。
6. 私聊交码 SHALL 只消费直接文本，验证码仅藏在引用、转发或图片中时 SHALL 保持未通过。

## 实施边界

设计中上述四类功能缺口已闭合。创建远端前仍需确认新仓库公开性、初始版本和展示名；这些属于发布/建仓参数，不改变本设计。历史 metadata 描述在实际搬迁时按真实行为修正，禁止继续宣称入群立即发送欢迎语。本阶段只写 spec，不执行建仓、迁移、清理、提交或 push。
