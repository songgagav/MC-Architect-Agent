# 地域知识范围与参考资料

Knowledge Base v4 将来源、规则和地域配置分别保存到 `jiangnan_agent/knowledge/v4/sources.json`、`rules.json` 和 `regions.json`。v4 增加 Roof & Eaves v2 生成器及 schema v3 解析器的项目代码来源；地域配置、知识规则和状态与 v3 保持一致，不新增历史屋顶规则。v1-v3 仍可显式加载。查询按地域 ID 精确匹配，不推断行政层级或风格相似性。规则分为已核查的 `active` 和待核查的 `pending_verification`；普通查询隐藏待核查记录。

## 当前启用地域

| 地域 ID | 范围 | 状态 |
| --- | --- | --- |
| `huizhou_core` | UNESCO 列入的西递、宏村，仅限其村落级描述 | `active` |
| `jiangnan_suzhou` | UNESCO 列入的苏州古典园林，仅限园林级描述 | `active` |
| `jiaxing_huzhou_water_towns` | 嘉兴/湖州水乡 | `catalog_only` |
| `ningbo_east_zhejiang` | 宁波/浙东 | `catalog_only` |
| `yangzhou_canal` | 扬州/运河地区 | `catalog_only` |
| `shanghai_songjiang` | 上海/松江 | `catalog_only` |

目录项状态不代表其知识已经入库。目录专用地域没有可执行规则；当前没有将嘉兴、浙东、扬州或松江的规则接入参数或生成器。

## v4 当前规则及出处

| 来源 ID | 核查状态 | v4 中允许支持的内容 | 明确不支持 |
| --- | --- | --- | --- |
| `unesco.xidi-hongcun.ouval` — [UNESCO：皖南古村落－西递、宏村](https://whc.unesco.org/en/list/1002/) | 官方页面全文已核查；定位为 Description（中文）及 Outstanding Universal Value > Brief synthesis（英文） | 名录对西递、宏村的位置、村落格局、景观、建筑、装饰和水系的描述 | 推广为所有徽州住宅的规则；历史开间、柱网、进深、柱高或屋面尺寸 |
| `unesco.suzhou-gardens.ouval` — [UNESCO：苏州古典园林](https://whc.unesco.org/en/list/813/) | 官方页面全文已核查；定位为 Description（中文）及 Outstanding Universal Value > Brief synthesis（英文） | 名录对苏州古典园林、缩景设计及水、石、植物和建筑等园林元素的描述 | 推广为所有江南住宅/园林的统一布局、构造做法或比例 |
| `huangshan.gazette.hui-residence-elements` — [黄山市政府：徽州宅居要素](https://www.huangshan.gov.cn/zjhs/rwhz/hpjz/8294057.html) | 仅元数据可见；本次未取回正文和章节定位；相关规则为 `pending_verification` | 仅保留待核查任务 | 默认查询、参数默认值、生成器规则和历史标准 |
| `huangshan.gazette.hui-residence` — [黄山市政府：徽州宅居](https://www.huangshan.gov.cn/zjhs/rwhz/fsmq/8294878.html) | 仅元数据可见；本次未取回正文和章节定位 | 来源目录记录 | 未核实的正文摘要或任何尺寸标准 |
| `suzhou.garden-admin.architecture` — [苏州市园林和绿化管理局：建筑](https://ylj.suzhou.gov.cn/szsylj/ylys/201903/484421d38f504f5787a8f307925e3ad7.shtml) | 页面正文未成功取回；仅列为来源入口，不关联活动规则 | 后续全文核查入口 | 建筑形式、构造或尺寸结论 |
| `generator.roof-eaves.v2` — 本项目屋面、檐口和屋脊构件生成器 | 已核对仓库实现 | Minecraft 屋面断面、檐口、屋脊和材料角色的确定性实现 | 历史营造事实、实测比例或地域规范 |
| `resolver.parameters.v3` — 本项目参数解析器 schema v3 | 已核对仓库实现 | 参数别名归一化、派生字段和参数来源标记 | 历史建筑数值或未实现的建筑规则 |

UNESCO 页面未给出页面出版日期，因此来源记录把 `publication_date` 留空，并在 `date_note` 中记录页面所列的遗产列入年份。章节定位、核查等级、访问日期均在 JSON 来源记录中。地方网页未核实的日期不会从搜索摘要推定。

规则中的 `confidence=high` 指规则准确转述了所引用的官方名录文字，不代表该文字可以外推到其他地域、建筑类型或年代。v4 的活动历史规则是描述性知识，不自动生成历史尺寸或营造指令；新增的项目代码来源只描述 Minecraft 创作实现。

### 查询示例

```json
{
  "knowledge_base_version": 4,
  "region": "huizhou_core",
  "building_type": "traditional_village",
  "evidence_kind": "literature_fact"
}
```

返回记录含 `source_id`、题名、作者/发布机构、日期说明、URL/DOI/ISBN、章节定位、核查等级、适用范围和规则状态。普通查询不返回待核查条目。v4 新增的两条 `project_code` 来源仅用于解释当前代码和创作参数，不会作为营造史证据。兼容性调用仍可显式选择知识库 v1-v3；这些旧版记录保留其原始数据，不会被静默改写。

## 参数/游戏适配与用户参考的边界

- 生成器规则标记为 `minecraft_adaptation`，描述当前 Python 生成行为，不是传统建筑事实。
- Roof & Eaves v2 的三组屋顶预设是 Minecraft 创作参数，使用屋面坡面、檐口、屋脊和方块状态表达视觉差异；它们没有历史真实性或营造比例主张。
- 用户偏好（如自由组合模块）标记为 `user_preference`，不是文献证据。
- 参数来源类别包括 `user_input`、`literature_reference`、`survey_data`、`derived` 和 `minecraft_adaptation`。当前 hall/corridor schema 的独立输入只接受用户输入或当前生成器适配；没有可核实的测绘尺寸，也没有能支撑开间、柱高或屋面参数的活动文献规则，所以这些字段目前不接受 `literature_reference` 或 `survey_data` 覆盖。
- `E:\MCbuild\Template` 中两个 Litematica 文件只作视觉参考，摘要用于识别本地原件；不据此推断年代、地域真实性或营造标准。
- 用户输入、测绘数据、派生值和 Minecraft 游戏适配参数在参数注册表中分开记录。当前生成器默认值是可复现的 Minecraft 设计输入，不得描述为历史测绘数据。

| 本地文件 | 尺寸 | 文件元数据方块数 | 调色板项 | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| `芳堂-茯茯角.litematic` | 43 × 36 × 42 | 7,930 | 123 | `0bb61a4466780f3afa625c654481e344a1271c063ac3adc3c7d8139f3e2d3d9a` |
| `流苏坊框架-茯茯角.litematic` | 31 × 31 × 32 | 3,909 | 84 | `a26bc4b06639bf33236f5fa2905fb830f26caecb671387c785bcd0259ecbda7e` |

原投影文件及其本地预览不会复制进知识库或由规则修改。文件视觉上可见的色彩、体量与屋面分层只能作为个人设计参考。
