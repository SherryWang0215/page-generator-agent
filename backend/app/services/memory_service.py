from __future__ import annotations

import json
import logging

from ..config import settings
from .conversation_store import ConversationStore

logger = logging.getLogger(__name__)

# Intent types determined from conversation context
IntentType = str  # "generate" | "revise" | "chat"


class MemoryService:
    """Manage conversation memory: load history, assemble LLM context, detect intent."""

    def __init__(self, store: ConversationStore | None = None) -> None:
        self._store = store or ConversationStore()

    def get_or_create_conversation(
        self, user_id: str, conversation_id: str | None = None, page_id: str | None = None
    ) -> dict:
        """Get an existing conversation or create a new one."""
        self._store.ensure_indices()

        if conversation_id:
            conv = self._store.get_conversation(conversation_id)
            if conv:
                return conv

        return self._store.create_conversation(user_id=user_id, page_id=page_id)

    def load_history(self, conversation_id: str) -> list[dict]:
        """Load recent message history for a conversation.

        Returns messages in chronological order, limited to memory_max_rounds.
        Returns empty list if ES is unavailable (graceful degradation).
        """
        if not settings.memory_enabled:
            return []

        try:
            self._store.ensure_indices()
            return self._store.get_recent_messages(conversation_id)
        except Exception as exc:
            logger.warning(
                "Failed to load conversation history, degrading to stateless | conv=%s | reason=%s",
                conversation_id,
                exc,
            )
            return []

    def _build_profile_context(self, user_id: str) -> str:
        """Build user profile context string for injection into system prompt.

        Only includes preferences with confidence >= threshold.
        Returns empty string if no profile or all confidences below threshold.
        """
        try:
            profile = self._store.get_profile(user_id)
        except Exception:
            return ""

        if not profile or not profile.get("preferences"):
            return ""

        prefs = profile["preferences"]
        threshold = settings.profile_confidence_threshold
        lines: list[str] = []

        for dimension in ("style", "page_type", "color_tendency", "topics", "tone"):
            dim_data = prefs.get(dimension)
            if not dim_data:
                continue
            confidence = dim_data.get("confidence", 0)
            if confidence < threshold:
                continue
            preferred = dim_data.get("preferred", "")
            if preferred:
                lines.append(f"- {dimension}: {preferred} (置信度 {confidence:.0%})")

        if not lines:
            return ""

        return "用户偏好：\n" + "\n".join(lines)

    def build_llm_messages(
        self,
        conversation_id: str,
        current_content: str,
        system_prompt: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, str]]:
        """Assemble the full message list for LLM input.

        Structure: [system_prompt + profile_context] + [summary] + recent_history + [current_user_message]
        """
        history = self.load_history(conversation_id)

        messages: list[dict[str, str]] = []
        if system_prompt:
            # Inject user profile into system prompt if available
            profile_ctx = self._build_profile_context(user_id) if user_id else ""
            if profile_ctx:
                enhanced_prompt = f"{system_prompt}\n\n{profile_ctx}"
            else:
                enhanced_prompt = system_prompt
            messages.append({"role": "system", "content": enhanced_prompt})

        # Inject conversation summary if available
        conv = self._store.get_conversation(conversation_id)
        if conv and conv.get("summary"):
            messages.append({"role": "system", "content": f"[对话摘要]\n{conv['summary']}"})

        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant", "system"):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": current_content})
        return messages

    def save_assistant_message(
        self,
        conversation_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> dict:
        """Save an assistant message."""
        embedding = None
        if settings.search_enabled and settings.search_embed_messages:
            embedding = self._generate_embedding(content)
        return self._store.add_message(
            conversation_id, role="assistant", content=content, metadata=metadata, embedding=embedding
        )

    def maybe_compress_conversation(self, conversation_id: str) -> str | None:
        """Compress early conversation history into a summary if needed.

        Trigger condition: total message rounds > memory_max_rounds + summary_trigger_rounds.
        Sliding window: compress messages before the most recent max_rounds.
        Returns the summary text, or None if not triggered.
        """
        if not settings.summary_enabled:
            return None

        try:
            total_messages = self._store.count_messages(conversation_id)
            max_messages = settings.memory_max_rounds * 2
            trigger_threshold = max_messages + settings.summary_trigger_rounds * 2

            if total_messages < trigger_threshold:
                return None

            return self._compress_conversation(conversation_id, total_messages, max_messages)
        except Exception as exc:
            logger.warning("Conversation compression failed | conv=%s | reason=%s", conversation_id, exc)
            return None

    def _compress_conversation(self, conversation_id: str, total_messages: int, max_messages: int) -> str:
        """Generate/update summary for messages that fall outside the recent window.

        Strategy: incremental merge — combine existing summary + newly compressed messages.
        """
        conv = self._store.get_conversation(conversation_id)
        existing_summary = conv.get("summary", "") if conv else ""
        existing_compressed = conv.get("compressed_round_count", 0) if conv else 0

        # Calculate how many messages to compress (all before the recent window)
        messages_to_compress_count = total_messages - max_messages
        # Only compress new messages since last compression
        new_compress_count = messages_to_compress_count - existing_compressed * 2
        if new_compress_count <= 0:
            return existing_summary

        # Fetch the messages that need to be compressed
        new_messages = self._store.get_messages_range(
            conversation_id,
            offset=existing_compressed * 2,
            limit=new_compress_count,
        )

        if not new_messages:
            return existing_summary

        # Build text for summarization
        conversation_text = "\n".join(
            f"{'[用户]' if msg['role'] == 'user' else '[助手]'}: {msg['content']}"
            for msg in new_messages
        )

        summary_prompt = (
            "将以下对话历史压缩为一段简短的摘要，保留关键信息：\n"
            "- 用户生成了什么类型的页面\n"
            "- 用户做了哪些修改\n"
            "- 用户的偏好和反馈\n"
            "- 当前页面的状态\n\n"
        )
        if existing_summary:
            summary_prompt += f"已有摘要：\n{existing_summary}\n\n需要合并的新对话：\n{conversation_text}"
        else:
            summary_prompt += f"对话历史：\n{conversation_text}"

        try:
            from .llm_client import OpenAICompatibleClient

            llm = OpenAICompatibleClient()
            result = llm.generate_json(
                system_prompt="你是一个对话摘要助手。请输出 JSON，包含一个 summary 字段，值为合并后的摘要文本。",
                user_prompt=summary_prompt,
            )
            new_summary = result.get("summary", existing_summary)
        except Exception as exc:
            logger.warning("LLM summary generation failed | conv=%s | reason=%s", conversation_id, exc)
            return existing_summary

        # Update conversation with new summary
        new_compressed_rounds = messages_to_compress_count // 2
        self._store.update_conversation(
            conversation_id,
            summary=new_summary,
            compressed_round_count=new_compressed_rounds,
        )
        logger.info(
            "Conversation compressed | conv=%s | compressed_rounds=%d | summary_len=%d",
            conversation_id, new_compressed_rounds, len(new_summary),
        )
        return new_summary

    def maybe_extract_profile(self, user_id: str) -> dict | None:
        """Extract user profile if message count exceeds trigger threshold.

        Returns the extracted profile dict, or None if not triggered.
        """
        try:
            total = self._store.count_user_messages(user_id)
            if total < settings.profile_extraction_trigger_count:
                return None

            return self.extract_profile(user_id)
        except Exception as exc:
            logger.warning("Profile extraction check failed | user=%s | reason=%s", user_id, exc)
            return None

    def extract_profile(self, user_id: str) -> dict:
        """Extract user profile from conversation history using LLM.

        Returns the saved profile dict.
        """
        from .llm_client import OpenAICompatibleClient

        messages = self._store.get_user_conversation_messages(user_id, limit=50)
        if not messages:
            logger.info("No messages to extract profile from | user=%s", user_id)
            return self._store.get_profile(user_id) or {}

        # Build conversation text for extraction
        conversation_text = "\n".join(
            f"[用户]: {msg['content']}" for msg in reversed(messages)  # chronological order
        )

        extraction_prompt = (
            "根据以下用户与页面生成助手的对话历史，提取用户的页面设计偏好。"
            "输出 JSON，包含以下维度：\n"
            "- style: 偏好的页面风格 (preferred 字符串, history 字符串数组, confidence 0-1)\n"
            "- page_type: 偏好的页面类型 (同上格式)\n"
            "- color_tendency: 色彩倾向 (preferred, evidence 字符串数组, confidence)\n"
            "- topics: 常见主题 (frequent 字符串数组, confidence)\n"
            "- tone: 语气偏好 (preferred, evidence 字符串数组, confidence)\n"
            "如果某维度没有足够证据，confidence 设为 0。\n\n"
            f"对话历史：\n{conversation_text}"
        )

        try:
            llm = OpenAICompatibleClient()
            result = llm.generate_json(
                system_prompt="你是一个用户偏好分析助手。请严格按照要求的 JSON 格式输出。",
                user_prompt=extraction_prompt,
            )
        except Exception as exc:
            logger.warning("LLM profile extraction failed | user=%s | reason=%s", user_id, exc)
            return self._store.get_profile(user_id) or {}

        # Merge with existing profile
        existing = self._store.get_profile(user_id)
        existing_prefs = existing.get("preferences", {}) if existing else {}
        existing_sources = existing.get("source_conversation_ids", []) if existing else []

        # Get conversation IDs that contributed
        conv_ids = list(set(msg.get("conversation_id", "") for msg in messages if msg.get("conversation_id")))

        # Merge: new extraction overwrites existing for dimensions with higher confidence
        merged = self._merge_preferences(existing_prefs, result)

        return self._store.save_profile(
            user_id=user_id,
            preferences=merged,
            source_conversation_ids=list(set(existing_sources + conv_ids)),
        )

    def _merge_preferences(self, existing: dict, new: dict) -> dict:
        """Merge new preference extraction with existing profile.

        For each dimension, keep the one with higher confidence.
        """
        merged = {}
        for dim in ("style", "page_type", "color_tendency", "topics", "tone"):
            existing_dim = existing.get(dim, {})
            new_dim = new.get(dim, {})

            existing_conf = existing_dim.get("confidence", 0) if isinstance(existing_dim, dict) else 0
            new_conf = new_dim.get("confidence", 0) if isinstance(new_dim, dict) else 0

            if new_conf >= existing_conf:
                merged[dim] = new_dim
            else:
                merged[dim] = existing_dim

        return merged

    def _generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for a text. Returns None on failure."""
        try:
            from .embedding_client import encode

            return encode([text], text_type="document")[0]
        except Exception as exc:
            logger.warning("Embedding generation failed | reason=%s", exc)
            return None

    def save_user_message(
        self, conversation_id: str, content: str, metadata: dict | None = None
    ) -> dict:
        """Save a user message and update conversation title if first message."""
        # Generate embedding for user messages if search is enabled
        embedding = None
        if settings.search_enabled and settings.search_embed_messages:
            embedding = self._generate_embedding(content)

        msg = self._store.add_message(
            conversation_id, role="user", content=content, metadata=metadata, embedding=embedding
        )
        # Set conversation title from first user message
        conv = self._store.get_conversation(conversation_id)
        if conv and not conv.get("title"):
            title = content[:20]
            self._store.update_conversation(conversation_id, title=title)
        return msg

    def search_conversations(self, user_id: str, query: str, limit: int | None = None) -> tuple[list[dict], int]:
        """Search user's conversations using hybrid retrieval.

        Returns (results, total).
        """
        if not settings.search_enabled:
            return [], 0

        k = limit or settings.search_top_k

        # Generate query embedding
        query_embedding = None
        try:
            from .embedding_client import encode

            query_embedding = encode([query], text_type="query")[0]
        except Exception as exc:
            logger.warning("Query embedding failed, falling back to BM25 only | reason=%s", exc)

        return self._store.search_conversations(
            user_id=user_id,
            query_text=query,
            query_embedding=query_embedding,
            limit=k,
        )

    # -- Intent detection: 3-tier strategy (fast-path → zero-signal → LLM) --

    # Tier 1: strong signals — direct return, no LLM needed
    _strong_gen_patterns = (
        "生成一个", "创建一个", "帮我做一个", "给我做一个", "做一页",
        "建一个", "帮我生成", "给我生成", "写一个页面", "帮我做一页",
        "做一版", "出一个", "产出一版",
    )
    _revision_verbs = (
        "改", "换", "调整", "修改", "替换", "删除", "移除", "添加", "增加",
        "加大", "缩小", "变更", "强化",
    )
    _revision_targets = (
        "标题", "颜色", "配色", "字体", "布局", "按钮", "文案", "图片",
        "背景", "样式", "风格", "色调", "模块", "组件", "内容", "排版",
        "间距", "图标", "logo", "banner", "hero", "cta", "footer", "header",
        "副标题", "主标题", "描述", "卖点",
    )
    # Tier 2: zero signal detection — any keyword at all
    _all_page_keywords = (
        "生成", "创建", "制作", "设计", "落地页", "页面", "推广页", "做一个", "建一个",
        "写一个", "帮我做", "帮我生成", "给我做", "做一页", "做一版",
        "改", "修改", "换", "换成", "调整", "变成", "移除", "删除", "添加", "增加",
        "替换", "变更", "变小", "变大", "颜色", "字体", "布局", "标题", "内容",
        "样式", "风格", "色调", "按钮", "文案", "图片", "背景", "模块", "组件",
        "商务", "科技", "简洁", "大气", "高端", "年轻", "活泼", "正式", "温馨",
        "信任感", "专业", "现代", "极简", "炫酷", "可爱", "清爽",
    )

    def detect_intent(self, conversation_id: str, current_content: str) -> IntentType:
        """3-tier intent detection:
        1. Strong signals → direct return (fast & free)
        2. Zero signal → direct chat (fast & free)
        3. Weak/ambiguous → LLM classification
        """
        conv = self._store.get_conversation(conversation_id)
        if conv is None:
            logger.info("Intent detection | tier=0 | conv_not_found, defaulting to generate")
            return "generate"

        has_page = bool(conv.get("page_id"))
        content = current_content

        # Tier 1: check strong signals
        strong_result = self._check_strong_signals(content, has_page)
        if strong_result is not None:
            logger.info(
                "Intent detection | tier=1 | intent=%s | reason=strong_signal | content=%.60s",
                strong_result, content,
            )
            return strong_result

        # Tier 2: check zero signal — if nothing page-related at all, it's chat
        if not any(kw in content for kw in self._all_page_keywords) and len(content) < 15:
            logger.info(
                "Intent detection | tier=2 | intent=chat | reason=zero_signal | content=%.60s",
                content,
            )
            return "chat"

        # Tier 3: weak/ambiguous signal → LLM
        logger.info(
            "Intent detection | tier=3 | using LLM classification | has_page=%s | content=%.60s",
            has_page, content,
        )
        try:
            intent = self._llm_detect_intent(content, has_page)
            logger.info("Intent detection | tier=3 | intent=%s | source=LLM", intent)
            return intent
        except Exception:
            logger.warning("LLM intent detection failed, falling back to keywords")
            intent = self._fallback_detect_intent(content, has_page)
            logger.info("Intent detection | tier=3-fallback | intent=%s | source=keywords", intent)
            return intent

    def _check_strong_signals(self, content: str, has_page: bool) -> IntentType | None:
        """Return intent if strong signal detected, None otherwise."""
        # Strong generation: complete phrase like "生成一个科技落地页"
        matched_gen = [p for p in self._strong_gen_patterns if p in content]
        if matched_gen:
            logger.debug("Strong gen signal matched | patterns=%s", matched_gen)
            return "generate"

        # Strong revision: verb + target noun, e.g. "改标题", "换成蓝色"
        # First, strip false-positive phrases where revision verbs appear in
        # unrelated contexts (e.g. "改天" means "another day", not "modify")
        cleaned = content
        for noise in ("改天", "改变世界", "改不了"):
            cleaned = cleaned.replace(noise, "")
        matched_verbs = [v for v in self._revision_verbs if v in cleaned]
        matched_targets = [t for t in self._revision_targets if t in content]
        if matched_verbs and matched_targets:
            logger.debug(
                "Strong rev signal matched | verbs=%s | targets=%s",
                matched_verbs, matched_targets,
            )
            return "revise" if has_page else "generate"

        return None

    def _llm_detect_intent(self, content: str, has_page: bool) -> IntentType:
        """Use LLM to classify user intent as generate / revise / chat."""
        from .llm_client import OpenAICompatibleClient

        context_hint = "当前正在编辑一个已有页面" if has_page else "尚未创建页面"

        system_prompt = (
            "你是一个意图分类器。根据用户输入判断其意图，仅输出 JSON 格式，不要输出其他内容。\n\n"
            "意图类型（三选一）：\n"
            "- generate: 用户想要生成/创建一个全新的页面\n"
            "- revise: 用户想要修改/调整/优化当前页面的内容、样式、布局、文案等\n"
            "- chat: 用户在进行闲聊、打招呼、问问题、或其他与页面操作无关的对话\n\n"
            f"参考信息：{context_hint}\n\n"
            '输出格式：{{"intent": "generate"}} 或 {{"intent": "revise"}} 或 {{"intent": "chat"}}'
        )

        llm = OpenAICompatibleClient()
        result = llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=f"用户说：{content}",
        )
        intent = result.get("intent", "chat")
        if intent not in ("generate", "revise", "chat"):
            logger.warning("LLM returned unknown intent=%s, defaulting to chat", intent)
            return "chat"
        return intent

    # -- Fallback: keyword matching when LLM unavailable --

    _gen_keywords = (
        "生成", "创建", "制作", "设计", "落地页", "页面", "推广页", "做一个", "建一个",
        "写一个", "帮我做", "帮我生成", "给我做",
    )
    _rev_keywords = (
        "改", "修改", "换", "换成", "调整", "变成", "移除", "删除", "添加", "增加",
        "替换", "变更", "变小", "变大", "颜色", "字体", "布局", "标题", "内容",
        "样式", "风格", "色调", "按钮", "文案", "图片", "背景", "模块", "组件",
    )

    def _fallback_detect_intent(self, content: str, has_page: bool) -> IntentType:
        """Fallback keyword-based intent detection (LLM unavailable)."""
        has_gen = any(kw in content for kw in self._gen_keywords)
        has_rev = any(kw in content for kw in self._rev_keywords)

        if has_page:
            if has_rev:
                return "revise"
            if has_gen:
                return "generate"
            return "chat"

        if has_rev:
            return "revise"
        if has_gen:
            return "generate"
        return "chat"
