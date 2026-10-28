# Jiangnan Architect Agent

本地运行的江南建筑生成项目，目标 Minecraft Java 1.21.5（DataVersion 4325）。当前完成项目初始化和方块数据引擎阶段：工程 JSON 可保存/加载，稀疏方块模型可生成并导出 Sponge Schematic v3 `.schem`。

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

## 生成第一栋简单房屋

```powershell
jiangnan generate --project workspace\projects\suzhou-hall.jap.json
```

默认生成到 `workspace\exports` 下的安全文件名 `.schem`。工程中的 `settings.building` 可调整 `width`、`length`、`wall_height`、`roof_overhang` 和方块材料。`.schem` 为 Sponge v3 gzip-NBT，可使用 WorldEdit 导入测试世界。不要让生成器直接写入已有 Minecraft 存档。

仓库内的示例工程：

```powershell
jiangnan validate examples\three_bay_house.jap.json
jiangnan generate --project examples\three_bay_house.jap.json
```

## 开发与检查

```powershell
python -m pytest
```

GitHub Actions 在 Windows 和 Ubuntu、Python 3.12 上运行同一套 pytest。

## 目录

- `jiangnan_agent/core/`：方块、坐标、边界、稀疏方块模型和变换。
- `jiangnan_agent/io/`：工程 JSON 与 Sponge v3 读写。
- `jiangnan_agent/generators/`：当前简单房屋生成器。
- `tests/`：方块模型、工程 JSON、命令行、Sponge 文件和简单房屋测试。
- `docs/roadmap.md`：完整九阶段路线图。

后续阶段按路线图逐步增加参数化构件、模块组合、工程历史、AI Agent、Blender 预览和知识库。
