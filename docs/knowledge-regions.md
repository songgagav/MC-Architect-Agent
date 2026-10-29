# 地域知识范围与参考资料

本文区分当前可查询的知识记录、用户提供的视觉参考和仅供后续研究的地域候选。候选项暂不进入 Knowledge Base、参数 schema、Asset Library 或生成器。

## 当前知识范围

本轮聚焦用户指定的“长江中下游的江南徽派建筑风格”。这是项目范围，不代表长江中下游存在一种边界统一、内部完全一致的历史风格。可查询规则使用精确地域标签，不通过父子地区关系自动扩展：

- `cn.anhui.south.huangshan.yixian.xidi-hongcun`：仅对应 UNESCO 名录中的西递、宏村。
- `cn.anhui.south.huizhou`：用于黄山市地方志办网页所概述的徽州宅居内容；每条规则的范围仍以条目自身说明为准。
- `user.selected.lower_yangtze.jiangnan_huizhou`：用户选定的项目范围，只是用户偏好记录。

文献事实、Minecraft 方块适配和用户偏好分开保存。现有的历史/地方资料描述用于定性规则，未推导或声称任何统一的开间、柱网、进深、柱高或屋顶尺寸。Knowledge Base v2 尚未改变现有厅堂和回廊的方块生成逻辑。

## 用户投影文件审阅

`E:\MCbuild\Template` 中的两个文件已用 Mine2Blend 与 Blender 生成四向预览。以下是文件属性及画面观察，目的是留存可复现的用户视觉参考，不是判断其历史年代、地域来源或真实性。

| 文件 | Litematic 尺寸 | 文件元数据方块数 | 调色板项数 | SHA-256 |
|---|---:|---:|---:|---|
| `芳堂-茯茯角.litematic` | 43 × 36 × 42 | 7,930 | 123 | `0bb61a4466780f3afa625c654481e344a1271c063ac3adc3c7d8139f3e2d3d9a` |
| `流苏坊框架-茯茯角.litematic` | 31 × 31 × 32 | 3,909 | 84 | `a26bc4b06639bf33236f5fa2905fb830f26caecb671387c785bcd0259ecbda7e` |

预览中可观察到深灰色屋面、浅色墙体、分层屋面与不同体量组合。这些仅记录为本项目可参考的配色、体量和 Minecraft 方块表现；规则来源明确标注为 `user_preference`，不能据此断言它们代表徽派传统做法。原始投影文件没有复制进仓库，也未被修改。

本机生成的八张预览保存在 `workspace/previews/template-reference-20261029/`。原投影文件及其派生预览都留在本地，不纳入仓库提交；知识条目只记录原件相对路径和摘要，供本机核对来源。

## 规则出处与适用边界

| 记录 | 类型 | 可支持的内容 | 不支持的推断 |
|---|---|---|---|
| [UNESCO：西递、宏村](https://whc.unesco.org/en/list/1002/) | `literature_fact` | 名录对两处村落的位置、历史时期、聚落格局、建筑、装饰和水系的描述 | 将场地级描述直接套到所有徽州住宅或整个江南 |
| [黄山市人民政府/市志办：徽州宅居要素](https://www.huangshan.gov.cn/zjhs/rwhz/hpjz/8294057.html) | `literature_fact` | 网页所概述的黛瓦/灰瓦、白墙、马头墙、砖木石雕及所述宅居形式 | 统一材料规范、统一平面类型或未经来源支持的尺寸 |
| [黄山市人民政府/市志办：徽州宅居](https://www.huangshan.gov.cn/zjhs/rwhz/fsmq/8294878.html) | 参考来源 | 作为地方志办相关概述的补充检索入口 | 自动升级成所有历史时期的通用结论 |

黄山市政府网页是地方志办提供的概述资料，因此相应条目采用中等置信级别，并限制为定性描述。UNESCO 条目也严格限定到名录地点和其描述范围。

## 后续候选地域（尚未接入）

下列资料用于确定后续查证方向。当前没有为这些地区增加知识规则、参数默认值或生成行为。

| 候选地域 | 后续可调查主题 | 状态与资料入口 |
|---|---|---|
| 苏州—太湖 | 宅园关系、园林空间、厅堂与院落的衔接 | 仅列候选：[苏州市园林和绿化管理局建筑资料](https://ylj.suzhou.gov.cn/szsylj/ylys/201903/484421d38f504f5787a8f307925e3ad7.shtml)、[师俭园资料](https://ylj.suzhou.gov.cn/szsylj/ylml/201912/0e8becef868a4f4b8b6618a4ba4e84c8.shtml) |
| 嘉兴—湖州水乡（乌镇、南浔、西塘） | 临水街巷、河埠、住宅与水系关系 | 仅列候选：[文旅部乌镇资料](https://sjfw.mct.gov.cn/site/dataservice/culdetails?curId=10&id=34882)、[文旅部南浔资料](https://sjfw.mct.gov.cn/site/dataservice/culdetails?curId=10&id=34889)、[嘉兴市西塘相关规划资料](https://jsj.jiaxing.gov.cn/module/download/downfile.jsp?classid=0&filename=cd0d550c2e1140a487d67e57796f9a34.pdf) |
| 浙东（宁波；绍兴待补独立来源） | 地方民居色彩、材料、街巷与院落 | 仅列候选：[宁波市住建局传统村落建设指引](https://zjw.ningbo.gov.cn/module/download/downfile.jsp?classid=0&filename=4f2191f7ef9c4b149af1ed6b3747c768.pdf) |
| 扬州—运河沿线 | 商业街巷、宅院、会馆与运河城市关系 | 仅列候选：[江苏省政府扬州街巷与宅居资料](https://www.jiangsu.gov.cn/art/2025/4/26/art_33718_11553099.html) |
| 上海松江 | 历史街区、地方宅居及其与江南水乡的联系 | 仅列候选：[上海市政府松江资料](https://www.shanghai.gov.cn/songjiang/index.html) |

只有在补齐适用地区、建筑类型、文献依据和反例/边界后，候选主题才进入新的知识库版本；是否进一步连接到参数和生成器需要单独验证，不能由资料目录自动推导。
