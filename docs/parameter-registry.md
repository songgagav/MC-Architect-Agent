# 参数与模块资产注册表

hall 与 corridor 的当前默认资产分别为 `jiangnan.hall@3` 和 `jiangnan.corridor@3`，参数定义为 schema v2。它们仍然调用原有 hall/corridor 生成器，未改变 Assembly、ProjectEditor、历史记录或 Schematic 接口。

## 来源类别

| 类别 | 含义 | 当前状态 |
| --- | --- | --- |
| `user_input` | 用户明确提供的参数值 | 当前 schema 接受 |
| `literature_reference` | 可追溯到活动文献规则的参考值 | 类别已登记；当前尺寸字段不接受，因为活动资料没有提供这些数值 |
| `survey_data` | 有记录的现场测绘值 | 类别已登记；目前没有测绘数据源，也没有字段启用此类输入 |
| `derived` | 由确定性参数公式计算的值 | 仅用于派生字段，例如 `plinth_width` |
| `minecraft_adaptation` | 当前游戏方块网格、生成器规则和可复现默认值 | 当前 schema 默认类别；引用对应 generator 源代码 |

schema v2 的每个独立字段均声明 `default_category`、`accepted_categories`、`source_ids` 和说明。当前接受的独立输入类别只有 `user_input` 和 `minecraft_adaptation`。不会把 UNESCO 对村落或园林的描述误用成开间、柱高、进深或屋顶数值依据。要启用文献或测绘来源，需新增来源记录及适用于该字段的版本化 schema，并验证来源/规则引用。

Schema v2 片段（完整厅堂、直廊 JSON 位于 `jiangnan_agent/parameters/v2/`）：

```json
{
  "schema_id": "hall",
  "version": 2,
  "defaults": {"building_type": "hall", "bay_count": 3, "bay_spacing": 5},
  "provenance_categories": [
    "user_input", "literature_reference", "survey_data", "derived", "minecraft_adaptation"
  ],
  "field_provenance": {
    "bay_count": {
      "default_category": "minecraft_adaptation",
      "accepted_categories": ["user_input", "minecraft_adaptation"],
      "source_ids": ["generator.hall.v1"],
      "note": "Current deterministic Minecraft generator/default configuration; not a historical measurement."
    }
  },
  "derived_provenance": {
    "category": "derived",
    "source_id": "resolver.parameters.v2"
  }
}
```

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
      "source_ids": ["resolver.parameters.v2"]
    }
  }
}
```

## 资产地域关联

资产登记中的知识规则作为设计上下文引用，不直接改写生成器。例如 hall 当前登记 `huizhou_core` 和规则 `hui-village-layout-and-architecture`。`region_association_kind` 为 `design_target`，附注明确说明这不等于历史真实性或尺寸验证。corridor 设计目标目前覆盖 `huizhou_core` 与 `jiangnan_suzhou`，引用对应的村落/园林级描述。

```json
{
  "asset_id": "jiangnan.hall",
  "version": 3,
  "kind": "hall",
  "source_id": "generator.hall.v1",
  "anchor_interfaces": ["front", "rear", "court_west_front", "court_west_rear", "court_east_front", "court_east_rear"],
  "parameter_schema_id": "hall",
  "parameter_schema_version": 2,
  "knowledge_base_version": 3,
  "minecraft_version": "1.21.5",
  "region_ids": ["huizhou_core"],
  "region_association_kind": "design_target",
  "region_association_note": "Design target only; this association does not validate historical authenticity or dimensions.",
  "knowledge_rule_ids": ["hui-village-layout-and-architecture"]
}
```

`AssetSpec` 加载时会确认地域 profile 处于 active、知识规则存在且状态 active，并与资产的某个设计目标地域精确匹配。目录专用地域或未知规则不能注册为 v3 资产关联。

## 兼容性与可重复生成

- 参数 schema v1 和 asset v1/v2 目录保持可读取；新默认使用 schema v2 与 asset v3。
- 对同一组输入，asset v1、v2、v3 继续调用相同生成器，测试比较其方块映射一致。
- asset v1/v2 保持原有模块元数据形状；v3 模块附加来源、地域和版本信息。
- `ProjectEditor` 重生成模块时保留已有来源记录；工程保存/重开与模块历史继续使用现有序列化接口。
- 所有尺寸是 Minecraft 方块网格输入或确定性派生结果。除非另有已核查的测绘/文献证据，它们不代表历史营造标准。
