# Jiangnan Architect Agent 工作约定

处理本仓库中的江南 Minecraft 建筑任务时，优先使用 `jiangnan-architect` 本地 MCP 工具完成工程读取、模块编辑、校验和导出。

- 编辑前先读取目标工程和相关模块；通过稳定的 `module_id` 指定修改对象。
- 按用户明确提出的工程、模块和参数范围操作。模块或参数不明确时先询问用户，不要随意挑选第一个工程或模块。
- 每次修改后调用 `inspect_changes` 和 `validate_assembly` 检查结果；只有用户要求导出时才调用 `export_schematic`。
- 对地域或历史营造事实先调用 `list_knowledge_rules`；保留返回的来源、证据类型、置信度和适用范围。只有 `literature_fact` 可用于陈述文献事实，不能将用户偏好或 Minecraft 适配说成历史事实，也不能由定性描述推断传统尺寸。
- 模块变更会形成工程历史。可通过 `inspect_changes` 与 `jiangnan history` 检查；用 `jiangnan undo` 或 `jiangnan redo` 恢复工程版本。
- 仅将工程 JSON 写入 `workspace/projects`，仅将 `.schem` 写入 `workspace/exports`。使用相对于这些目录的路径，并为新输出选择不存在的文件名。
- 不删除或覆盖已有文件，不写入任何 Minecraft 存档，不把测试投影直接放入正式世界。
- 当前工具只支持厅堂 `hall` 与直廊 `corridor` 的创建、参数更新和替换；超出范围时说明限制，不要伪造已实现的模块。
- 不把海量方块数据放进提示词。让本地引擎通过工具参数生成方块，并以校验报告、版本差异和导出文件确认结果。
