# Phase DB-1：Minecraft 建筑知识库与资源数据库

## 目标与边界

本阶段为 Windows 10/11 x64、Python 3.12 和 Minecraft Java 1.21.5 建立本地参考库。设计重点是 Minecraft 建筑的视觉比例、风格一致性和模块自由组合，采用约 1 方块 = 1 米的创作网格；不把风格建议说成历史营造标准。

本库不替换工程 JSON，也不修改 `Assembly`、`ProjectEditor`、工程历史、现有厅堂/回廊生成器、Sponge Schematic 导出、Codex MCP 工具或 Minecraft 存档。它提供数据登记、只读投影分析和查询。默认生成行为保持：非空 Assembly 优先；空 Assembly 才走旧设置；Assembly 无效时明确报错。

## 存储分层

```text
版本化 JSON 注册表 ──校验/导入──> SQLite（索引、关系、聚合、查询）
用户原始 .litematic / .schem / 预览图 ──路径 + SHA-256──> 文件系统
可编辑建筑工程 ──保持现有格式──> 工程 JSON（不进入参考库）
```

- **SQLite**：Python 标准库 `sqlite3`，开启外键，迁移号记录在 `PRAGMA user_version` 和 `schema_migrations`。DB-1 原始 schema 为 3；DB-2 在其基础上追加迁移 004，当前 schema 为 4。迁移按 `001` 至 `004` 顺序执行；异常会回滚。
- **JSON**：知识库沿用 `jiangnan_agent/knowledge/v3/`；hall/corridor 生成器参数沿用 `parameters/v2/`；跨模块设计参数登记位于 `library/parameters/v1/minecraft_building_design.json`；模块索引位于 `library/catalog/v1/modules.json`；风格预设位于 `library/styles/v1/`。这些文本文件是可审阅、可版本控制的定义。
- **文件系统**：数据库仅记录原始文件路径、SHA-256 和聚合信息。不会把几百万个方块拆成数据库行，也不会复制或修改用户投影。相对路径以仓库根目录为准；仓库外文件保留绝对路径。
- **工程边界**：数据库的参考资产不是工程中的模块实例。工程仍由 `workspace/projects/*.jap.json` 保存；参考库不保存工程方块快照。

默认 SQLite 路径为 `workspace/library/architect_library.sqlite3`，已加入 `.gitignore`。`Template/` 中的用户投影同样不会提交。SQLite 备份不会包含原始投影和预览图片，必须另行备份这些文件。

## Schema 概览

| 表 | 内容 | 关键约束 |
| --- | --- | --- |
| `schema_migrations`、`library_meta` | 迁移记录、稳定 library ID | 迁移版本主键；重复初始化不重复应用 |
| `knowledge_registry_versions` | 知识库完整 JSON 快照、SHA-256、加载时间 | 版本主键；同版本内容不可变，变更必须升版本 |
| `knowledge_sources`、`knowledge_rules`、`region_profiles` | 当前查询索引及注册表版本 | 来源/规则 ID 唯一；规则外键指向来源；地域状态受限 |
| `knowledge_rule_regions` | 规则的地域适用关系 | 规则、地域外键和复合唯一键 |
| `parameter_schemas` | 模块参数 schema 定义 | `(schema_id, version)` 复合主键 |
| `module_assets` | 模块定义、实现状态、生成器引用、连接锚点 | `(asset_id, version)` 复合主键；仅 `implemented` 可关联 schema |
| `module_asset_regions`、`module_dependencies`、`module_knowledge_rules` | 模块地域、依赖和知识规则关系 | 模块/地域/规则外键；定义与工程实例分开 |
| `style_profiles`、`style_reference_assets` | 风格预设及参考资产关系 | `(profile_id, version)` 复合主键和外键 |
| `reference_files`、`reference_assets` | 文件 SHA 去重、稳定资源 ID 和版本元数据 | SHA-256 唯一；`(asset_id, version)` 和 `(asset_id, file_id)` 唯一 |
| `reference_material_counts` | 每文件的完整 BlockState 计数 | 文件外键；状态唯一；计数为正数 |
| `reference_layer_counts` | 每文件、每 Y 层的 BlockState 计数 | 文件外键；`(file_id, y, state)` 唯一 |

知识库快照包含版本化 Sources、Rules 和 Region Profiles。数据库中的这些规范化表是当前版本查询索引；旧版内容保存在 `knowledge_registry_versions.snapshot_json` 中。重复加载相同版本和内容是幂等的；对同一版本改内容会失败并要求创建新版本，避免无声覆盖旧快照。模块定义、参数 schema 和风格预设也按同一原则保护：相同 ID 与版本的 JSON 或定义路径发生变化时初始化会明确失败，要求提高资源版本号。

地域仅 `huizhou_core` 和 `jiangnan_suzhou` 为 `active`。嘉兴/湖州、宁波/浙东、扬州/运河、上海/松江仅为 `catalog_only`，地域规则查询不会返回它们的内容。模块定义中 hall/corridor 当前版本均登记为 `implemented`；柱梁、墙体、门窗、屋顶、檐口、厢房和亭子只登记为 `planned`，默认模块列表不返回计划资源。

参数表同时登记现有 hall/corridor 生成器 schema v2 和通用 `minecraft_building_design@1`。通用 schema 覆盖整体宽/深/高、开间和柱网、屋顶形制/坡度/屋脊轮廓、出檐/翘角/屋面层次、材料、门窗比例、装饰密度、参考资产与模块连接约束。每项标为当前支持、部分支持、风格建议或规划项，并列出用户输入、派生、文献、测绘、参考统计、用户偏好或 Minecraft 适配等来源类别。

通用 schema 只登记设计参数，不改变现有生成器。未实现字段（如翘角、屋脊细化、屋面语义层、独立门窗比例或装饰密度生成）保留空默认值并标记状态；现有 hall/corridor 字段沿用原 schema 和 resolver。资料未提供可靠测绘尺寸时，不写入伪历史默认值。用户可覆盖风格建议，现有几何、方块状态和 Schematic 硬校验仍然执行。

## 参考资产与权利记录

`ReferenceAsset` 保存稳定 `asset_id`、资产 `version`、显示名、来源文件、格式、DataVersion、地域归属状态、建筑类型、尺寸、非空气占用方块数、BlockState 统计、半开区间包围盒、预览路径、SHA-256、导入/兼容状态、作者、来源说明、使用权声明、时间戳和解析器版本。

- 未由用户明确分配地域或来源证明的投影保持 `region_assignment_status=unverified`，不从文件名推断地域。
- 作者字段只取投影中嵌入的作者。授权缺失时 `license=unknown`、`redistribution=not_granted`；拥有本地文件不表示可再分发。
- 可按同一资产 ID 登记新文件版本；相同文件 SHA 会复用 `reference_files` 与聚合统计。相同资产 ID 和同一 SHA 再导入是幂等操作；若元数据不一致，会明确报错。
- 预览文件通过 `library previews` 关联。完整性校验会检查原始投影 SHA-256 和预览路径是否存在。
- 删除外部资源不会破坏历史元数据，但 `library verify` 会报告缺失文件。SQLite 不会尝试恢复或替换用户文件。
- `library init` 检测到旧解析器版本时，会为每个去重文件 SHA 读取至少一个 SHA-256 匹配的原始投影，并在事务中重建统计与 DataVersion provenance。若所有副本都缺失、校验和变化或无法解析，初始化会明确报错；可用 `library verify --asset-id <id>` 独立核查每个资产登记的路径，缺失或哈希不符会抛出明确异常，避免一个失效副本掩盖其他可用副本。

## Litematic 导入器

入口为 `jiangnan_agent.library.litematic.read_litematic()` 和 `analyze_litematic()`，由 `LibraryService.import_litematic()` 调用。它支持 gzip 或未压缩 NBT、多 Region、有符号区域尺寸、Region DataVersion、方块 palette，以及按紧密位宽打包且可能跨 64 位边界的 `BlockStates`。数组长度按区域体积和 palette 位宽校验；palette 越界、格式版本未知、NBT 损坏或无占用方块会产生明确错误。

区域的 `Position` 与正负 `Size` 原样保留在解析模型中，迭代坐标按 Region 方向还原；完整原始状态仍由源文件和 SHA-256 保全。统计过程流式迭代，不创建逐方块 SQLite 行。报告包括占用方块包围盒、尺寸、状态/材料计数、Y 层统计、水平截面范围和覆盖率。材料 ID 统计把 stair 等方块状态变体聚合到同一方块名。

为限制本地文件导致的资源消耗，投影文件与解压后的 NBT 大小各限制为 128 MiB；单个 Region 及整份投影总计最多分析 8,388,608 个体素位置。超过上限会明确拒绝；体积检查会在复制 packed 状态和扫描方块前生效。[LitematicaSchematic.java](https://github.com/maruohon/litematica/blob/27efd02b5f691a8999f1ac3854269f9fa202b5ca/src/main/java/litematica/schematic/LitematicaSchematic.java)、[TightLongBackedIntArray.java](https://github.com/maruohon/litematica/blob/27efd02b5f691a8999f1ac3854269f9fa202b5ca/src/main/java/litematica/schematic/container/TightLongBackedIntArray.java)、[SchematicRegion.java](https://github.com/maruohon/litematica/blob/27efd02b5f691a8999f1ac3854269f9fa202b5ca/src/main/java/litematica/schematic/SchematicRegion.java)。

文件级与每个 Region 的 DataVersion 都参与兼容判断；只要其中有低于 4325 的版本就标为 `parsed_older_data_version_requires_review`，有高于 4325 的版本则标记为较新版本不兼容。各 Region 版本保存在资产 provenance 中，不会由文件级版本覆盖。读取成功不代表游戏可无损载入；当前不调用 Minecraft DataFixer、不升级旧方块状态，也不声称经过 1.21.5/WorldEdit 实测。

## 风格预设

- `jiangnan_mc_classic` 以 `jiangnan_suzhou` 为 Minecraft 视觉设计目标。
- `huizhou_mc_classic` 以 `huizhou_core` 为 Minecraft 视觉设计目标。
- 两个配置都标记 `classification=minecraft_visual_style`。`grid_scale_meters_per_block=1.0` 是用户创作尺度；材质候选动态取已登记参考投影中频次最高的方块状态。
- 风格 JSON 固定写出参考资产版本（当前两个预设版本为 2）；查询会使用这些具体版本的统计，导入同一 ID 的新参考版本不会悄悄改变既有预设的配色候选。缺少固定版本时显示为缺少引用。
- `silhouette`、`roof_layers` 及材料的屋顶/墙体语义保持 `unverified`，直至人工标注或有经过验证的识别方法。装饰密度是用户可覆盖字段。
- 风格配置不限制用户偏好，也不直接调用或改写生成器。

## Windows 命令行

```powershell
cd E:\MCbuild
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

jiangnan library init
jiangnan library import "Template\芳堂-茯茯角.litematic" --asset-id reference.fangtang --name "芳堂-茯茯角" --building-type hall
jiangnan library import "Template\流苏坊框架-茯茯角.litematic" --asset-id reference.liusufang-frame --name "流苏坊框架-茯茯角" --building-type frame
jiangnan library list references
jiangnan library show reference.fangtang
jiangnan library materials reference.fangtang
jiangnan library layers reference.fangtang
jiangnan library list regions
jiangnan library list sources
jiangnan library list rules --region jiangnan_suzhou
jiangnan library list parameters
jiangnan library parameter minecraft_building_design
jiangnan library module jiangnan.hall
jiangnan library list styles
jiangnan library style jiangnan_mc_classic
jiangnan library verify
jiangnan library backup --output workspace\library\backup.sqlite3
```

如果 `jiangnan` 命令尚未安装到当前 shell，可将命令前缀换成 `.\.venv\Scripts\python.exe -X utf8 -m jiangnan_agent.cli`。`--database <path>` 可放在任何 `library` 子命令之后，供临时数据库和测试使用。Python 查询 API 位于 `jiangnan_agent.library.LibraryService`。

## 两份实际模板的导入记录

本机 `Template/` 中的两份文件均已只读导入到未跟踪数据库 `workspace/library/architect_library.sqlite3`。完整机器报告在 `workspace/library/db1-import-report.json`；本地记录只用于当前机器，仓库不包含用户原投影或渲染图。

| Asset ID | 来源文件 | DataVersion | 尺寸 X×Y×Z | 非空气方块 | BlockState 变体 | 区域归属 | SHA-256 前缀 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `reference.fangtang` | `芳堂-茯茯角.litematic` | 3465 | 43×36×42 | 7,930 | 122 | 未核查 | `0bb61a446678…` |
| `reference.liusufang-frame` | `流苏坊框架-茯茯角.litematic` | 3465 | 31×31×32 | 3,909 | 83 | 未核查 | `a26bc4b06639…` |

解析尺寸、非空气方块数和 SHA-256 与本机 2026-10-29 的既有 Mine2Blend/Blender 转换报告一致；转换报告分别列出 43/31 个唯一材料 ID 和正面、侧面、俯视、透视渲染。该对照是文件统计一致性证据，不是当前 DB-1 重新运行 Mine2Blend、Minecraft 1.21.5 或 WorldEdit 的端到端验收。

作者元数据均为 `Paper_Angle`，区域来源和再分发许可都没有独立核实。因此数据库未给两份投影分配徽州或苏州地域，也没有把它们表述为历史测绘。引用在风格 JSON 中仅表示用户提供的 Minecraft 参考文件。roof/wall/window 等语义分区仍为未核查。

## 备份与恢复

创建不会覆盖既有文件的 SQLite 在线备份：

```powershell
jiangnan library backup --output workspace\library\architect_library-backup.sqlite3
```

备份后分别校验原投影和图像文件，并把它们与数据库放进同一套个人备份中。需要使用备份时，停止写入，然后将 `--database` 指向备份副本；不要让程序同时写同一个数据库副本，也不要用未审核的覆盖操作替换现有用户库。

## 测试与验收状态

- Windows Python 3.12 环境：完整测试 `288 passed`；MCP stdio 协议回归 `1 passed`。
- Wheel 构建成功；包内检查确认包含 DB migrations、模块目录、两份风格 JSON 和通用参数 JSON，并且未打包用户 `Template/` 或 `workspace/`。
- 新增测试覆盖迁移/重复初始化、知识快照版本与哈希、地域隔离、外键和 ID 约束、参数来源/状态、模块/参数/风格版本不可变、固定和首次解析风格引用版本、SHA 去重、解析器升级重算和共享文件坏路径报告、资产新版本、材料/高度层统计、状态属性保留、packed array 跨 long 解码、零值首 word、多 Region/负尺寸、root/Region 版本差异、资源上限、压缩/未压缩 NBT、损坏文件、预览关联、事务回滚和 SQLite 备份。
- 新增 CLI 覆盖库初始化、地域/参数查询；既有测试继续覆盖 Assembly/generate 裁定及工程接口不变。
- 两个真实用户模板成功导入；尺寸、占用方块数与 SHA-256 已和既有本地报告对照。真实 Minecraft/WorldEdit 的 1.21.5 放置验收仍待进行。
- DB 路径和用户预览图保持本地未跟踪；知识、参数、模块和风格 JSON 才是提交内容。
