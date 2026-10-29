# Windows 10/11 验收步骤

正式运行和交付平台为 Windows 10/11 x64、Python 3.12；Minecraft 目标固定为 Java 1.21.5（DataVersion 4325）。Ubuntu GitHub Actions 仅作非阻塞兼容检查。

## 自动化验收

在项目 PowerShell 中：

```powershell
cd E:\MCbuild
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_mcp_server.py::test_mcp_stdio_lists_strict_tools_and_creates_a_project_module
.\.venv\Scripts\python.exe -m pytest -q
```

完整测试包含 MCP stdio 客户端/服务端往返、Schematic 写入与回读、参数和资产版本兼容、生成确定性、Assembly 优先级、路径越界、Windows Extended Path、BlockState 方向旋转/镜像、README fixture 等。GitHub Actions 必需项为 `Windows tests (required)`；`Ubuntu compatibility (non-blocking)` 不决定 Windows 交付是否通过。CI 显式启用 UTF-8，避免中文输出依赖 Windows 当前代码页。

## Codex 本地 MCP 验收

先安装并运行协议测试。若本机尚未注册此服务，再执行：

```powershell
codex mcp add jiangnan-architect -- "E:\MCbuild\.venv\Scripts\python.exe" -m jiangnan_agent.agent_tools.mcp_server --workspace-root "E:\MCbuild"
codex mcp list
```

重新加载 Codex 后，在新对话中依次要求它创建独立测试工程（例如 `mcp-acceptance.jap.json`）、添加三开间 hall、运行装配检查并导出新的 `.schem`。确认工具结果中的工程和导出路径都位于 `E:\MCbuild\workspace\`，且没有触碰其他工程或 Minecraft 存档。

自动化 MCP stdio 集成测试运行成功，证明 MCP 协议、工具 schema 和本地服务调用可用。本机 `codex mcp list` 显示 `jiangnan-architect` 已注册且为 `enabled`；**本次修订未重配该用户设置，也未重新执行桌面端新对话的交互式工具调用握手**，因此该 UI 层握手仍需单独确认。

## Mine2Blend 与 Blender 实机预览

下面的 PowerShell 脚本生成新的 asset v3 hall 工程、Sponge v3 `.schem`，再运行本机 Mine2Blend 与 Blender。每次使用不同时间戳，避免覆盖既有文件：

```powershell
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$projectPath = "workspace/projects/phase7-$runId.jap.json"
$schematicPath = "workspace/exports/phase7-$runId.schem"
$previewPath = "workspace/previews/phase7-$runId"

@"
from pathlib import Path
from jiangnan_agent.assembly.model import Assembly
from jiangnan_agent.assets import module_from_asset
from jiangnan_agent.io.project_json import JiangnanProject, save_project

project = JiangnanProject(
    name="Phase 7 Windows acceptance",
    assembly=Assembly((module_from_asset("hall-main", "jiangnan.hall", {"bay_count": 3}),)),
)
save_project(project, Path(r"$projectPath"))
"@ | .\.venv\Scripts\python.exe -

.\.venv\Scripts\jiangnan.exe generate --project $projectPath --output $schematicPath
.\.venv\Scripts\jiangnan.exe preview `
  --schematic $schematicPath `
  --output-dir $previewPath `
  --mine2blend-root "E:\MCbuild\Mine2Blend\mcblock_mine2blend" `
  --blender "D:\SteamLibrary\steamapps\common\Blender\blender.exe"
```

验收时应检查 `preview.json` 记录 DataVersion、方块数、Mine2Blend/Blender 版本，并确认 `top.png`、`front.png`、`side.png`、`perspective.png` 均可打开。

本次已在本机使用 asset v3 生成 522 方块的 `18 × 10 × 9` hall，并由 Mine2Blend `spike-0.1.1` 与 Blender 5.2.3 LTS 产生四张视图。未加入仓库的复现工件位于 `workspace/exports/windows_acceptance_phase7.schem` 和 `workspace/previews/windows_acceptance_phase7/`。

## Minecraft 1.21.5 与 WorldEdit 实机验收

**状态：待实机验证。** 本任务没有启动 Minecraft/WorldEdit，也没有声称 Schematic 已通过游戏内验收。WorldEdit 官方命令文档说明可用 `//schem load` 载入剪贴板、`//paste -a` 跳过空气方块；独立安装的配置路径通常为 `config/worldedit/schematics`，服务端则通常为 `plugins/WorldEdit/schematics`。以实际安装平台的配置为准。[WorldEdit 命令](https://worldedit.enginehub.org/en/latest/commands/)、[WorldEdit Clipboard 与 Schematic](https://worldedit.enginehub.org/en/latest/usage/clipboard/)

1. 安装与 Minecraft Java 1.21.5 匹配的 WorldEdit，在新建的独立创造模式测试世界中操作；不要使用重要存档。
2. 将生成文件复制到该 WorldEdit 实例的 schematics 目录。使用本次工件时文件名为 `windows_acceptance_phase7.schem`。
3. 进入空旷区域，执行 `//schem load windows_acceptance_phase7.schem`，确认 WorldEdit 接受 Sponge 文件并显示正确尺寸。
4. 在安全空地执行 `//paste -as`（`-a` 跳过空气，`-s` 选择粘贴区域）。检查朝向、门的开合/铰链、楼梯与半砖方向、窗格、屋檐接缝、室内通行和屋顶缺口。
5. 用选区 `//copy` 后执行 `//schem save windows_acceptance_phase7-roundtrip`，再于另一处空地加载并粘贴回读文件。记录截图、游戏/WorldEdit 版本、粘贴尺寸和方块状态检查结果；若失败，先隔离问题方块状态，再决定是否调整转换器。

在完成以上游戏内检查并保存复现记录之前，Minecraft/WorldEdit 门槛保持 `pending`。本地导出回读测试和 Blender 预览不能替代游戏内放置验证。
