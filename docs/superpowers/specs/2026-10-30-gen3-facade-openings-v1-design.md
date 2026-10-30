# MC-Architect-Agent GEN-3：Façade & Openings v1 设计

**状态：**用户原则批准，已纳入补充裁定

**目标环境：**Windows 10/11 x64、Python 3.12、Minecraft Java 1.21.5；创作尺度约 1 方块/米。

## 意图

在现有建筑引擎和 GEN-2 Roof & Eaves v2 上，为 hall 和 corridor 增加可复用的墙体、门窗与立面木构配置。设计优先服务 Minecraft 中的视觉效果和模块组合；所有新样式是可编辑的 Minecraft 创作配置，不是传统营造尺寸或地域真实性认证。

## 当前依据

- PR #2 已于 2026-10-30 合入 `main`，随后 Task 0 PR #5 于 2026-10-31 以普通 merge 合入，当前基线提交为 `48636674bcc3c812bdc97cbc815e0474de3b5cf6`。Task 0 合并前 Windows 全套为 **386 passed**；PR #5 的两次 Windows 必需检查及 Ubuntu 兼容检查均成功（Actions runs `41092577087`、`41092639913`）。重复 PR #1 已关闭；其 Phase 2 内容已在 main。
- `jiangnan_agent.generators.components` 已有 `generate_wall`、`generate_door`、`generate_window`、`generate_column` 和 `generate_beam`；hall 固定生成一个中置门与正面窗，corridor 当前为开敞廊架。
- Task 0 已修复 SQLite 模块目录与 Python Asset Registry 的版本发现及同步，保留旧记录；当前 hall/corridor 的资产版本为 v4、参数 Schema 为 v3。GEN-3 将新增资产 v5 与参数 Schema v4。
- Mine2Blend 和用户指定的 Blender 路径在本机存在；`workspace/` 含既有用户数据，后续只新增唯一命名的工程、导出与预览，不覆盖或清理已有内容。

## 目标与范围

1. GEN-2/DB-2 的目录收尾已经在独立 Task 0 PR 中完成：SQLite 实现模块与 Python Asset Registry 同步，同时保留计划模块和旧记录查询。
2. 为墙面、开口、门、窗、柱梁装饰建立明确、可序列化的参数 Profile；在现有生成器上作增量扩展。
3. hall 接入完整立面配置；corridor 可选配置围护和装饰，默认仍保持开敞。
4. 提供 `jiangnan_whitewall_timber`、`huizhou_graybrick_entry`、`garden_open_gallery` 三种 Minecraft 创作配置。
5. 用真实引擎生成 roof profile 与 façade 示例工程、Sponge v3 文件及四视图预览，并记录可见问题和未完成的实机验证。

## 非目标与保护边界

- 不改写 hall/corridor 主生成器，不改变无 façade profile 时的既有逐方块结果。
- 不修改屋顶算法、Assembly 锚点、ProjectEditor 历史语义、工程 JSON 格式主结构、Schematic v3 或 MCP 协议。
- 不将 DB-2 中 `candidate` 或未经人工确认的语义构件转为正式生成模板。
- 不实现复杂斗拱、歇山/攒尖屋顶、大型门楼或新 AI 模型；不声称传统尺寸、比例或地域史实。
- 不写入 Minecraft 世界存档。自动化测试、Blender 预览与游戏内 WorldEdit 验收分别记录；未在游戏验证时保持 `pending`。

## 集成方案

考虑过的路径：

1. 重写或压平既有历史，再强制更新远程分支。历史较整齐，但会重写用户已推送的 DB-2/GEN-2 分支。
2. 保留已有历史；PR #2 先入 `main`，从现有 DB-2/GEN-2 分支建立集成分支并合入最新 `main`，不强制推送。先以独立 PR 收尾 Task 0，再以其分支为基础提交 GEN-3 façade PR。
3. 将 DB-2、GEN-2、Task 0 和整个 GEN-3 合为一个大 PR，减少 PR 数量，但会让 GEN-2 收尾与新立面功能难以分开审查。

采用方案 2，符合用户“先合并 PR”的安排，也保留 Task 0 与 façade 功能的分阶段审查。PR #2 已完成，PR #1 已关闭。Task 0 集成分支以普通 merge 合入最新 `main`，Task 0 PR #5 在 Windows CI 和旧工程回归通过后普通合入，生成当前基线 `48636674bcc3c812bdc97cbc815e0474de3b5cf6`。GEN-3 分支 `phase-gen3-facade-v1` 从该更新后的 `main` 创建。禁止重写已有远程分支历史，不重复带入 Phase 2、Phase 3 或 DB-1。

## 设计

### 1. 资产与参数版本

- 将已有目录作为历史快照保留；新增 hall/corridor 参数 schema v4、Asset Registry v5，以及对应的知识库项目代码来源记录。创作预设来源使用 `minecraft_adaptation`，不引用 DB-2 候选构件。
- SQLite 模块目录按目录版本自动发现。实现中的 hall/corridor 以 Python Asset Registry 为准；同步当前快照中的 v4、v5 记录，保留现有 v3 记录且不改写旧版本。计划模块仍从最新 SQLite module catalog 读取。资产及模块快照按版本不可变；预设独立登记，并可与 GEN-2 屋顶 Profile 组合。
- `get_module_definition(id)` 继续默认返回最新版本，显式版本读取仍可用。`list_modules()` 默认返回每个 ID 的最新记录，可显式请求历史版本；保留 `include_planned` 行为。若现有表结构足以表达，不增加无必要的数据库迁移。
- LibraryService 自动读取版本化样式目录；新增三种 façade 创作 Profile 的可查询记录。每个配置保留版本、生成器来源、适用设计目标和 Schema 引用。

### 2. 立面 Profile 与几何生成

- 新增 typed `WallPanelProfile`、`DoorProfile`、`WindowProfile`、`TimberDetailProfile`、`FacadeOpening`，并以一个可序列化的 `FacadeProfile` 组合它们。配置材料角色使用完整 BlockState，并校验方块和方向属性。每个 `FacadeOpening` 有稳定 `opening_id` 和连接用途标识（`primary_entry` 或 `non_connecting`）；hall 必须恰有一个 `primary_entry`，不得通过扫描所有门方块推断连接锚点。
- `generate_wall` 在保留现有位置参数和默认行为的基础上接受可选 Profile。墙体厚度沿其 X 或 Z 法向展开；层序、墙面材料、局部装饰由 Profile 决定。每一层保留同一开口掩码，装饰不得填入开口或通行空间。
- Door Profile 至少支持 1 格单扇门和 2 格双扇门、门框及门楣。Window Profile 支持普通窗、离散木格窗与少量装饰花窗样式，并配置宽、高、窗框厚度及材料。
- 立面局部坐标统一为 X 沿正面从左至右增加、Y 向上、Z 从 rear 向 front 增加；front/rear/left/right 的朝外法线分别为 +Z/-Z/-X/+X。front/rear 按 X 向开间索引定位；left/right 按实际侧柱间段或局部 Z 坐标定位，不复用 `bay_count`。
- hall 使用显式 `facade_profile` 控制门、窗、墙层和木构细节；旧 `door_width` 与旧材料配置仍可读。`FacadeOpening` 以稳定 ID、立面、开间/柱间段索引或局部坐标、段内偏移和门槛/窗台偏移定位；未给出布局时，显式 Profile 沿用当前中门与两侧正面窗的规则。主入口位置变化后，以该 opening 的实际位置重新计算现有 `front` 锚点坐标；锚点名称及模块连接接口保持不变。`through_passage` 仍从同一主入口派生既有 `rear` 锚点；首版不允许其他开口新增连接锚点，其他开口只能标记为 `non_connecting`。必要时以省略哨兵区分旧参数是否显式给出，冲突必须报错。
- corridor 仅在显式 Profile 下生成指定围护面；`garden_open_gallery` 保持通透，默认无 Profile 时仍生成当前开敞廊架。
- `WallPanelProfile` 明确厚度层从立面参考层沿 `inward` 或 `outward` 扩展；单层默认保持当前占格。Profile 不授予整面墙的替换权；`BlockOwnershipMap` 只对逐格明确授权的墙块开放替换。验证扩厚后与柱梁、屋檐、门窗、Assembly 净空和连接区的关系。
- 墙、门窗、柱梁和装饰之间使用方块所有权及开口保留掩码。门窗和装饰只能替换 Profile 明确声明可替换的墙体格；结构格、通行格和未声明占格冲突受保护或显式报错，不依靠生成顺序静默覆盖。木构 Profile 只补充外露柱梁、柱础/柱头、简单梁枋层次及墙木收边。
- 新建 Profile 经过现有旋转/镜像流程时，仅允许已支持的方块状态；不支持的属性变换报错。

### 3. 预设和示例

三种预设是可覆盖的 Minecraft 视觉配置：

- `jiangnan_whitewall_timber`：白墙、深色木构、木格窗。
- `huizhou_graybrick_entry`：浅色墙面、灰砖点缀、深色门框。
- `garden_open_gallery`：通透木构、开敞廊面与低密度装饰。

DB-2 候选构件不会被读取为这些配置的事实或模板。Task 0 的三个 roof profile 示例与 Task 6 的三个完整 façade 建筑分别留存：前者在 façade 变更前单独审查屋顶轮廓，后者验证新立面和建筑组合。所有输出写入唯一命名的 `workspace/projects`、`workspace/exports` 和 `workspace/previews` 子路径。

## 验收设计

- 资产发现与 SQLite 查询返回同一最新 hall/corridor 版本、Schema 版本和锚点；旧版本可显式查询，计划模块仍被正确过滤；既有 DB-1/DB-2 记录不丢失。
- hall/corridor 无 `facade_profile` 时默认方块哈希与既有版本完全一致；所有 typed Profile 均有确定性的 JSON 编解码，旧 `door_width`、`materials` 与新 Profile 仅在双方显式给出时检查冲突。旧工程和固定资产快照保持原样。
- 覆盖 3/5 开间 hall、多个正面门、唯一主入口移动后的 `front` 锚点更新、侧面开窗、按实际柱间段定位、墙体加厚与扩展方向、直廊围护、单/双门、普通窗/木格窗/花窗、X/Z 立面方向、开口掩码、材料状态、格窗旋转/镜像、装饰冲突、屋顶组合、ProjectEditor 撤销/重做及结构/通行/连接净空冲突。
- 覆盖参数 Schema 兼容、资产版本、项目保存/重载、局部编辑、撤销/重做、Assembly 与 `generate` 优先级、MCP 回归、Sponge v3 导出与回读。
- Task 0 的三个屋顶预设各有可编辑工程、Schematic 和 top/front/side/perspective 四张渲染；GEN-3 三组完整建筑各有 Blender 四视图，并留存人工视觉审查记录。
- Windows 10/11、Python 3.12 全套测试必须通过；真实 Minecraft Java 1.21.5/WorldEdit 粘贴若未实际操作，报告明确标为待验。

## 留给实施者的选择

Profile 内部字段命名、离散窗格绘制方式、预设的具体材料方块及示例尺寸，应以现有方块状态校验器和生成器接口为准；只选取可验证、可旋转/镜像的方案。任何拟增加的第三方依赖或对已有工程/输出格式的不兼容变化，都不在本设计授权范围内，应先回报。
