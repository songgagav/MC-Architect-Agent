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

Python API 可按模块 ID 重新生成厅堂或直廊，记录方块差异，并在工程中保留撤销/重做快照：

```python
from jiangnan_agent.io import ProjectEditor, load_project, save_project

project = load_project("workspace/projects/suzhou-hall.jap.json")
ProjectEditor(project).regenerate_module("hall-main", {"bay_count": 5}, "调整为五开间")
save_project(project, "workspace/projects/suzhou-hall.jap.json")
```

## 生成建筑

```powershell
jiangnan generate --project workspace\projects\suzhou-hall.jap.json
```

默认生成到 `workspace\exports` 下的安全文件名 `.schem`。`simple_house` 可调整 `width`、`length`、`wall_height`、`roof_overhang` 和方块材料。`.schem` 为 Sponge v3 gzip-NBT，可使用 WorldEdit 导入测试世界。不要让生成器直接写入已有 Minecraft 存档。

仓库内的示例工程：

```powershell
jiangnan validate examples\three_bay_house.jap.json
jiangnan generate --project examples\three_bay_house.jap.json
jiangnan validate examples\three_bay_hall.jap.json
jiangnan generate --project examples\three_bay_hall.jap.json
```

`hall` 工程可调 `bay_count`（奇数开间）、`bay_width`、`depth`、`column_height`、`plinth_height`、`roof_rise`、`eaves`、`door_width` 和 `materials`。生成器会按参数同步调整柱网、梁、墙、门窗、台基、檐口和屋顶。

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
- 工程编辑器保存完整组合快照、方块差异，并提供撤销/重做。
- `jiangnan_agent/generators/`：基础构件、参数化厅堂/直廊与简单房屋生成器。
- `tests/`：方块模型、工程 JSON、命令行、Sponge 文件和简单房屋测试。
- `docs/roadmap.md`：完整九阶段路线图。

后续阶段按路线图逐步增加参数化构件、模块组合、工程历史、AI Agent、Blender 预览和知识库。
