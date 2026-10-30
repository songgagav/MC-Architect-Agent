# GEN-2 Roof & Eaves v2 收尾审查

## 运行记录

- 工件目录：`workspace/gen2-roof-closeout-20261030T162923770910Z/`
- 生成方式：三开间 hall、`HallParameters`、版本化屋顶预设、`hall_module`、项目 JSON 与 Sponge Schematic v3。
- Minecraft DataVersion：4325（Minecraft Java 1.21.5）。
- 预览工具：Mine2Blend converter `spike-0.1.1`，资源 `mcmeta-2026-02-26-copy`；Blender `5.2.3 LTS`。
- 输出：3 个可重新打开的 `.jap.json` 工程、3 个 `.schem` 文件、12 张 1200×900 PNG 和每组预览报告。
- 回读：三份 Schematic 均以 DataVersion 4325 成功读取。方块图在按 Sponge Offset 恢复到原始局部坐标后，与已保存工程生成的模型逐方块一致；测试覆盖了工程重新打开、DataVersion、Offset 和方块状态。

## 实际生成数据

| 屋顶预设 | 方块数 | 尺寸 X×Y×Z | Schematic Offset | DataVersion | Schematic SHA-256 |
|---|---:|---:|---|---:|---|
| `jiangnan_dark_tile` v1 | 504 | 16×10×9 | `(0, 0, -1)` | 4325 | `cc48804833048d18dc08d3f47011959daecdc310fc2075e1c77a61b7a670aff9` |
| `gray_brick_layered` v1 | 562 | 18×9×11 | `(-1, 0, -2)` | 4325 | `19b99fc519d4964ae24681abd45c02cfef136d74d793934110e7dc4926202938` |
| `warm_spruce_garden` v1 | 522 | 18×8×9 | `(-1, 0, -1)` | 4325 | `6173d2e7390f76d754f2dbb1a8f42fbf7ed3ac73fe702e85e07a43583da4d6db` |

## 四视图视觉审查

已逐张检查三组预览的 `top`、`front`、`side`、`perspective`，共 12 张。

| 预设 | 观察结果 |
|---|---|
| `jiangnan_dark_tile` | 屋面坡线对称，深色屋面与单层檐口区分清楚；正面柱、梁和门的位置连贯。透视图可见阶梯方块的分层边线，未见明显缺块或檐口脱离。 |
| `gray_brick_layered` | 厚檐和灰砖屋面层次最强；侧视能读出屋脊平台和两侧坡面，透视层叠感较重但与预设的双层檐口、平台断面一致。未见明显开洞或柱梁断接。 |
| `warm_spruce_garden` | 低坡度、无独立盖脊、宽木檐表达为轻型园林屋面；整体较平缓，木色占比高。该外观符合所设参数，未见明显几何缺口。 |

以上只代表 Blender 图像中的视觉检查，不替代 Minecraft 方块碰撞、状态或实际放置检查。阶梯和半砖的游戏内接合效果仍需实机确认。

## 验收边界

- Windows 本机 Mine2Blend 与 Blender 后台渲染：通过；12 张图片和 3 份 `preview.json` 均已生成。
- 项目保存/重载和 Schematic v3 回读：自动化测试通过，方块状态及 Offset 对应一致。
- Minecraft Java 1.21.5、WorldEdit 加载/粘贴/回读：**pending**；本次未启动游戏，也未修改任何世界存档。
