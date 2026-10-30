# 参数与模块资产注册表

hall 与 corridor 的当前默认资产分别为 `jiangnan.hall@4` 和 `jiangnan.corridor@4`，参数定义为 schema v3，知识库绑定 v4。参数解析仍调用原有 hall/corridor 生成器；Assembly、ProjectEditor、历史记录或 Schematic 接口保持兼容。资产 v1-v3、参数 schema v1-v2 和知识库 v1-v3 仍可按原版本读取。

## 来源类别

| 类别 | 含义 | 当前状态 |
| --- | --- | --- |
| `user_input` | 用户明确提供的参数值 | 当前 schema 接受 |
| `literature_reference` | 可追溯到活动文献规则的参考值 | 类别已登记；当前尺寸字段不接受，因为活动资料没有提供这些数值 |
| `survey_data` | 有记录的现场测绘值 | 类别已登记；目前没有测绘数据源，也没有字段启用此类输入 |
| `derived` | 由确定性参数公式计算的值 | 仅用于派生字段，例如 `plinth_width` |
| `minecraft_adaptation` | 当前游戏方块网格、生成器规则和可复现默认值 | 当前 schema 默认类别；引用对应 generator 源代码 |

schema v3 的每个独立字段均声明 `default_category`、`accepted_categories`、`source_ids` 和说明。当前接受的独立输入类别只有 `user_input` 和 `minecraft_adaptation`。不会把 UNESCO 对村落或园林的描述误用成开间、柱高、进深或屋顶数值依据。要启用文献或测绘来源，需新增来源记录及适用于该字段的版本化 schema，并验证来源/规则引用。屋顶、檐口、屋脊与材料预设均标为 Minecraft 视觉适配；没有声称它们是历史营造比例。

Schema v3 片段（完整厅堂、直廊 JSON 位于 `jiangnan_agent/parameters/v3/`）：

```json
{
  "schema_id": "hall",
  "version": 3,
  "defaults": {
    "building_type": "hall",
    "bay_count": 3,
    "bay_spacing": 5,
    "roof_profile": {
      "ridge_height": 3,
      "section_points": [[0, 0], [1000, 1000]],
      "surface_bands": [{"start": 0, "end": 1000, "form": "stair", "material_role": "roof_stair"}]
    },
    "eave_profile": {
      "side_overhang": 1,
      "gable_end_treatment": "overhanging_gable",
      "gable_end_projection": 1,
      "thickness": 1,
      "layer_roles": ["eaves"]
    },
    "ridge_profile": {"cap_width": 0, "cap_height": 0, "material_role": "ridge"},
    "material_palette": {
      "roof_stair": "minecraft:polished_deepslate_stairs",
      "eaves": "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]"
    }
  },
  "provenance_categories": [
    "user_input", "literature_reference", "survey_data", "derived", "minecraft_adaptation"
  ],
  "field_provenance": {
    "bay_count": {
      "default_category": "minecraft_adaptation",
      "accepted_categories": ["user_input", "minecraft_adaptation"],
      "source_ids": ["generator.hall.v1"],
      "note": "Current deterministic Minecraft generator/default configuration; not a historical measurement."
    },
    "roof_profile": {
      "default_category": "minecraft_adaptation",
      "accepted_categories": ["user_input", "minecraft_adaptation"],
      "source_ids": ["generator.roof-eaves.v2"],
      "note": "Minecraft roof visual configuration; not a historical measurement or standard."
    }
  },
  "derived_provenance": {
    "category": "derived",
    "source_id": "resolver.parameters.v3"
  }
}
```

屋顶参数组包括：`roof_profile`（屋脊抬高值、归一化坡面断面及材料分段）、`eave_profile`（两侧出檐、山墙端处理、分层檐口和可选重复装饰）、`ridge_profile`（可选盖脊和重复装饰）、`material_palette`（语义角色到完整 Minecraft BlockState 的映射）。坡面材料分段引用 Palette 中的角色；当构件需要新的角色时，Palette 可以增加非空角色名。参数解析和生成都会用项目维护的 Minecraft Java 1.21.5 建筑材质子集校验 Palette 方块 ID 和已登记状态属性；旧 schema 的 `materials.roof/eaves` 也在解析时校验。此子集不是游戏全部方块注册表，未登记项会明确报错。`full_block` 只接受登记为整块的材质或 `type=double` 的半砖；启用盖脊时，盖脊主体同样要求整块材质。斜面高度发生一级变化且相邻分段包含整块或半砖表面时，生成器会填充连接方块；整块使用整块材质，半砖过渡使用双层半砖，避免只在棱角接触而留下空隙。

版本化 Minecraft 创作预设包括 `jiangnan_dark_tile`、`gray_brick_layered` 和 `warm_spruce_garden`。可从 `jiangnan_agent.parameters` 调用 `list_roof_presets()` 和 `load_roof_preset(preset_id)` 查询、加载。参数保存在 `jiangnan_agent/parameters/v3/roof_profiles.json`；应用预设后修改得到的值仍是明确输入，可确定性生成。

旧参数仍由 schema v3 资产兼容并归一化到规范字段：`roof_rise` 和 `roof_section.rise` 映射到 `roof_profile.ridge_height`；`eaves` 映射到两侧与山墙端的出檐值及端部处理；`materials.roof`、`materials.eaves` 映射到 Palette 对应角色。旧 `roof_section` 对象必须声明 `profile: "symmetric_gable"`。规范字段与旧字段同时提供时，归一化值相同则接受；冲突时在套用默认值前抛出 `ParameterConflictError`。新工程建议直接使用规范 Profile 字段。

## 参数解析示例

```python
from jiangnan_agent.parameters import resolve_parameters

result = resolve_parameters("jiangnan.hall", {"bay_count": 5})
assert result.parameter_provenance["bay_count"]["category"] == "user_input"
assert result.parameter_provenance["bay_spacing"]["category"] == "minecraft_adaptation"
assert result.derived_provenance["plinth_width"]["category"] == "derived"
```

调用者可以用 `provenance={"bay_count": {"category": "user_input"}}` 显式记录来源类别。若输入值没有附加 provenance，解析器会把它标记为 `user_input`。尝试把当前 hall 的开间值标记为 `literature_reference` 或 `survey_data` 会明确报错；用户不能用一个不相关的建筑描述替代测绘尺寸证据。

一个解析后的记录形状如下：

```json
{
  "parameter_provenance": {
    "bay_count": {"category": "user_input", "source_ids": [], "rule_ids": []},
    "bay_spacing": {
      "category": "minecraft_adaptation",
      "source_ids": ["generator.hall.v1"],
      "rule_ids": []
    }
  },
  "derived_provenance": {
    "plinth_width": {
      "category": "derived",
      "expression": "bay_count * bay_spacing + 1",
      "source_ids": ["resolver.parameters.v3"]
    }
  }
}
```

## 资产地域关联

资产登记中的知识规则作为设计上下文引用，不直接改写生成器。例如 hall 当前登记 `huizhou_core` 和规则 `hui-village-layout-and-architecture`。`region_association_kind` 为 `design_target`，附注明确说明这不等于历史真实性或尺寸验证。corridor 设计目标目前覆盖 `huizhou_core` 与 `jiangnan_suzhou`，引用对应的村落/园林级描述。

```json
{
  "asset_id": "jiangnan.hall",
  "version": 4,
  "kind": "hall",
  "source_id": "generator.hall.v1",
  "anchor_interfaces": ["front", "rear", "court_west_front", "court_west_rear", "court_east_front", "court_east_rear"],
  "parameter_schema_id": "hall",
  "parameter_schema_version": 3,
  "knowledge_base_version": 4,
  "minecraft_version": "1.21.5",
  "region_ids": ["huizhou_core"],
  "region_association_kind": "design_target",
  "region_association_note": "Design target only; this association does not validate historical authenticity or dimensions.",
  "knowledge_rule_ids": ["hui-village-layout-and-architecture"]
}
```

`AssetSpec` 加载时会确认地域 profile 处于 active、知识规则存在且状态 active，并与资产的某个设计目标地域精确匹配。目录专用地域或未知规则不能注册为 v4 资产关联。

## 兼容性与可重复生成

- 参数 schema v1-v2、asset v1-v3 目录和知识库 v1-v3 保持可读取；新默认使用 schema v3、asset v4 与知识库 v4。
- 对同一组兼容输入，asset v1-v4 继续调用现有厅堂/直廊生成器；默认 roof profile 的厅堂与直廊输出由固定哈希回归锁定。
- 资产目录 v4 原样保留 v1-v3 条目；v4 模块附加参数来源、地域、知识版本与 profile 参数配置。
- `ProjectEditor` 重生成模块时保留已有来源记录；工程保存/重开与模块历史继续使用现有序列化接口。
- 新 roof/eave/ridge/palette profile 可通过工程 JSON 保存、重开和重生成，且保留撤销/重做历史。
- 所有尺寸是 Minecraft 方块网格输入或确定性派生结果。除非另有已核查的测绘/文献证据，它们不代表历史营造标准。
