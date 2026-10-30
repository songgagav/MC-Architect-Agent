# MC-Architect-Agent GEN-2：Roof & Eaves v2 设计

**状态：**用户已批准，实施完成，待正确基线复审。
**目标平台：**Windows 10/11 x64、Python 3.12、Minecraft Java 1.21.5 / DataVersion 4325。

## 意图

在现有参数化厅堂和回廊上扩展双坡屋顶表现，将屋面、檐口和屋脊拆成可组合、可独立配置的构件。设计优先考虑 Minecraft 中的轮廓、层次和材料协调；默认方块结果保持不变，不宣称历史尺寸或形制已获考证。

## 当前实现依据

- `generate_gable_roof(width, depth, base_y, rise, eaves, material)` 在 `generators/components.py` 生成对称楼梯坡面；檐口由独立 `generate_eaves` 生成。
- `generate_hall` 与 `generate_corridor` 直接组合这两个构件；它们的参数和材料可覆盖，既有 Assembly、ProjectEditor、历史记录、Schematic 和 MCP 都依赖这条路径。
- 参数 schema 当前为 v2；资源注册表快照为 v3，hall/corridor 的当前资产版本也为 v3。schema 已包含旧字段 `roof_rise`、`eaves`、`materials` 的映射。
- DB-2 参考投影尚无已核验语义构件，自动标注仍为 candidate；因此不把投影猜测转换成屋顶模板或营造依据。
- 旧默认模型的确定性基线：hall 522 个方块，bounds `min=(-1,0,-1), max-exclusive=(17,10,8)`，排序方块记录 SHA-256 `af86496dad80003d609d31a98e24a50957da419d32ca39a9ca622e8e61bc41b3`；corridor 150 个方块，bounds `min=(-1,0,-1), max-exclusive=(12,7,4)`，SHA-256 `6b99402a56bb31b35e6209d64a8ac4f4f83b3b452171ea53a39bd6b1aef0d707`。哈希输入按坐标 `(x,y,z)` 排序，每行编码为 `x,y,z:<BlockState>\n` 后取 UTF-8 SHA-256。

## 目标

1. 将屋面主体、檐口、屋脊作为独立的确定性 `VoxelModel` 构件生成和组合，复用当前屋顶算法及方块模型；保留现有 `generate_gable_roof` 调用兼容层。
2. 通过 `roof_profile` 控制双坡断面及屋脊升高量，并用无重叠的 `surface_bands` 将屋面区段映射到材料 palette 的楼梯、半砖或整块角色；通过 `eave_profile` 控制檐口伸出量、厚度、分层收边和装饰；通过 `ridge_profile` 控制屋脊盖脊宽度、材料和装饰。屋面层次按断面带、檐口收边和屋脊盖脊分配，不在同一坐标叠放互相覆盖的方块。
3. 将断面输入表达为整数千分比控制点（檐口到屋脊的水平比例/高度比例），默认直线断面；控制点坐标在 0–1000 范围，水平值严格递增、高度值不下降，端点为 `[0,0]` 和 `[1000,1000]`。对每个实际半跨格位 `i` 使用精确有理数 `t=i*1000/half_run`，在 `t` 所属控制点线段上插值高度，再乘以屋脊升高量，最终仅对块高四舍五入（正好半格时向上）；全程不先量化 `t`，且不用浮点数。展开后的高度从 0 开始、到屋脊升高量结束、单步变化为 0 或 1；若结果不满足就拒绝 profile，不做静默修形，再沿进深镜像。hall 的开间宽度改变屋脊长度，hall 进深或 corridor 宽度改变断面半跨，柱高平移屋面基准，屋脊升高量改变峰顶位置；无法在当前尺寸满足规则时显式报错。
4. 仅扩展双坡主体，提供两种端部处理：`hard_gable`（山墙端不外挑）和 `overhanging_gable`（沿屋脊方向按参数外挑）。檐口方向的出檐独立控制。几何标签是本项目的 Minecraft 表达配置，不作为历史鉴定。
5. 提供至少三个版本化 Minecraft 创作预设：深色瓦面、灰色石材、木色屋面。每个预设明确写出轮廓、檐口/屋脊层次和材料角色；材料只使用当前项目解析器可读取的方块状态，不暗示其来自历史测绘。
6. 新 hall/corridor 参数资源增加 `roof_profile`、`eave_profile`、`ridge_profile`、`material_palette`。参数 schema 升至 v3；hall/corridor 资产及注册表快照升至 v4。旧 v1/v2 schema、v1-v3 资产和已有工程参数继续可读，旧字段映射不产生歧义。

## 创作预设（提案）

以下都是本项目的 Minecraft 方块方案，不是历史测绘结论。升高量按檐口屋面基准向上计块；`section` 的端点使用整数千分比。材料使用现有解析器支持的 BlockState 字符串。

| profile_id | 屋面断面与脊升高 | 端部 / 檐口 | 屋脊 | 材料角色 |
| --- | --- | --- | --- | --- |
| `jiangnan_dark_tile` | `[[0,0],[1000,1000]]`，升高 3 | 硬山；檐口外挑 1、厚 1；檐口收边 1 层 | 盖脊宽 1、盖脊高 1 | 屋面 `minecraft:polished_deepslate_stairs`；檐口 `minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]`；屋脊 `minecraft:polished_deepslate`；装饰无 |
| `gray_brick_layered` | `[[0,0],[333,500],[667,500],[1000,1000]]`，升高 2 | 悬山端外挑 1；檐口外挑 2、厚 2；两层收边 | 盖脊宽 1、盖脊高 1 | 屋面 `minecraft:stone_brick_stairs`；檐口 `minecraft:stone_brick_slab[type=bottom,waterlogged=false]`；屋脊 `minecraft:chiseled_stone_bricks`；装饰无 |
| `warm_spruce_garden` | `[[0,0],[1000,1000]]`，升高 1 | 悬山端外挑 1；檐口外挑 1、厚 1；单层收边 | 盖脊关闭（宽 0、高 0） | 屋面 `minecraft:spruce_stairs`；檐口 `minecraft:spruce_slab[type=bottom,waterlogged=false]`；屋脊 `minecraft:spruce_planks`；装饰无 |

预设参数来源登记为 `minecraft_adaptation` / Minecraft 创作配置，不关联未经核验的历史测绘来源。预设可在 schema 几何边界内覆盖断面、尺寸和材料；生成器仍负责校验各方块的合法状态与方向。`jiangnan_dark_tile` 升高 3，适用半跨至少 3 格；`gray_brick_layered` 升高 2，适用半跨至少 2 格；`warm_spruce_garden` 升高 1，适用半跨至少 1 格，可用于默认宽度回廊。默认 corridor 的半跨为 1，前两个预设必须降低升高量后才能用于该断面；无法满足的配置要报错。默认 hall/corridor 的 legacy `eaves=1` 等效于横向与山墙端各外挑 1 格，故默认端部效果是外挑型；新显式 profile 未指定时，不自动套用表中的任一创作预设，以保留当前输出。

`surface_bands` 按从檐口到屋脊的 `[start,end)` 千分比区间映射 `stair`、`slab`、`full_block` 形状及对应 palette 角色；区间连续无缝，最后一带包含屋脊端点 1000，即最后一带采用 `[start,1000]`。楼梯统一由生成器写入正确 facing、bottom half、straight shape、`waterlogged=false`；屋面半砖使用 top half 以对齐完整屋面高度，檐口半砖则沿用 palette 给出的明确状态；整块不附加方向属性。参数解析和生成均使用项目维护的 Minecraft Java 1.21.5 建筑材质子集校验方块 ID 和已登记属性，旧 schema 的 `materials.roof/eaves` 也在解析时校验；此子集不是游戏完整方块注册表，未知 ID、命名空间或状态属性会明确拒绝。`full_block` 只接受登记为整块的材质或 `type=double` 的半砖；盖脊主体使用整块材质或双层半砖。相邻坡面高度变化一级且包含整块或半砖表面时，补入连接方块；半砖过渡使用双层半砖，避免只在棱角接触的空隙。默认值为全区间楼梯面、现有半砖檐口、关闭独立盖脊，确保旧输出不变。檐口装饰放在檐口基准线上方一格，不占用支撑墙体或梁端；屋脊装饰使用屋脊 Profile 定义的位置。

## 兼容性与硬约束

- 默认双坡 profile 必须与当前默认 hall/corridor 逐方块相同，以上记录哈希用于回归测试。保留 `bay_width`、`roof_rise`、`eaves`、`materials` 等已接受输入和原生成器签名。
- 默认 ridge profile 不新增盖脊方块，峰顶继续由现有屋面方块形成；只有显式启用新盖脊层时才改变方块结果。启用盖脊后，盖脊构件声明拥有其覆盖区，屋面构件跳过同一坐标。旧 `eaves` 同时映射到横向檐口外挑与山墙端外挑，以保持当前布局。
- 旧输入映射：`roof_rise` / `roof_section.rise` → `roof_profile.ridge_height`；`eaves` → `eave_profile.side_overhang` 与 `eave_profile.gable_end_projection`；`materials.roof` / `materials.eaves` → 对应 palette 角色。只给旧字段时先扩展为新 canonical 值；只给新 profile 时使用新值；旧字段和新字段同时显式给出时，归一化后相同则接受、不同则报参数冲突。兼容的 Python 参数类在补默认值前区分“省略”和“显式传入”，构造完成后 `HallParameters()` / `CorridorParameters()` 仍暴露现有默认值。旧工程无须写入新字段。
- `eave_profile.thickness` 定义为从檐口基准向下的方块层数；多层檐口可以覆盖其设计接口上的梁端，覆盖属于登记的连接，不得扩散到其他屋面/墙体方块。`ridge_profile.cap_height=0` 表示关闭盖脊；大于零时盖脊从屋脊中心面向上叠放，底层只替换中心屋面块，顶层为新增层。盖脊宽度按横断面中心对称，必须为正奇数或在关闭时为 0。
- 构件采用显式占格所有权，避免靠合并顺序静默覆盖：若檐口有位于屋面基准面的边缘层，则檐口构件拥有 `z=0` 和 `z=depth-1` 的边界格（含已配置的山墙端外挑范围），屋面主体跳过这些格；若没有该层，则屋面主体保留边界格。若启用盖脊，其声明的中心带由盖脊拥有，屋面主体同样跳过相同格。檐口与梁端只允许上述声明连接；屋顶组合到 hall/corridor 主体时也只允许这些梁端接口坐标重叠，其他重叠都报几何冲突。默认所有权分区必须仍生成旧默认哈希。
- 方块状态必须按形状设置：楼梯方向、半砖类型、`waterlogged` 等状态需正确；整块方块不附带不支持的方向属性。旋转时依赖现有状态转换规则；不支持的状态必须报错，不得静默变形。
- 派生几何不得超出硬约束：坡面完整、屋脊连续、檐口与坡面连接、构件之间无意外覆盖；遇到不兼容的宽度/进深/profile 组合明确失败。
- 回廊 schema v3 的 `bounds_width` / `bounds_depth` 按长度、宽度和相应檐口投影派生；v1/v2 解析行为保持不变。
- 只增加参数和资源版本，不提升项目 JSON 格式，不改变 Assembly 优先生成规则、工程历史、MCP 工具、Schematic v3 输出或用户存档保护逻辑。
- 任何风格软建议都允许用户覆盖；用户输入仍须满足几何、BlockState 及导出约束。

## 实现方式与取舍

### 方案 A：类型化 profile + 现有生成器上的纯构件函数（选用）

保留现有 `HallParameters` / `CorridorParameters` 与 `VoxelModel` 组合路径，补充明确类型的 roof/eave/ridge profile 及材料 palette；`generate_hall`、`generate_corridor` 只负责计算尺寸并组合构件。当前坡面算法保留为默认 profile 的实现。优点是默认输出、旧输入和模块接口容易锁定；适合先完成双坡断面和材料层次。

### 方案 B：通用 JSON 屋顶规则解释器

用可组合 JSON 指令描述任意曲面、屋角及材料覆盖。它更开放，但会引入第二套几何语言和验证器，并扩大旋转、冲突和版本兼容风险；复杂歇山/攒尖又明确暂缓，因此本阶段不采用。

本设计采用方案 A，符合用户指定的“复用现有屋顶生成器、拆分屋面/檐口/屋脊，并保留默认行为”。三组预设作为 Minecraft 创作参数登记，不作为文献事实。

## 非目标

- 不实现歇山、攒尖或其他复合屋顶，不新增建筑类型。
- 不改写厅堂、回廊、Assembly、ProjectEditor、MCP、工程历史或 Schematic 结构。
- 不开发屋顶图像识别、复杂 AI 或自动参考构件提取；不把 DB-2 candidate 标注当作生成输入。
- 不严格复原《营造法原》比例，不声称预设或参数是历史标准。
- 不直接写入 Minecraft 世界存档。

## 验收

- 默认 hall/corridor 方块映射的数量、半开包围盒（minimum inclusive / maximum exclusive）和排序 SHA-256 与“当前实现依据”完全一致。
- 生成三开间、五开间厅堂和至少两种长度回廊；测试常规坡面、平缓断面、硬山/悬山端部、不同檐口厚度/分层、脊饰及三种材料预设。
- 参数变化可确定性更新屋面、檐口和屋脊；无缺行、断脊、意外覆盖或未声明碰撞。对无效 profile、尺寸冲突和非法 BlockState 给出明确错误。
- 旋转 90° 后检查楼梯/半砖等受支持状态；将各配置导出并用现有 Schematic 读取器回读，方块状态、边界和数量一致。
- Assembly、ProjectEditor 修改/历史、旧工程读取、旧参数字段、MCP 和既有 Schematic 回归测试保持通过。
- Mine2Blend、Blender 和 Minecraft 1.21.5/WorldEdit 的实机外观仍单独标记为待验，不能由单元测试代替。
