# Roof & Eaves v2：参数化屋顶与檐口

Roof & Eaves v2 扩展现有 hall 和 corridor 生成器，不替换它们。当前保留对称双坡屋顶，可配置屋面断面、檐口、屋脊和方块材料。原有厅堂、回廊默认输出保持兼容。设计按 Minecraft 方块视觉效果调整，约以 1 方块表达 1 米；参数不是历史测绘尺寸或传统营造标准。

## 参数组

| 字段 | 用途 | 主要约束 |
| --- | --- | --- |
| `roof_profile` | 屋脊高度、归一化半坡断面、屋面材料分段 | 屋脊高度为正整数。断面点是千分比整数，从 `(0, 0)` 开始并以 `(1000, 1000)` 结束；水平值严格递增，高度不下降。按建筑实际半跨采样后必须适配建筑宽度，相邻方块高度不能跳跃超过 1 格。材料分段必须无间隙覆盖整个断面。 |
| `eave_profile` | 两侧出檐、山墙端处理、分层收边和可选重复装饰 | `hard_gable` 要求山墙端出檐为 0；`overhanging_gable` 要求正出檐。收边材料层数必须等于檐口厚度。重复装饰位于檐口基准线上方 1 格，避免占用墙体或梁端。 |
| `ridge_profile` | 可选屋脊盖脊和重复装饰 | 禁用盖脊时宽、高均为 0；启用后宽度必须为正奇数，高度为正整数。 |
| `material_palette` | 将语义材料角色映射为完整 Minecraft BlockState | 方块状态会解析校验。拒绝空气状态，因为当前 VoxelModel 会把空气解释为删除方块。断面可引用自定义材料角色，例如 `ridge`、`roof_slab`。 |

屋面材料分段支持 `stair`（楼梯）、`slab`（半砖）和 `full_block`（完整方块）。每个分段引用 `material_palette` 中的角色，可组合多种屋面形态与材料。楼梯和半砖由生成器按形态补齐朝向及上下半部状态；`full_block` 使用 Minecraft 1.21.5 的已登记整块材质族，并拒绝玻璃板、栏杆、门、火把等已知非整块形态，以及无法核验的非原版命名空间方块。可识别范围需随新材料逐步扩展。材料使用完整方块状态，例如：

```text
minecraft:stone_brick_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]
minecraft:stone_brick_slab[type=bottom,waterlogged=false]
```

楼梯和半砖朝向经由现有 BlockState 变换处理；遇到不支持的方向状态时明确报错，不会静默损坏。当前只支持对称双坡屋顶与硬山、悬挑山墙端处理。歇山、攒尖和复杂组合屋顶不在本版本范围内。

## Minecraft 创作预设

版本化定义存放在 `jiangnan_agent/parameters/v3/roof_profiles.json`，Python API 位于 `jiangnan_agent.parameters`。

| 预设 ID | 视觉参数 | 材料组合 |
| --- | --- | --- |
| `jiangnan_dark_tile` | 屋脊抬高 3 格；直线对称断面；两侧出檐 1 格；硬山；屋脊盖脊 1 格 | 深板岩瓦楼梯、深板岩瓦半砖、磨制深板岩屋脊 |
| `gray_brick_layered` | 屋脊抬高 2 格；中段抬升断面；两侧出檐 2 格；双层檐口；悬挑山墙；屋脊盖脊 1 格 | 石砖楼梯、石砖半砖、錾制石砖 |
| `warm_spruce_garden` | 屋脊抬高 1 格；两侧及山墙端出檐 1 格；悬挑山墙；无盖脊 | 云杉楼梯、云杉半砖、云杉木板 |

这些是 Minecraft 创作配置。预设名称仅为视觉风格标签，不代表已经核实的地域归属或历史构造。可以在加载后调整参数，也可以和其他模块参数组合。

## 创建并生成一座使用预设的厅堂

先在现有 Python 3.12 虚拟环境安装项目。下面的 PowerShell 示例用一个预设创建版本化厅堂模块，保存可编辑工程，然后通过现有命令行导出 `.schem`：

```powershell
@'
from dataclasses import asdict
from pathlib import Path

from jiangnan_agent.assembly import Assembly
from jiangnan_agent.assets import module_from_asset
from jiangnan_agent.io import JiangnanProject, save_project
from jiangnan_agent.parameters import load_roof_preset

preset = load_roof_preset("jiangnan_dark_tile")
parameters = {
    "bay_count": 3,
    "roof_profile": asdict(preset.roof_profile),
    "eave_profile": asdict(preset.eave_profile),
    "ridge_profile": asdict(preset.ridge_profile),
    "material_palette": dict(preset.material_palette.roles),
}
module = module_from_asset("hall-main", "jiangnan.hall", parameters)
project = JiangnanProject(name="Dark tile hall", assembly=Assembly((module,)))
destination = Path("workspace/projects/dark-tile-hall.jap.json")
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    raise FileExistsError(destination)
save_project(project, destination)
'@ | .\.venv\Scripts\python.exe -

jiangnan validate workspace\projects\dark-tile-hall.jap.json
New-Item -ItemType Directory -Force workspace\exports | Out-Null
if (Test-Path workspace\exports\dark-tile-hall.schem) { throw "Choose a new schematic output filename." }
jiangnan generate --project workspace\projects\dark-tile-hall.jap.json `
  --output workspace\exports\dark-tile-hall.schem
```

命令会生成 Sponge Schematic v3。需要重新生成时，请选择一个新输出文件名，避免覆盖之前保留的结果。Assembly 只要含有模块，就优先用于生成；Assembly 无效时直接报错，不回退到旧工程设置。Profile 参数保存在工程 JSON 中，并可继续通过 `ProjectEditor` 修改、撤销和重做。

## 旧参数兼容与冲突

现有 schema v3 资产继续接受以下旧字段，并归一化到新参数：

- `roof_rise`、`roof_section.rise` → `roof_profile.ridge_height`
- `eaves` → 两侧出檐、山墙端出檐和端部处理方式
- `materials.roof`、`materials.eaves` → `material_palette` 对应角色

旧的 `roof_section` 对象只有在指定 `profile: "symmetric_gable"` 时才接受。

同时提供旧字段和规范 Profile 字段时，归一化后的值相同则接受；值冲突会抛出 `ParameterConflictError`。解析器不会静默选择其中一个。新工程建议直接使用规范 Profile 字段。

## 验证范围

自动化测试覆盖断面确定性、构件接缝与所有权、方块材料状态、hall/corridor 默认兼容、方向变换和 Sponge Schematic 写入/回读。Python 测试通过不代表已检查 Minecraft 中的实际观感。请在 Minecraft Java 1.21.5 的独立测试世界中用 WorldEdit 导入 `.schem`，检查放置结果与视觉效果。Mine2Blend/Blender 渲染是独立预览流程，需要单独运行。生成器不会写入现有 Minecraft 世界存档。
