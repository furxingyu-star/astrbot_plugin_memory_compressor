# astrbot_plugin_memory_compressor

AstrBot 记忆压缩插件：在对话压缩时提取长期事实，索引常驻提示词，细节按需读取。

## 功能
- **自动压缩**：对话轮数超过阈值时，调用 LLM 将旧对话压缩为摘要与事实档案。
- **索引注入**：每轮请求只注入事实的“标题列表”，几乎不额外占用上下文。
- **按需检索**：LLM 可通过 `recall_memory(topic)` 工具读取某条记忆的详细内容。
- **数据持久化**：记忆按会话隔离，存储在 `data/plugin_data/astrbot_plugin_memory_compressor/`，插件更新不丢失。

## 安装
1. 将本目录放入 `AstrBot/data/plugins/`。
2. 重启 AstrBot，或在 WebUI 插件页重载插件。
3. 在 WebUI 插件设置中调整阈值与保留轮数（默认触发阈值 10，保留最近 4 轮）。

## 重要提醒
本插件接管了上下文压缩职责。请在 AstrBot 配置中将**内置压缩关闭**（“压缩前最多保留对话轮数”设为 `-1`，并将上下文窗口兜底值设得足够大），避免与内置压缩冲突。

## 配置项
| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `compress_threshold` | int | 10 | 超过此轮数触发压缩 |
| `keep_recent_rounds` | int | 4 | 压缩时保留的最近原文轮数 |
| `enable_tool_recall` | bool | true | 是否启用按需检索工具 |# astrbot_plugin_memory_compressor