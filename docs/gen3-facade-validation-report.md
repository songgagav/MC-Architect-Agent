# GEN-3 Façade & Openings v1 验收报告

## 范围与环境

- 目标：Minecraft Java 1.21.5，Sponge Schematic DataVersion 4325；尺度为 Minecraft 创作尺度。
- 平台：Windows 10/11 x64，Python 3.12。
- 预览：Mine2Blend `spike-0.1.1`、Blender `5.2.3 LTS`。
- 本次运行目录：`E:\MCbuild\workspace\gen3-facade-v1-20261030T180924043082Z-89a8ef34`。它是本机验收工件，不纳入 Git；示例生成器和本报告纳入版本控制。
- 游戏内放置：**pending**。未启动 Minecraft 或 WorldEdit，因此本报告不宣称游戏内通过。

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
| 江南三开间 | 正面入口居中，墙面、深色木构和台基层次可辨；俯视屋面连续。侧面可见人字山墙的阶梯轮廓，透视图中屋面分层与出檐较醒目。 | 渲染中未见立面构件互相覆盖或明显屋面缺块。屋顶层次较重，游戏内需复查楼梯方向与檐口接缝。 |
| 徽州五开间 | 正面主入口居中，两侧窗口与柱位成对；灰色屋面和深色收边形成强对比。透视图中屋顶占据较大视觉面积，山墙阶梯层次清楚。 | 入口错位已修正。渲染中未见明显墙柱冲突；需在游戏内确认屋面阶梯间隙及窗格朝向。 |
| 园林三开间 | 正面两侧窗扩大为 3×2，竖格之间可见玻璃区域，中心双门保持对称；透视图表现出木构窗洞。端面仍为封闭山墙。 | 正面比原始 2×2 交叉格窗更通透。它仍是厅堂式端墙，不代表完全敞开的亭廊；如需全开敞构架，需另行设计明确的结构开口类型。 |

三种屋顶的渲染均表现为清晰的阶梯分层；这属于 Mine2Blend/Blender 中观察到的轮廓，不足以证明 Minecraft 楼梯与半砖的游戏内连接状态正确。导出材料颜色和方块纹理在渲染器中可见；透明方块和部分方块模型可能与游戏内视觉不同。

## 自动化验证

Windows Python 3.12 本次结果：

- GEN-3 示例、开间联动、Schematic 回读及避免覆盖测试：通过。
- façade profile/geometry/components、厅堂和回廊、参数/资产注册、工程 JSON、编辑历史专项集合：**223 passed**。
- MCP stdio 客户端/服务端往返测试：**1 passed**。
- 完整 Windows pytest：**470 passed**。
- `git diff --check`：通过。

## 游戏内待验

在新建的独立 Minecraft Java 1.21.5 创造测试世界中，用匹配版本的 WorldEdit 分别粘贴三份 `.schem`。检查入口和窗格的朝向、开合、通行、楼梯/半砖状态、屋脊、檐口、屋面缺口与实体模型。将游戏版本、WorldEdit 版本、截图和任何问题记录在此后，再把状态从 `pending` 更新为实际结果。不要使用重要存档。

## 本地预览文件

每个建筑目录均含 `top.png`、`front.png`、`side.png`、`perspective.png` 和 `preview.json`。例如：

- `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/previews/jiangnan-hall-3bay/`
- `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/previews/huizhou-hall-5bay/`
- `workspace/gen3-facade-v1-20261030T180924043082Z-89a8ef34/previews/garden-hall-3bay/`
