# Phase 5 — Codex 本地建筑工具设计

## 意图

让当前 Codex 对话能够用自然语言设计、检查、修改和导出 Minecraft 建筑。Codex 负责理解请求并选择工具；本地 Python 工具负责调用已经实现的参数化生成器、模块组合、工程历史、验证器和 Sponge v3 导出器。模型只提交有限的类型化参数，不生成方块坐标清单。

## 目标

- 用本地 MCP 服务把现有建筑引擎暴露给 Codex，不在项目中启动另一个模型 Agent。
- 支持从空白工程创建厅堂模块、按稳定模块 ID 修改厅堂/直廊参数、组合模块、检查变更、验证 Assembly 并导出 `.schem`。
- 让新建的三开间厅堂流程可复现：创建工程、生成模块、验证、持久化并导出。
- 修改现有工程时，通过 `ProjectEditor` 生成版本记录；精确报告受影响模块和方块变化，保留撤销/重做。
- MCP 工具使用结构化参数和结果，复用 Python 引擎中的校验，不接受模型输出的原始方块体素数据。
- 提供本地 Codex 连接配置与使用说明；普通 CLI 与 pytest 安装不因 MCP 集成而强制依赖 OpenAI API。

## 非目标

- 不在 Python 应用里调用 OpenAI API，不引入 Agents SDK、模型 API Key、模型账单或第二套对话状态。当前 Codex 是唯一的自然语言 Agent。
- 不引入多 Agent 协作、网站、GUI、Blender 渲染、参考图理解或江南营造文献知识库。
- 不生成整个街区，不直接向 Minecraft 世界或存档写入方块。
- 不假设已有未实现的模块类型。第一版只暴露当前生成器可以生成的厅堂和直廊；简单房屋仍走现有旧式单体生成流程，不伪装成 Assembly 模块。
- 不增加模块删除、任意文件操作或静默覆盖工程/导出文件的工具。

## 方案比较与选择

1. **当前 Codex 调用本地 MCP 工具（采用）**：由 Codex 完成自然语言理解和工具编排，本地 MCP 进程直接调用 Python 引擎。符合用户选择，不需要独立 API Key，也能沿用现有工程和历史模型。代价是建筑对话发生在 Codex 中，项目本身不提供独立聊天命令。
2. **项目内置 Agents SDK 聊天 CLI**：可独立运行 `jiangnan chat`，但要配置 `OPENAI_API_KEY`，额外承担 API 调用、对话状态和 SDK 版本维护；与“由当前 Codex 调用”重复，因此本阶段不选。
3. **只让模型返回 JSON 设计计划**：不必运行 MCP，但本地代码还需要另一个步骤手动执行计划，不能完成自然语言到工程编辑的闭环，因此不选。

## 现状和边界

- `JiangnanProject` 保存 Assembly、生成设置和版本历史；工程 JSON 写入采用原子替换。
- `ProjectEditor` 能按模块 ID 重生成厅堂/直廊，也支持模块替换、撤销和重做；它目前没有统一的新增模块、变换和连接历史入口，需要补齐这些编辑入口，避免 MCP 工具绕开 Phase 4 历史。
- Assembly 已提供模块锚点、旋转/平移/镜像、连接、碰撞/净空检查和组合渲染。
- CLI 已有 `init`、`validate`、`history`、`undo`、`redo`、`generate`，可以继续保留，不被 MCP 改写。
- 目标游戏继续固定为 Minecraft Java 1.21.5 / DataVersion 4325。

## 设计

### 运行方式

- 新增本地 Python MCP stdio 服务和独立工具适配层；服务进程只负责把 MCP 参数转换成领域调用，不复制生成器、校验或序列化逻辑。
- MCP 作为可选安装项，例如 `.[mcp]`；没有 MCP 依赖时，现有 CLI、库导入和测试安装仍可用。
- Codex 通过本机 Python 3.12 虚拟环境启动该服务。使用 Codex 本机 MCP 注册命令登记 stdio 进程；注册项位于当前用户配置，但服务参数固定绑定 `E:\MCbuild` 这份仓库，不启用网络监听；MCP 协议日志写到 stderr，stdout 只承载协议数据。仓库迁移位置后需更新该注册项。
- Codex 是唯一的自然语言编排者。工具说明明确告知支持的 `kind`、参数、编辑作用范围和失败条件；工具的输入/输出均为有限 JSON 数据。

### 工具面

只暴露 Phase 5 完成首个建筑与精确修改闭环所需的工具：

- **查询**：`list_projects`、`get_project`、`list_modules`、`get_module`。
- **生成和编辑**：`create_project`、`create_module`、`set_parameters`、`transform_module`、`connect_modules`、`replace_module`。第一版 `create_module` 和 `set_parameters` 仅接受 `hall` 与 `corridor`；`transform_module` 支持现有引擎提供的平移、绕 Y 轴旋转和镜像；连接只接受现有模块及明确锚点，自动放置的新模块通过 `create_module` 的可选锚点连接信息调用现有连接算法。
- **质量检查**：`validate_assembly`、`inspect_changes`。返回结构化 issue、模块 ID、版本号和方块变化数量；不把完整方块表发送给模型。
- **交付**：`export_schematic`。复用现有 `generate` 来源裁定：Assembly 非空时只验证/渲染 Assembly，失败即报错；空 Assembly 才使用旧设置。

所有会改变工程的工具都调用 `ProjectEditor` 的公开方法并创建历史版本，然后立即原子保存。新增历史入口必须准确覆盖新增/重生成模块、变换和连接的受影响 ID 与方块差异。`create_project` 和导出使用新路径并拒绝覆盖；现有工程的修改仅作用于调用方明确指定的工程文件，并写入历史。用户明确要求修改指定工程/模块/参数时，视为对该范围的人工确认，不再重复询问；目标或变更范围不明确时，Codex 先用只读工具查询并向用户澄清，不能先写入。第一版不提供删除模块、任意路径读写或世界存档写入。

### 路径与错误处理

- 工具只接触仓库下的 `workspace/projects/` 工程 JSON 和 `workspace/exports/` `.schem` 文件；使用相对路径，拒绝绝对路径、路径穿越和解析后越出对应根目录的符号链接。
- 新工程与导出文件必须不存在；已有工程的显式编辑使用现有原子保存和版本历史。
- 每个工具都返回可读错误，不吞掉生成、参数校验、Assembly 验证或导出失败，也不自动切换到另一种生成来源。
- 工具结果明确标出操作类型、工程路径、当前版本、受影响模块、验证状态、文件路径和方块数量；模型总结结果时不得声称未运行的游戏内验收已通过。

### 当前 Codex 使用说明

- 文档说明安装 MCP 可选依赖、使用仓库 `.venv` Python 启动 stdio 服务、用 `codex mcp add` 在当前 Codex 用户配置登记该仓库工具、验证登记状态并重载/重启 Codex；虽然注册项在用户级，MCP 服务仍只能访问绑定仓库内允许的两个目录。
- 仓库级指引要求建筑任务优先读取工程后调用可用的建筑工具；任何写入只针对用户指定的 `.jap.json`，导出只进入 `workspace/exports/`，不直接改 Minecraft 世界。
- 若当前 Codex 客户端尚未加载 MCP 配置，服务仍可独立协议测试；实际对话验收需在客户端重载后完成。

## 验收

- 不配置 `OPENAI_API_KEY` 也能启动 MCP 服务；CLI 和基础项目安装仍正常。
- MCP 工具清单和参数 schema 可由客户端发现；读工具返回项目/模块数据；非法参数与越界路径被拒绝。
- 对话“设计一座三开间江南民居”能够调用本地工具创建一个 `bay_count=3` 的厅堂工程，校验 Assembly 并导出可回读的 Sponge v3 `.schem`。
- 修改现有厅堂/直廊时，工具精确定位模块 ID、写入一个版本记录，并确认非目标模块数据不变；撤销和重做仍可用。
- Assembly 非空时使用 Assembly；验证或渲染失败不会回退旧设置；新建文件和 schematic 导出不会覆盖已存在文件；所有工具都不写入 Minecraft 存档。
- 单元/协议测试覆盖工具参数、路径边界、历史记录、校验错误、schema/发现和 schematic 回读；完整 pytest 通过。真实 Minecraft/WorldEdit 放置仍单独标记为人工实机验收。

## 留给实现者的选择

- 选择当前兼容的 MCP Python SDK 版本和 Codex 注册方式，并在依赖及文档中固定可复现配置。
- 设计 JSON 结构时优先使用已有 dataclass 和 serializer；工具返回保持轻量，不暴露全部稀疏方块体素。
- 选择如何将 `create_project`、新增模块、连接与变换纳入 `ProjectEditor` 的公共、可回归测试接口；不要从 MCP 层直接改 `project.assembly` 后绕过历史。

## 参考

- [OpenAI Agents SDK：当前 SDK 运行在应用中](https://developers.openai.com/api/docs/guides/agents/sdk)
- [OpenAI Agents SDK Python quickstart：单 Agent、工具与 API Key 设置](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python)
- [OpenAI Codex 文档：连接 MCP 服务](https://developers.openai.com/learn/docs-mcp)
