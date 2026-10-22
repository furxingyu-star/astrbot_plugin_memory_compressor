import json
from pathlib import Path

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

MEMORY_DIR = Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_memory_compressor"


class MemoryCompressorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 每轮 LLM 请求前：注入记忆索引
    @filter.on_llm_request()
    async def inject_memory_index(self, event: AstrMessageEvent, req):
        umo = event.unified_msg_origin
        facts = self._load_memory(umo).get("facts", {})
        if not facts:
            return
        index_lines = [f"- {title}" for title in facts.keys()]
        req.system_prompt += (
            "\n\n[长期记忆索引]\n"
            + "\n".join(index_lines)
            + "\n如需某条记忆的详细内容，请调用 recall_memory(topic) 工具。"
        )

    # 2. 压缩检查：挂在 on_llm_request 上，在注入索引之后执行
    @filter.on_llm_request(priority=-1)
    async def maybe_compress(self, event: AstrMessageEvent, req):
        umo = event.unified_msg_origin
        history = await self.context.conversation_manager.get_conversation(umo)
        threshold = self.config.get("compress_threshold", 10)
        keep = self.config.get("keep_recent_rounds", 4)

        if not history or len(history) <= threshold:
            return
        await self._compress_and_store(umo, history, keep)

    async def _compress_and_store(self, umo: str, history: list, keep: int):
        old_part = history[:-keep] if keep > 0 else history
        if not old_part:
            return

        prompt = (
            "请处理以下对话：\n"
            "1. 用一段话总结核心内容（滚动摘要）；\n"
            "2. 提取值得长期记住的事实（用户偏好、身份、进行中的事），"
            "每条事实给出简短标题和详细内容。\n"
            '以 JSON 返回：{"summary":"...","facts":[{"title":"...","content":"..."}]}\n\n'
            f"对话：\n{json.dumps(old_part, ensure_ascii=False)}"
        )

        try:
            result = await self.context.llm_generate(prompt=prompt)
            parsed = json.loads(result)
        except Exception as e:
            logger.error(f"[记忆压缩] LLM 调用或解析失败：{e}")
            return

        memory = self._load_memory(umo)
        memory.setdefault("summary", "")
        memory["summary"] += "\n" + parsed.get("summary", "")
        facts = memory.setdefault("facts", {})
        for fact in parsed.get("facts", []):
            title = fact.get("title", "").strip()
            if title:
                facts[title] = fact.get("content", "")
        self._save_memory(umo, memory)

        # 将旧对话从会话历史中移除，仅保留最近 keep 轮
        await self.context.conversation_manager.update_conversation(
            umo, history[-keep:] if keep > 0 else []
        )
        logger.info(f"[记忆压缩] 已压缩 {len(old_part)} 条旧消息，存储 {len(parsed.get('facts', []))} 条事实。")

    # 3. LLM 工具：按需读取记忆详情
    @filter.llm_tool()
    async def recall_memory(self, event: AstrMessageEvent, topic: str) -> str:
        """根据标题从长期记忆中读取详细内容。"""
        if not self.config.get("enable_tool_recall", True):
            return "记忆检索工具当前未启用。"
        umo = event.unified_msg_origin
        facts = self._load_memory(umo).get("facts", {})
        if not facts:
            return "当前会话尚无长期记忆条目。"
        if topic in facts:
            return facts[topic]
        matched = [t for t in facts if topic in t or t in topic]
        if matched:
            return "\n\n".join(f"【{t}】\n{facts[t]}" for t in matched)
        return f"未找到与“{topic}”匹配的记忆。可用条目：{list(facts.keys())}"

    # 辅助方法
    def _memory_path(self, umo: str) -> Path:
        safe = umo.replace(":", "_").replace("/", "_")
        return MEMORY_DIR / f"{safe}.json"

    def _load_memory(self, umo: str) -> dict:
        path = self._memory_path(umo)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_memory(self, umo: str, memory: dict):
        self._memory_path(umo).write_text(
            json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
        )