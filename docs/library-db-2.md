# Phase DB-2：建筑语义标注、构件分析与 Minecraft 风格提取

## 范围

DB-2 在 DB-1 的 SQLite 参考库上追加 schema v4。它复用 `LibraryService`、只读 Litematic 解析器、BlockState 模型和既有 `jiangnan_mc_classic` / `huizhou_mc_classic` 预设；不改生成器、Assembly、ProjectEditor、工程历史、Schematic、MCP 协议或 Minecraft 世界存档。

分析目标是 Minecraft 创作参考：统一按 1 方块约等于 1 米描述网格，但不宣称现实尺度复原。输入投影的 DataVersion 原样记录。低于 Minecraft Java 1.21.5 / DataVersion 4325 不会阻止分析，也不会触发 DataFixer 或 DataVersion 篡改。

## 坐标及选择器

所有标注以原始 Litematica Region 的绝对源坐标保存。负尺寸 Region 的坐标方向由解析器恢复后再进行选择。支持三种几何：

| 几何 | JSON 形态 | 约束 |
| --- | --- | --- |
| 整个 Region | `{}` | `region_name` 独立保存在 annotation 行；只统计非空气位置 |
| 半开盒 | `{"min":[x,y,z],"max":[x,y,z]}` | `min` 含边界、`max` 不含；每轴非空且完全位于对应 Region |
| 精确方块集 | 输入 `{"positions":[...]}`；存储 `{"runs":[[y,z,x0,x1],...]}` | 非空、唯一、在 Region 内且位置上为非空气；X 游程半开、排序并合并相邻方块 |

精确集合避免把每一个方块扩展为独立 SQLite 行。构件快照保存相对于局部原点的 X 游程；标注 selector 保留原始全局坐标。BlockState 字符串保留完整状态属性；材料汇总另按方块 ID 统计。构件尺寸和包围盒从所选的实际占用位置计算，因此空白边距不会被误当成构件本体。

## 语义状态与人工审核

允许标签：`roof_surface`、`roof_ridge`、`eaves`、`column`、`beam`、`wall`、`door`、`window`、`floor`、`foundation`、`railing`、`decoration`、`unknown`。

首版的规则候选只利用 Minecraft 方块身份：门方块生成门候选，玻璃类方块生成窗候选，栅栏/墙/铁栏杆方块生成栏杆候选。方块身份不能确定建筑语义，因此所有建议都标记为 `candidate`，记录 rule ID、规则版本与置信值；重复运行是幂等的。不会把文件名、作者名、预设地域名当作来源证据。

人工创建和编辑也先进入 `candidate`。`review_annotation` 追加一个 revision，并要求填写审核人及 `verified` 或 `rejected` 结论；编辑后再次回到 `candidate`。只有当前被选取的 `verified` revision 能注册为参考构件。过去已审核的 revision 和已注册构件作为历史快照保留，不会被静默重写。

## 表结构

迁移文件：`jiangnan_agent/library/migrations/004_semantic_annotations.sql`。

| 表 | 内容与约束 |
| --- | --- |
| `semantic_annotation_revisions` | 以 `(annotation_id, revision)` 为主键，引用精确参考资产版本；标签、几何、来源种类、状态和 confidence 受检查约束；`verified` 必须有审核人和时间 |
| `reference_components` | 只存静态参考组件快照；引用已审核 annotation revision 及原始 asset version；记录局部原点、尺寸、BlockState/材料、层统计和 X 游程；状态限定为 `static_reference` 与 `not_parameterized` / `planned` |
| `style_analysis_revisions` | 引用不可变的 style profile/version，存分析快照与审核历史；状态与 verified 审核人约束同上 |
| `style_analysis_sources` | 为每份报告固定一组具体 `asset_id@version` 来源；使用外键阻止引用不存在的资产 |

每次重新测量都先检查原始投影 SHA-256，读取结束后再检查哈希和字节数。缺失、内容改变、NBT 损坏或标注引用不存在的 Region 会产生明确错误。原文件只读。

## 风格分析

`create_style_analysis(profile_id)` 从 style profile 当前固定的参考版本生成独立的 candidate 报告。可以用 `source_assets=[("reference.fangtang", 1)]` 限制到预设已固定的来源；不允许夹带未被该预设引用的其他资源。相同 profile/source/内容重复生成幂等；内容变更后追加 analysis revision。人工作出报告审核会先重新校验每个固定来源的 SHA-256，再新建 revision 并拷贝原来源链接；来源文件变化时拒绝审核。

报告将以下项标记为实际读取的 Minecraft 数据：尺寸、占用包围盒、方块状态和材料频次、Region 尺寸/方向、各 Y 层的方块状态分布、经过人工确认的构件分析。空 Region 保留尺寸和零方块统计，层/调色板数据为空且占用包围盒为 `null`。候选标注单列，不作为已核验构件统计。未分类占用数按 `(Region, 坐标)` 计数，因此不同 Region 即使坐标重叠也分别计算；只有 verified 标注能覆盖统计。当前尚无人工分区时，报告会显示零条 verified 标注、candidate 数量和未分类占用方块数。

轮廓比例是参考投影的 Minecraft 方块包围尺寸比例；屋顶轮廓、墙木关系、装饰密度以及现实建筑构造解释没有经过语义审核时保留 `unverified` / `unknown`。参考投影可以作为两种 Minecraft 预设的创作灵感，但不会自动分配徽州或苏州地域，也不会改写两个风格 JSON 的版本或字段。

## Python API

```python
from jiangnan_agent.library import LibraryDatabase, LibraryService

library = LibraryService(LibraryDatabase("workspace/library/architect_library.sqlite3"))
library.initialize()

candidates = library.propose_annotations("reference.fangtang")
annotations = library.list_annotations(asset_id="reference.fangtang", status="candidate")
summary = library.analyze_annotation(candidates[0].annotation_id)

reviewed = library.review_annotation(
    candidates[0].annotation_id,
    reviewer="MOSS",
    decision="verified",
    note="对照投影及预览人工确认",
)
component = library.register_reference_component(
    reviewed.annotation_id,
    name="已核验的静态参考构件",
    style_tags=("minecraft-reference",),
)

style_report = library.create_style_analysis("jiangnan_mc_classic")
```

`component` 是可查询/导出的静态参考数据，不会被现有参数化生成器自动调用。想把构件变成生成器，必须在后续阶段另外实现并验证参数化映射。

## Windows CLI

```powershell
cd E:\MCbuild
$db2 = "workspace\library\architect_library_db2.sqlite3"
jiangnan library annotations propose reference.fangtang --database $db2
jiangnan library annotations list --asset-id reference.fangtang --status candidate --database $db2
jiangnan library annotations create --annotation-id manual.unclassified-example --asset-id reference.fangtang `
  --region Unnamed --component-type unknown --geometry-type block_set `
  --geometry '{"positions":[[42,35,41]]}' --database $db2
jiangnan library annotations analyze manual.unclassified-example --database $db2
# 先检查预览，再把 candidate-id-from-list 替换成列表返回的 ID
jiangnan library annotations review candidate-id-from-list --reviewer MOSS --decision verified --note "已人工核对" --database $db2
jiangnan library components register candidate-id-from-list --name "已核验静态参考构件" --database $db2
jiangnan library components list --source-asset reference.fangtang --database $db2
jiangnan library style-analysis create jiangnan_mc_classic --database $db2
jiangnan library style-analysis list --profile-id jiangnan_mc_classic --database $db2
```

组件注册和风格分析命令会返回 ID。需要导出时，将返回值赋给 `$componentId` 或 `$analysisId`，并选择一个不存在的新输出文件名，例如：

```powershell
jiangnan library components report $componentId --output workspace\library\component-report-new.json --database $db2
jiangnan library style-analysis export $analysisId --output workspace\library\style-analysis-new.json --database $db2
```

`[42,35,41]` 是这份投影的第一个占用坐标，方块为 tripwire；示例将其标为 `unknown`，不代表建筑构件。其他精确坐标、区域名和 BlockState 属性必须对照预览审核；只有确认类别正确后才应使用 `verified` 并登记静态构件。导出报告采用独占新建，目标文件已存在时会报错。

## 验收边界

- 单元测试覆盖负尺寸 Region、负坐标、空/重叠 Region、半开区间、空气/重复/越界选择、packed BlockStates、annotation revision、来源哈希变更后拒绝风格报告审核、审核权限、确定性摘要、静态组件状态、风格来源 pin、重复报告、报告不覆盖及已填充 DB-1 v3 数据迁移。
- 本地两份真实文件的尺寸、状态分布和 SHA-256 由生产解析器直接读取；报告保存在本地忽略目录 `workspace/library/`，其中不复制或改写用户投影。
- 尚未经过用户逐个构件审核的自动建议必须保留 candidate。未运行 Mine2Blend/Blender/Minecraft/WorldEdit 的验收不能报告为已通过。
- 本阶段不升级 DataVersion，不实现通用版本转换，不更改正式世界，不进入 GEN-2。

## 本机两份实际投影的初步结果

2026-10-30 使用本机 `Template/` 原件在生产解析器上直接读取。原 DB-1 的 `workspace/library/architect_library.sqlite3` 保持原样；其 schema 3 数据复制到新文件 `workspace/library/architect_library_db2.sqlite3`，迁移后为 schema 4。完整测量、候选明细、风格报告、数据库副本和哈希记录在忽略文件 `workspace/library/db2-structure-analysis-20261030.json`，两个独立风格报告也保存在同一目录。

| Asset ID | DataVersion | 尺寸 X×Y×Z | 非空气方块 | BlockState 变体 | 材料 ID | 自动候选（均未核验） | 未分类占用方块 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `reference.fangtang` | 3465 | 43×36×42 | 7,930 | 122 | 43 | `window` 6；`railing` 270 | 7,930 |
| `reference.liusufang-frame` | 3465 | 31×31×32 | 3,909 | 83 | 31 | `window` 32；`railing` 59 | 3,909 |

当前规则没有在这两份 palette 中发现直接命中的门方块 ID。`window` 和 `railing` 数字表示候选选择范围内的实际方块数，不表示已确认构件；例如 `railing` 候选含墙类方块，必须逐处检查其视觉与空间位置。两份文件均为 DataVersion 3465，保持地域归属未核查。自动标注为 4 条 candidate、0 条 verified；静态 Reference Component 为 0 个，因本阶段没有人工审核，不会凭自动猜测登记构件。未分类方块数按当前 verified 标注覆盖计算，所以与总占用数一致。

迁移副本前后 DB-1 参考资产 ID/版本/方块数、205 条材料聚合、805 条高度层聚合、4 个既有风格版本、12 个知识来源和 10 条知识规则均一致；新副本记录迁移 004 一次。源 DB-1 哈希与两份 Litematic 哈希在读取/分析前后不变。迁移副本的 SQLite `integrity_check` 为 `ok`，`foreign_key_check` 无错误。风格输出固定 `jiangnan_mc_classic@2` 与 `huizhou_mc_classic@2`，状态均为 candidate，每份报告固定两项参考资产的 v1；这没有修改 style profile JSON。

未在 DB-2 中重跑 Mine2Blend/Blender，也未在 Minecraft Java 1.21.5/WorldEdit 实机放置，所以版本内实际材质映射和可视效果仍待验。用户下一步应在预览中确认/修正语义区域后再执行审核；不要把候选列表直接当作构件库。
