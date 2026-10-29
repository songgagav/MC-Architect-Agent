# Jiangnan Architect Agent 开发路线图

项目聚焦江南单体建筑、园林构件与模块组合，不负责整座城镇的自动规划。目标游戏版本固定为 Minecraft Java 1.21.5，DataVersion 4325。默认只生成独立工程文件，不直接改写已有 Minecraft 世界。

## 九个开发阶段

### Phase 0 — 项目初始化

建立独立 Git 仓库、Python 环境、项目配置、pytest 和 CI。支持读取/保存工程配置并运行首条 CLI 命令。**实现完成，基线已上传 GitHub。**

### Phase 1 — Minecraft 方块数据引擎

建立 `Block`、`BlockState`、`VoxelModel`、`BoundingBox`；统一 X/Y/Z；按 Sponge 官方 Schematic v3 规范导出和回读 `.schem`。方块状态需保留楼梯、半砖、门、栏杆等属性。**实现和自动化验收完成；Minecraft/WorldEdit 实机放置待验。**

### Phase 2 — 参数化古建筑构件引擎

实现柱、梁、墙、门窗、台基、屋顶、檐口、回廊等基础生成器，并可参数化生成厅堂和直廊；开间、进深、柱高、屋顶坡度、出檐和材料可调。**基础实现与自动化验收完成；游戏内外观和放置验证待进行。**

### Phase 3 — 模块化组合系统

组合门楼、厅堂、厢房、亭子、回廊等模块；定义连接锚点、占地边界、方向和连接规则。支持平移、旋转、镜像、连接、拆分、替换，并检测碰撞、门洞错位、檐口冲突和接缝高差。**组合内核、自动验证和两进院落示例完成；游戏内拼装与外观验证待进行。**

### Phase 4 — 工程保存与局部修改系统

建立版本化 `JiangnanProject` JSON，保存完整组合、对象 ID、模块参数和连接关系；记录方块级差异与不可变版本快照，支持撤销/重做。按模块 ID 只重生成目标厅堂或直廊，保留其他模块数据；尺寸变化造成的连接错位交由 Phase 3 校验器报告。**实现与自动化验收完成；游戏内长期编辑与外观验证待进行。**

当前 `generate` 来源规则：Assembly 非空时优先验证并导出 Assembly，即使 `settings.building` 同时存在也不参与生成；Assembly 验证/渲染失败时报错且不回退。Assembly 为空时使用旧生成设置。未来可增加 `source="auto" | "assembly" | "legacy"`，其中 `auto` 延续当前规则；现阶段不实现该参数。

### Phase 5 — Codex 本地建筑工具接入

由当前 Codex 通过本机 MCP stdio 服务调用 Python 建筑引擎。工具覆盖工程和模块读取、厅堂/直廊创建、参数修改、模块变换与连接、工程校验、历史差异检查和 `.schem` 导出。模型只选择结构化参数，方块由本地程序生成；不调用模型 API，也不要求 Agents SDK。**实现、自动化验收及 Codex 自然语言闭环验收完成。Minecraft/WorldEdit 实机放置仍待人工验证。**

### Phase 6 — 三维预览与视觉审核

使用 Mine2Blend 将 Sponge `.schem` 转成 OBJ，并调用 Blender 后台渲染俯视、正面、侧面、透视四视图。输出 `preview.json` 记录工具/输入/图片信息；可选的新旧 `.schem` 对比会生成逐方块状态差异统计和成对视图。已在本机 Mine2Blend 转换器与 Blender 5.2.3 上完成三开间厅堂的真实转换和四视图渲染，包含相机裁切回归修正。**实现与本机自动化验收完成；其他 Mine2Blend/Blender 版本和不同资源包仍需验证。**

示例命令和输入输出约束见 README 的“三维预览与修改对比”。此功能只读取 `.schem` 并写入新的预览目录，不访问 Minecraft 世界。

### Phase 7 — 江南古建筑知识库与专业构件

Knowledge Base v3 将来源、规则、地域配置拆分为独立版本化文件，并为规则登记来源元数据、地域、核查状态和适用范围。当前仅 `huizhou_core`（西递、宏村的 UNESCO 村落级描述）与 `jiangnan_suzhou`（苏州古典园林的 UNESCO 园林级描述）处于 active；其他地域为 `catalog_only`。本次无法读取全文的地方网页及相关旧摘要留在 pending 状态，不进入默认查询或生成。知识库 v1/v2、参数 schema v1、资产目录 v1/v2 保持兼容。下一步为 hall/corridor 增加来源类别明确的参数 schema v2 和地域/规则关联的资产目录 v3；默认数值只作为可复现的 Minecraft 输入，不得称作历史标准。

### Phase 8 — 本地设计工作台与完整验收

提供本地 CLI 对话工作台，后续可增强模块拖拽界面。完成“描述→生成→预览→修改→组合→保存→导出→游戏内放置”闭环。

## 五个里程碑

- **M1 方块生成闭环**：Phase 0–1；导出真实可用的 `.schem`。
- **M2 模块化设计闭环**：Phase 2–4；生成、组合、编辑和保存模块。
- **M3 AI 设计闭环**：Phase 5；自然语言控制建筑生成与修改。
- **M4 视觉审核闭环**：Phase 6；自动预览并比较修改。
- **M5 完整个人工作台**：Phase 7–8；知识库、扩展构件和长期使用。

## Agent 工具组

| 工具组 | 典型工具 | 职责 |
| --- | --- | --- |
| 工程与模块 | `list_projects`, `get_project`, `create_project`, `list_modules`, `get_module`, `create_module` | 查找、创建和读取工程模块 |
| 参数与装配 | `set_parameters`, `transform_module`, `connect_modules`, `replace_module` | 生成、调整和组合厅堂/直廊 |
| 质量检查 | `validate_assembly`, `inspect_changes` | 检查冲突并读取有界版本差异 |
| 工程交付 | `export_schematic` | 校验并导出 Sponge v3 文件 |

首版 MCP 工具名以项目 README 与服务注册表为准。版本撤销和重做继续由现有 `jiangnan history/undo/redo` CLI 提供；三维预览属于 Phase 6。

## 质量要求

1. **可重复生成**：相同输入、模块版本和随机种子产生相同方块结果。
2. **独立可编辑**：每个模块有固定 ID，可独立更改或替换。
3. **方块状态正确**：旋转后门、楼梯、屋脊等状态正确。
4. **可回退**：工程变更有历史并可恢复。
5. **输出可靠**：`.schem` 可独立回读校验，并通过真实游戏放置检查。
6. **原始世界安全**：不直接写入已有 Minecraft 世界；施工先生成独立文件。

## 固定质量案例

三开间厅堂、五开间厅堂、转角回廊、双侧厢房组合、旋转 90° 的屋顶、带台阶的园林亭。建筑检查还要覆盖门窗可用、通行空间、屋顶缺口和模块接缝。

## 权限边界

生成与预览可以自动运行。覆盖已批准模块、删除文件、修改 Minecraft 正式世界需要人工确认。
