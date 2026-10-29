# Jiangnan Architect Agent

本地运行的江南建筑生成项目，目标 Minecraft Java 1.21.5（DataVersion 4325）。当前包含工程 JSON、稀疏方块模型、Sponge Schematic v3 `.schem` 读写、参数化建筑生成器和可验证的模块组合内核。

## 环境安装

项目使用 Python 3.12。PowerShell 中：

```powershell
cd E:\MCbuild
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

也可以直接调用虚拟环境的 Python：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Codex 本地建筑工具

本机 MCP stdio 服务让当前 Codex 调用 Python 建筑引擎和只读知识检索。方块生成、工程保存、校验与 `.schem` 导出都在本机执行；地域知识工具返回文献来源、置信度和适用范围。本方案不调用模型 API，也不需要 API 密钥。

在 `E:\MCbuild` 的 PowerShell 中安装 MCP 可选依赖并注册服务：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"
codex mcp add jiangnan-architect -- "E:\MCbuild\.venv\Scripts\python.exe" -m jiangnan_agent.agent_tools.mcp_server --workspace-root "E:\MCbuild"
codex mcp list
```

注册后重新加载 Codex；如果工具仍未出现，重启 Codex 后再开一个对话。服务只通过标准输入输出与 Codex 通信，不开放网络端口。

首版提供以下工具：

- 工程与模块：`list_projects`、`get_project`、`create_project`、`list_modules`、`get_module`、`create_module`
- 知识查询：`list_knowledge_rules`（支持知识版本、地区、建筑类型和证据类型筛选）
- 参数与装配：`set_parameters`、`transform_module`、`connect_modules`、`replace_module`
- 检查与导出：`validate_assembly`、`inspect_changes`、`export_schematic`

当前生成器支持 `hall` 和 `corridor`。`project_path` 相对于 `workspace/projects`，`output_path` 相对于 `workspace/exports`；工具拒绝越界路径和覆盖已存在的新文件。每次模块修改都会保存为工程历史版本。可用 `inspect_changes` 查看差异，使用 `jiangnan history`、`jiangnan undo` 和 `jiangnan redo` 查看或恢复版本。

工具只在工程目录中读写 JSON，只把 `.schem` 写到 exports 目录；不会删除文件、打开或修改 Minecraft 世界存档。Schematic 请先在独立测试世界中用 WorldEdit 验证。

## 创建、读取工程

```powershell
jiangnan init --name "苏州厅堂" --output workspace\projects\suzhou-hall.jap.json
jiangnan validate workspace\projects\suzhou-hall.jap.json
jiangnan info workspace\projects\suzhou-hall.jap.json
```

工程文件以 JSON 保存，包括工程 ID、目标 Minecraft 版本、DataVersion、模块列表与生成设置。

版本 2 工程还保存模块的方块、生成参数、连接锚点、净空区和组合关系；版本 1 工程可直接读取，保存时迁移为版本 2。

查看编辑记录并撤销/重做：

```powershell
jiangnan history workspace\projects\suzhou-hall.jap.json
jiangnan undo workspace\projects\suzhou-hall.jap.json
jiangnan redo workspace\projects\suzhou-hall.jap.json
```

Python API 可按模块 ID 重新生成厅堂或直廊，记录方块差异，并在工程中保留撤销/重做快照：示例先从 `examples/hall_v1_parameters.json` 创建确定的 `hall-main` fixture，再编辑并保存。

```python
from pathlib import Path

from examples.hall_main_fixture import create_hall_main_fixture
from jiangnan_agent.io import ProjectEditor, save_project

project_path = Path("workspace/projects/editable-hall.jap.json")
project = create_hall_main_fixture()
save_project(project, project_path)
ProjectEditor(project).regenerate_module("hall-main", {"bay_count": 5}, "调整为五开间")
save_project(project, project_path)
```

## 生成建筑

```powershell
jiangnan generate --project workspace\projects\suzhou-hall.jap.json
```

默认生成到 `workspace\exports` 下的安全文件名 `.schem`。`simple_house` 可调整 `width`、`length`、`wall_height`、`roof_overhang` 和方块材料。`.schem` 为 Sponge v3 gzip-NBT，可使用 WorldEdit 导入测试世界。不要让生成器直接写入已有 Minecraft 存档。

当前生成来源规则：

- Assembly 非空时，先验证并导出当前模块组合。即使工程还带有 `settings.building`，也只使用 Assembly。
- Assembly 验证或渲染失败时直接报告错误，不回退到旧设置。
- Assembly 为空时，继续按 `settings.building` 生成单体房屋或厅堂。

未来可以增加 `source="auto" | "assembly" | "legacy"` 显式选择；目前尚未实现该参数，`auto` 的预期行为与以上规则一致。

仓库内的示例工程：

```powershell
jiangnan validate examples\three_bay_house.jap.json
jiangnan generate --project examples\three_bay_house.jap.json
jiangnan validate examples\three_bay_hall.jap.json
jiangnan generate --project examples\three_bay_hall.jap.json
```

`hall` 工程可调 `bay_count`（奇数开间）、`bay_width`、`depth`、`column_height`、`plinth_height`、`roof_rise`、`eaves`、`door_width` 和 `materials`。生成器会按参数同步调整柱网、梁、墙、门窗、台基、檐口和屋顶。

## 版本化知识、参数与资产

厅堂与直廊的新模块通过版本化资产登记创建，执行仍映射到现有 `HallParameters`、`CorridorParameters` 和生成器。参数 schema 将独立输入、派生结果、硬约束与软提示分开；冲突字段或不支持版本会明确报错。模块工程记录资产、知识库和参数 schema 版本，原有无元数据的工程仍可读取。

当前知识库默认为 v3，来源、规则和地域配置分别存放；v1/v2 可显式读取。只有 `huizhou_core`（西递、宏村的村落级官方描述）和 `jiangnan_suzhou`（苏州古典园林的园林级官方描述）启用。其他候选地域为 `catalog_only`；未取得全文和定位的地方资料及对应规则标为待核查，并从普通查询中隐藏。当前资产清单仍为 v2，厅堂与直廊资产 v2 复用参数 schema v1 和现有方块生成器；相同输入的方块结果保持一致。知识规则按地域 ID 精确筛选，不推断地区层级，也不把描述性史料转换成未证实的尺寸。

可复现的三开间参数样例见 `examples/hall_v1_parameters.json`（参数 schema v1）。`bay_spacing` 映射到现有参数 `bay_width`；屋顶断面 v1 仅支持生成器当前实现的对称双坡。地域范围、来源核查等级和待核查记录见 [`docs/knowledge-regions.md`](docs/knowledge-regions.md)。用户 `.litematic` 只登记为视觉偏好参考，不作为历史证据。

## 三维预览与修改对比

`jiangnan preview` 调用 Mine2Blend 将 Sponge `.schem` 转成 OBJ，再用 Blender 后台渲染俯视、正面、侧面和透视图。需要本机安装 Mine2Blend 和 Blender；输出目录必须为空或尚不存在，程序不会覆盖已有预览。

```powershell
$mine2blend = "E:\MCbuild\Mine2Blend\mcblock_mine2blend"
$blender = "D:\SteamLibrary\steamapps\common\Blender\blender.exe"
jiangnan preview `
  --schematic workspace\exports\three_bay_hall-phase2.schem `
  --output-dir workspace\previews\hall-v1 `
  --mine2blend-root $mine2blend `
  --blender $blender
```

可增加 `--compare-before <旧版本.schem>` 同时渲染新旧版本，并生成 `comparison.json`，其中包含按方块状态计算的新增、删除、替换和变化数量。每次预览另生成 `preview.json`，记录输入、尺寸、工具版本、相机范围和图片位置。

## 模块组合示例

```powershell
python -m examples.two_courtyard
```

示例将三座厅堂、两段直廊和四面院墙保留为独立模块，通过门洞与边界锚点连接，校验后输出 `workspace\exports\two_courtyard.schem`。也可以在 Python 中调用 `build_two_courtyard()`，再用 `replace_corridor_roof()` 单独替换一段廊子的屋顶材料。此示例验证的是几何连接规则，不代表经过文献考证的营造方案。

## 开发与检查

```powershell
python -m pytest
```

GitHub Actions 在 Windows 和 Ubuntu、Python 3.12 上运行同一套 pytest。

## 目录

- `jiangnan_agent/core/`：方块、坐标、边界、稀疏方块模型和变换。
- `jiangnan_agent/assembly/`：模块锚点、平移/旋转/镜像、连接图、拆分/替换、冲突校验和组合渲染。
- `jiangnan_agent/io/`：工程 JSON 与 Sponge v3 读写。
- `jiangnan_agent/knowledge/`、`parameters/`、`assets/`：版本化知识规则、参数 schema 与模块资产清单。
- `jiangnan_agent/preview/`：Mine2Blend 转换、Blender 四视图渲染和方块差异报告。
- 工程编辑器保存完整组合快照、方块差异，并提供撤销/重做。
- `jiangnan_agent/generators/`：基础构件、参数化厅堂/直廊与简单房屋生成器。
- `tests/`：方块模型、工程 JSON、命令行、Sponge 文件和简单房屋测试。
- `docs/roadmap.md`：完整九阶段路线图。

当前工作已包括参数化构件、模块组合、工程历史、Codex 本地工具接入、版本化知识/参数/资产基础，以及 Mine2Blend/Blender 预览。知识查询仅返回有范围标记的规则，不会自动改变生成器。后续按路线图增加可验证的专业构件和更多地域来源。
