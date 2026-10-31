# GEN-3.1 Roof–Façade Visual Quality Gate

## 结论

GEN-3 原始 Blender 透视图中的檐口断带是真实生成缺口，不是 Mine2Blend 丢块或 Blender 材质显示差异。生成模型和原始 Sponge v3 投影在该处都没有方块：檐口边缘只到 y=6（江南）或 y=6（徽州），其上 y=7 是空气；相邻内侧屋面从 y=7 开始。楼梯的下半部覆盖该格的下半空间，不能填补外缘上半空间。GEN-3.1 对工程实例增加显式、可选的实心边缘衬层，并以屋面外缘上半砖与衬层衔接。

该修复已在本地 Windows 生成、Sponge v3 回读和 Mine2Blend/Blender 对比渲染中验证。Minecraft 1.21.5 + WorldEdit 实机粘贴仍为 **pending**。本报告不将视觉预览视为实机通过，也不据此启动 GEN-4。

## 原始输出复现及根因

来源是未修改的 GEN-3 运行 `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34`。先重新加载工程并生成原输出，再逐坐标比较模型与原 `.schem` 的完整 BlockState 映射；两栋的工程生成结果均与原始 `.schem` 完全相同。

### 江南三开间

生成器链路复核了 `generate_roof_surface()`、`generate_eaves_component()`、`generate_roof_components()` 和 hall 集成后的最终模型。正面边缘在 z=6，背面边缘在 z=0；x=0、7、15 截面取样结果相同：

| 位置 | 原始 BlockState | Minecraft 占格解释 |
|---|---|---|
| 前檐 `(x,6,6)` | `deepslate_tile_slab[type=bottom]` | 下半格实体 |
| 前檐 `(x,7,6)` | `air` | 缺失；可直接看到其后的梁/墙区域 |
| 前坡 `(x,7,5)` | `polished_deepslate_stairs[facing=north,half=bottom,shape=straight]` | 该格楼梯下半部有实体，但坡面台阶位于上半部并朝内 |
| 后檐 `(x,6,0)` | `deepslate_tile_slab[type=bottom]` | 下半格实体 |
| 后檐 `(x,7,0)` | `air` | 缺失 |
| 后坡 `(x,7,1)` | `polished_deepslate_stairs[facing=south,half=bottom,shape=straight]` | 坡面楼梯不占据檐口格的上半空间 |

这不是坡面层整体高低错位：相邻檐口下半砖和坡面楼梯的坐标符合旧生成参数，但没有覆盖檐口格上半部的连接构件。Mine2Blend 的原版楼梯模型在缺口格没有被输入，因此不是渲染器漏画。

### 徽州五开间

正面边缘 z=8、背面边缘 z=0；x=-1、12、26 取样一致：边缘 y=5 和 y=6 均为 `stone_brick_slab[type=bottom]`，y=7 为 `air`；内侧 z=7（前）/ z=1（后）的 y=7 是朝内的石砖楼梯。原配置的双层下半砖使檐口视觉更厚，但仍没有填充 y=7。此处同样是明确缺块，而不是楼梯/半砖实体模型或 Mine2Blend 造成的假缝。

完整的中部与端部截面（含坐标及 BlockState）由复现脚本输出为 CSV，见“可复核工件”。原始 `.schem` SHA-256 未改变，证明检查过程没有改写用户验收文件。

## 最小修复与示例比例

生成器新增 opt-in `eave_profile.surface_connection="edge_liner"` 与显式 `surface_connection_role`。仅正面/背面外缘使用声明的完整方块，屋面边缘使用上半砖覆盖其上半空间。校验拒绝非完整衬层材料、底半砖、非楼梯首道坡面、首段高度不为 1、衬层位置被檐口装饰占用等无效配置。所有权由檐口构件显式登记；没有规则地填墙、梁柱或山墙空间。

兼容性方面，默认值为 `legacy`。既有参数、默认 hall/corridor 生成结果和版本化屋顶预设不变；旧工程不配置该字段时不会生成衬层。三开间和五开间的原有示例版本仍保存在来源运行中，没有覆盖。

五开间示例另存实例级创作变体 `huizhou_roof_light_v2`，没有改写 `gray_brick_layered v1`：檐口从双层改为单层，侧出檐从 2 格减为 1 格，取消方形盖脊，保持 2 格屋脊升高并使用直线采样断面；另加石砖衬层。为回应立面平板感，候选示例把窗宽由 2 改为 3、格栅由竖格改为网格，并启用现有柱础、柱头强调。它是 Minecraft 创作示例，不是历史比例结论。透视图显示屋顶纵向厚度及檐口空带减轻，正面开间木构节奏更清楚；墙面仍保留重复灰砖面，是可见的后续审美项。

## 方块差异和导出

两栋都导出 DataVersion 4325 的 Sponge Schematic v3，并重新读取后比较完整坐标与 BlockState。差异按绝对坐标计算；`state_changed` 表示同一格状态改变，不表示新坐标。

| 示例 | 前→后尺寸 | 方块数前→后 | 新增 | 删除 | 状态改变 | unchanged | 修复版 SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---|
| 江南三开间 | 16×10×9 → 16×10×9 | 504→536 | 32 | 0 | 32 | 472 | `8FAFEC1A9FEBA7778228460FCF0D23CB40D8DED80531BA11AF45C68ACC52186B` |
| 徽州五开间 | 28×9×13 → 28×9×11 | 1048→1044 | 112 | 116 | 164 | 768 | `582E6C4B8C551887D62C819025D9CBC5D5E2BDA7A8C3AE89EC8F3B8B08EE1819` |

江南每侧 16 格共添加 32 个磨制深板岩衬层方块，并将前后檐各 16 个边缘下半砖改为上半砖。徽州候选使用石砖衬层，并以单层上半砖取代双层下半砖檐口；缩短的山墙端/侧出檐和移除的盖脊导致原有坐标被删除，报告中的净块数略减。梁柱和立面保留区没有被衬层覆盖；中部柱位处衬层保持连续。

## Blender 人工视觉复核

最新对比运行：`workspace/gen3-1-roof-visual-gate-20261031T053000000000Z-final-review`。使用 Mine2Blend `spike-0.1.1`、Blender `5.2.3 LTS`，生成两栋各 before/after 的 top、front、side、perspective 共 16 张图。人工逐张查看了两栋的正面、侧面、俯视和透视图：

- 两栋透视图的前后檐长条露空均已被连续衬层闭合；正面屋面下沿连续。俯视图可看到新衬层沿两条屋檐贯通。
- 江南屋顶预设其余参数保持原样；变化仅限两侧边缘半砖状态及 32 个衬层坐标。透视图中缺口消失，侧视的人字山墙阶梯轮廓仍保持原来的开放空腔。
- 徽州候选屋顶变薄、出檐缩短、取消盖脊后，立面占比更平衡，原贯穿空带消失。正面较宽网格窗、柱础和柱头使开间分段更清晰，但灰砖墙面纹理重复仍可见。侧视山墙内部仍有开放区域；该端部墙体填充没有列入本次檐口断带修复。
- 这些结论仅针对 Mine2Blend/Blender 的网格与材质预览。截图未能证明游戏内方块光照、相邻楼梯自动连接/模型及实际 WorldEdit 粘贴结果。

## Windows 自动化验证

在完成最终五开间实例视觉调整后执行：

- `.venv` Python 3.12.2；GEN-3.1 屋面/檐口与衔接形状专项：记录在 PR 关联 CI 与本地完整 pytest 结果中。
- 本地完整 Windows pytest：**482 passed**（Python 3.12.2，pytest 8.4.2，11.30 秒）；包含默认 hall/corridor 输出回归哈希及旧工程测试。
- MCP stdio 精确 CI 用例：**1 passed**；`import mcp` 成功，模块路径为 `.venv\Lib\site-packages\mcp`。
- `git diff --check`：通过。Git 仅提示文档 LF 将按仓库工作区配置转换为 CRLF，不是空白错误。
- Blender 真实渲染：两栋均完成；渲染报告记录 DataVersion 4325、Mine2Blend `spike-0.1.1`、Blender 5.2.3 LTS。
- Minecraft Java 1.21.5 / WorldEdit：**pending**。

## 可复核工件

运行目录保存原 `.schem` 的只读复现、实例配置、修复后工程/投影、方块差异及完整坐标截面 CSV、渲染清单与图像。原 GEN-3 运行和工件不会覆盖。

| 内容 | 江南三开间 | 徽州五开间 |
|---|---|---|
| 原工程/投影 | `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/projects/jiangnan-hall-3bay.jap.json` / `exports/jiangnan-hall-3bay.schem` | `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/projects/huizhou-hall-5bay.jap.json` / `exports/huizhou-hall-5bay.schem` |
| 对比预览目录 | `workspace/gen3-1-roof-visual-gate-20261031T053000000000Z-final-review/previews/jiangnan-hall-3bay/` | `workspace/gen3-1-roof-visual-gate-20261031T053000000000Z-final-review/previews/huizhou-hall-5bay/` |
| 前后截面 CSV | `workspace/gen3-1-roof-visual-gate-20261031T053000000000Z-final-review/sections/jiangnan-hall-3bay-{before,gen3-1-after}.csv` | `workspace/gen3-1-roof-visual-gate-20261031T053000000000Z-final-review/sections/huizhou-hall-5bay-{before,gen3-1-after}.csv` |
| 完整机器报告 | `workspace/gen3-1-roof-visual-gate-20261031T053000000000Z-final-review/visual-gate-report.json`（含两栋记录） | 同左 |

原始 `.schem` 哈希：江南 `FC9BE7F190AE27B82365F109432F8C95942E30A822EC79A75D8E1E6876551237`；徽州 `A8D535BD5BD75FDF46D6292F2454CABC8BB3EBC91625A8FCB90C9D711C98F045`。

## 下一步状态

PR #6 合并前必须有最终 Windows 全套测试、PR 必需 CI 通过、兼容性复核和这批最终预览文件复核。合入后保留 Minecraft/WorldEdit 实机验证为 pending。GEN-3.1 完成后停止，等待用户审查；不自动开始 GEN-4。
