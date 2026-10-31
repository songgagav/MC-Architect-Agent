# GEN-3 Façade & Openings v1 验收报告

## 范围与环境

- 目标：Minecraft Java 1.21.5，Sponge Schematic DataVersion 4325；尺度为 Minecraft 创作尺度。
- 平台：Windows 10/11 x64，Python 3.12。
- 预览：Mine2Blend `spike-0.1.1`、Blender `5.2.3 LTS`。
- 本次运行目录：`E:\MCbuild\workspace\gen3-facade-v1-20261030T180924043082Z-89a8ef34`。它是本机验收工件，不纳入 Git；示例生成器和本报告纳入版本控制。
- 游戏内放置：**pending**。未启动 Minecraft 或 WorldEdit，因此本报告不宣称游戏内通过。

**视觉问题更正（GEN-3.1，2026-10-31）：**原始 GEN-3 江南三开间和徽州五开间投影确有檐口边缘缺块。本报告下方早先“渲染中未见明显屋面缺块”的记录已被后续逐坐标检查纠正；请以 [GEN-3.1 屋面—立面视觉质量门报告](gen3-1-roof-visual-quality-gate.md) 及其前后对照工件为准。GEN-3.1 Blender 复核认为两例修复版的檐口断带已闭合；Minecraft/WorldEdit 实机仍为 pending。

生成器在保存每个投影后重新读取 Sponge v3 文件，并比较完整坐标与 BlockState 映射；三份回读结果均与生成模型相同。预览清单均记录 DataVersion 4325、Mine2Blend 与 Blender 版本及四个视图路径。

## 三组建筑与导出校验

| 示例 | 立面预设 / 屋顶预设 | 开间 | 尺寸 X×Y×Z | 方块数 | `.schem` SHA-256 |
|---|---|---:|---:|---:|---|
| `jiangnan-hall-3bay` | `jiangnan_whitewall_timber` / `jiangnan_dark_tile` | 3 | 16×10×9 | 504 | `FC9BE7F190AE27B82365F109432F8C95942E30A822EC79A75D8E1E6876551237` |
| `huizhou-hall-5bay` | `huizhou_graybrick_entry` / `gray_brick_layered` | 5 | 28×9×13 | 1048 | `A8D535BD5BD75FDF46D6292F2454CABC8BB3EBC91625A8FCB90C9D711C98F045` |
| `garden-hall-3bay` | `garden_open_gallery` / `warm_spruce_garden` | 3 | 18×8×9 | 522 | `446185C205821AAB41A0CFDB75EE59F587073B934FE177A9D985FFB97C348EBD` |

五开间样例把 `primary_entry` 放在中心开间，左右窗对称放在相邻开间。园林样例在工程实例内把正面窗调整为 3×2 竖格窗，并移除两个侧窗，以突出开敞感；这一覆盖保存在工程设置中，未更改已登记的 `garden_open_gallery` 预设版本。所有例子将当前主门写入稳定的 `main-entry` ID；锚点从该声明生成，没有扫描其他门方块。

## 人工视觉审核

已逐一打开并检查三组建筑的俯视、正面、侧面和透视共 12 张实际渲染图。以下是对渲染画面的人工观察，不替代方块在 Minecraft 中的实际模型和光照检查。

| 建筑 | 视觉检查记录 | 审核意见 |
|---|---|---|
| 江南三开间 | GEN-3.1 对原始投影逐坐标复核发现前后檐各有一行缺块；GEN-3.1 实例变体以檐口上半砖和显式实心衬层闭合。 | 原记录中“未见明显屋面缺块”已纠正。修复版 Blender 四视图通过本地人工复核；游戏内接缝仍待验。 |
| 徽州五开间 | GEN-3.1 确认原屋檐外缘有连续缺块带，屋顶占比偏重；实例变体减薄檐口、缩短出檐、移除盖脊并使用显式衬层。 | 原记录中“未见明显屋面缺块”已纠正。修复版 Blender 四视图显示断带闭合、比例更轻；灰砖墙面纹理重复仍可见，游戏内接缝仍待验。 |
| 园林三开间 | 正面两侧窗扩大为 3×2，竖格之间可见玻璃区域，中心双门保持对称；透视图表现出木构窗洞。端面仍为封闭山墙。 | 正面比原始 2×2 交叉格窗更通透。它仍是厅堂式端墙，不代表完全敞开的亭廊；如需全开敞构架，需另行设计明确的结构开口类型。 |

三种屋顶的渲染均表现为清晰的阶梯分层；这属于 Mine2Blend/Blender 中观察到的轮廓，不足以证明 Minecraft 楼梯与半砖的游戏内连接状态正确。导出材料颜色和方块纹理在渲染器中可见；透明方块和部分方块模型可能与游戏内视觉不同。

## 自动化验证

Windows Python 3.12 本次结果：

- GEN-3 示例、开间联动、Schematic 回读及避免覆盖测试：通过。
- façade profile/geometry/components、厅堂和回廊、参数/资产注册、工程 JSON、编辑历史专项集合：**228 passed**。
- MCP stdio 客户端/服务端往返测试：**1 passed**。
- 完整 Windows pytest：**475 passed**。
- `git diff --check`：通过。

## 游戏内待验

在新建的独立 Minecraft Java 1.21.5 创造测试世界中，用匹配版本的 WorldEdit 分别粘贴三份 `.schem`。检查入口和窗格的朝向、开合、通行、楼梯/半砖状态、屋脊、檐口、屋面缺口与实体模型。将游戏版本、WorldEdit 版本、截图和任何问题记录在此后，再把状态从 `pending` 更新为实际结果。不要使用重要存档。

## 当前参数边界与后续建议

- 走廊会在参数解析时拒绝向内加厚后剩余净宽小于 1 格的配置。回归覆盖单侧和双侧内墙、向外墙及不封闭墙面；宽度 5、两侧各 2 层墙仍留有 1 格通道，`start`/`end` 锚点保持原位。
- `WindowProfile.sill_height` 为 v1 JSON 兼容字段，目前不生成窗台方块，也不移动窗口；窗口垂直位置由单个开口的 `FacadeOpening.sill_offset` 控制。后续若要参数化窗台，应新增有明确材料与占格规则的构件，而非改变此字段的既有含义。
- 五开间徽州原始屋面偏重问题已在 GEN-3.1 的新示例配置中调整；旧风格预设保持原版。楼梯/半砖接缝、玻璃/栏杆方块的实际游戏模型仍需在 Minecraft 1.21.5 复查。

## 本地预览文件

每个建筑目录均含 `top.png`、`front.png`、`side.png`、`perspective.png` 和 `preview.json`。例如：

- `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/previews/jiangnan-hall-3bay/`
- `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/previews/huizhou-hall-5bay/`
- `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/previews/garden-hall-3bay/`
