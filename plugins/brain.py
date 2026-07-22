"""
plugins/brain.py  —  Udom AI Self-Learning Brain
==================================================
• Maintains a persistent JSON knowledge base (bot_brain.json)
• Automatically researches the internet every 6 hours on useful topics
• Learns from every user interaction (Q&A memory)
• Injects relevant learned context into AI responses for better answers
• Exposes /train and /brainstats Telegram commands
"""

import os
import json
import asyncio
import re
from datetime import datetime, timezone

BRAIN_FILE = os.path.join(os.path.dirname(__file__), "..", "bot_brain.json")

# ─── All bot features / commands Udom knows about ─────────────────────────────
BOT_FEATURE_MAP = {
    "/download <link>": "Download video/audio from YouTube, TikTok, Facebook, Instagram, Twitter and 1000+ sites. Supports up to 3 hours. Also works by sending a URL directly.",
    "/ask <question>": "Ask Udom AI any question. Supports text, images (send photo), documents (PDF, Word, Excel, PPT), audio and video analysis.",
    "/image <description>": "Generate a professional Full HD 1920x1080 AI image using FLUX. Subject-aware: portrait, landscape, food, product, fantasy, interior, wildlife modes.",
    "/search <query>": "Live web search via DuckDuckGo. Returns real-time results with AI-summarized answer.",
    "/convert": "Convert video/audio formats. Send a file and use the Convert button.",
    "AI Voice Dub & Translate": "Send a video/audio file or link → click 'Voice Dub & Translate' → choose language (Khmer/English/Chinese/French/Spanish/Japanese). Replaces original speech with translated dubbed voice. Background music preserved at 20%.",
    "AI Video Recap": "Send a video/audio file or link → click 'AI Video/Audio Recap' → choose language. Generates a short 5-10 sentence spoken summary voiceover.",
    "Video Clipper": "Send a video → click 'Cut into Clips' or type a number. Splits video into 1-10 equal segments.",
    "Document/PDF Parser": "Send any PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx) file and ask questions about it.",
    "Image/OCR Analysis": "Send any image and ask Udom to describe, analyze, or extract text from it.",
    "Audio Transcription": "Send an audio/voice file — Udom transcribes it with exact verbatim speech using Gemini 2.0 AI.",
    "/timezone <offset>": "Set your local timezone offset, e.g. /timezone +7 for Cambodia/Thailand time.",
}

# ─── Topics the bot auto-researches to improve itself ─────────────────────────
AUTO_RESEARCH_TOPICS = [
    "AI chatbot best practices 2025",
    "yt-dlp YouTube download tips 2025",
    "FFmpeg audio video processing tricks",
    "gTTS text to speech quality improvements",
    "Gemini AI API features 2025",
    "FLUX AI image generation prompts",
    "Python asyncio performance optimization",
    "Telegram bot user experience tips",
    "speech recognition accuracy improvements",
    "video dubbing synchronization techniques",
]


# ══════════════════════════════════════════════════════════════════════════════
class BotBrain:
    """Persistent self-learning knowledge base for Udom AI."""

    def __init__(self):
        self._brain = self._load()

    # ── Persistence ──────────────────────────────────────────────────────────
    def _load(self) -> dict:
        if os.path.exists(BRAIN_FILE):
            try:
                with open(BRAIN_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "version": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_trained": None,
            "total_interactions": 0,
            "knowledge": {},          # topic -> [{"fact", "source", "ts", "uses"}]
            "qa_memory": [],          # [{q, a, ts}]  — capped at 300
            "user_patterns": {},      # phrase -> count
            "research_log": [],       # [{topic, ts, facts_added}]
        }

    def _save(self):
        try:
            with open(BRAIN_FILE, "w", encoding="utf-8") as f:
                json.dump(self._brain, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Brain] Save error: {e}")

    # ── Learning ─────────────────────────────────────────────────────────────
    def learn(self, topic: str, fact: str, source: str = "interaction"):
        """Add a fact about a topic to the knowledge base."""
        topic = topic.lower().strip()[:80]
        fact = fact.strip()[:600]
        if not fact:
            return

        kb = self._brain["knowledge"]
        if topic not in kb:
            kb[topic] = []

        existing = {e["fact"] for e in kb[topic]}
        if fact in existing:
            return  # deduplicate

        kb[topic].append({
            "fact": fact,
            "source": source,
            "ts": datetime.now(timezone.utc).isoformat(),
            "uses": 0,
        })

        # Keep top 60 most-used facts per topic
        if len(kb[topic]) > 60:
            kb[topic] = sorted(kb[topic], key=lambda x: x.get("uses", 0), reverse=True)[:60]

        self._save()

    def recall(self, query: str, max_facts: int = 4) -> list[str]:
        """Find relevant learned facts for a given query."""
        q_words = set(re.sub(r"[^\w\s]", " ", query.lower()).split())
        scored = []

        for topic, facts in self._brain["knowledge"].items():
            t_words = set(topic.split())
            overlap = len(q_words & t_words)
            if overlap > 0:
                for fact in facts:
                    scored.append((overlap + fact.get("uses", 0) * 0.1, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        chosen = [item[1] for _, item in scored[:max_facts]]

        # Increment usage counter
        for item in chosen:
            item["uses"] = item.get("uses", 0) + 1
        if chosen:
            self._save()

        return [item["fact"] for item in chosen]

    def record_interaction(self, question: str, answer: str):
        """Record a successful Q&A for memory and pattern learning."""
        self._brain["total_interactions"] = self._brain.get("total_interactions", 0) + 1

        # Q&A memory (capped at 300)
        qa = self._brain["qa_memory"]
        qa.append({"q": question[:250], "a": answer[:600], "ts": datetime.now(timezone.utc).isoformat()})
        if len(qa) > 300:
            self._brain["qa_memory"] = qa[-300:]

        # Track common query patterns (first 4 words)
        key = " ".join(question.lower().split()[:4])
        self._brain["user_patterns"][key] = self._brain["user_patterns"].get(key, 0) + 1

        # Auto-learn topics from question keywords
        for word in question.lower().split():
            if len(word) > 5:
                self.learn(word, f"User frequently asks about: {question[:120]}", "pattern")

        self._save()

    # ── Internet Research ─────────────────────────────────────────────────────
    async def auto_research(self, topics: list[str] | None = None, limit: int = 5) -> list[str]:
        """Search the internet and store findings in the knowledge base."""
        from duckduckgo_search import DDGS

        if topics is None:
            topics = AUTO_RESEARCH_TOPICS

        researched = []
        for topic in topics[:limit]:
            try:
                results = DDGS().text(topic, max_results=4)
                facts_added = 0
                for r in results:
                    fact = f"{r.get('title', '').strip()}: {r.get('body', '').strip()[:350]}"
                    if len(fact) > 20:
                        self.learn(topic, fact, source="web_research")
                        facts_added += 1

                self._brain["research_log"].append({
                    "topic": topic,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "facts_added": facts_added,
                })
                if len(self._brain["research_log"]) > 100:
                    self._brain["research_log"] = self._brain["research_log"][-100:]

                researched.append(f"✅ {topic} ({facts_added} facts)")
                await asyncio.sleep(1.5)  # Polite delay between searches
            except Exception as e:
                print(f"[Brain] Research error '{topic}': {e}")
                researched.append(f"❌ {topic}: {e}")

        self._brain["last_trained"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return researched

    # ── Stats ─────────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        total_facts = sum(len(v) for v in self._brain["knowledge"].values())
        top_patterns = sorted(
            self._brain["user_patterns"].items(), key=lambda x: x[1], reverse=True
        )[:5]
        return {
            "total_interactions": self._brain.get("total_interactions", 0),
            "knowledge_topics": len(self._brain["knowledge"]),
            "total_facts": total_facts,
            "qa_memory_size": len(self._brain["qa_memory"]),
            "last_trained": self._brain.get("last_trained", "Never"),
            "research_sessions": len(self._brain.get("research_log", [])),
            "top_patterns": top_patterns,
        }

    def build_context_for_query(self, query: str) -> str:
        """Build a context string from learned facts relevant to the query."""
        facts = self.recall(query, max_facts=4)
        if not facts:
            return ""
        lines = ["[Udom Learned Knowledge]"] + [f"• {f}" for f in facts]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Global singleton
bot_brain = BotBrain()


# ══════════════════════════════════════════════════════════════════════════════
# Background auto-training loop
async def auto_training_loop():
    """Runs indefinitely; researches the web every 6 hours to improve the bot."""
    while True:
        try:
            await asyncio.sleep(6 * 3600)  # Wait 6 hours first
            print("[Brain] 🧠 Starting auto-training research session...")
            results = await bot_brain.auto_research(AUTO_RESEARCH_TOPICS, limit=5)
            print(f"[Brain] Auto-training complete: {results}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Brain] Auto-training loop error: {e}")
            await asyncio.sleep(3600)  # Retry in 1 hour on error


# ══════════════════════════════════════════════════════════════════════════════
# Telegram command handlers
from pyrogram import Client, filters
from pyrogram.types import Message
from plugins.handlers import RealtimeTimer


@Client.on_message(filters.command("train"), group=1)
async def train_command(client: Client, message: Message):
    """
    /train — triggers an immediate internet research session.
    /train <topic> — researches a specific topic.
    """
    if len(message.command) > 1:
        custom_topic = " ".join(message.command[1:])
        topics = [custom_topic]
        reply_header = f"🔬 Researching: `{custom_topic}`"
    else:
        topics = AUTO_RESEARCH_TOPICS[:5]
        reply_header = "🧠 Starting full auto-training research session..."

    proc = await message.reply_text(f"⏱ [00:00] {reply_header}")
    try:
        async with RealtimeTimer(proc, f"🧠 Udom is researching & learning"):
            results = await bot_brain.auto_research(topics, limit=len(topics))

        stats = bot_brain.stats()
        result_text = "\n".join(results)
        report = (
            f"✅ **Training Complete!**\n\n"
            f"**Research Results:**\n{result_text}\n\n"
            f"📊 **Brain Stats:**\n"
            f"• Total interactions: `{stats['total_interactions']}`\n"
            f"• Knowledge topics: `{stats['knowledge_topics']}`\n"
            f"• Total facts: `{stats['total_facts']}`\n"
            f"• Q&A memory: `{stats['qa_memory_size']}` pairs\n"
            f"• Research sessions: `{stats['research_sessions']}`\n"
            f"• Last trained: `{stats['last_trained'][:19] if stats['last_trained'] != 'Never' else 'Never'}`"
        )
        await proc.edit_text(report)
    except Exception as e:
        await proc.edit_text(f"❌ Training error: {e}")


@Client.on_message(filters.command("brainstats"), group=1)
async def brainstats_command(client: Client, message: Message):
    """
    /brainstats — shows the current brain knowledge base statistics.
    """
    stats = bot_brain.stats()
    top = "\n".join(f"  `{p}` — {c}x" for p, c in stats["top_patterns"]) or "  None yet"
    features = "\n".join(f"• `{cmd}`: {desc[:80]}..." if len(desc) > 80 else f"• `{cmd}`: {desc}"
                         for cmd, desc in BOT_FEATURE_MAP.items())

    text = (
        f"🧠 **Udom AI Brain Statistics**\n\n"
        f"📊 **Learning Progress:**\n"
        f"• Total interactions learned: `{stats['total_interactions']}`\n"
        f"• Knowledge topics: `{stats['knowledge_topics']}`\n"
        f"• Total stored facts: `{stats['total_facts']}`\n"
        f"• Q&A memory pairs: `{stats['qa_memory_size']}`\n"
        f"• Research sessions run: `{stats['research_sessions']}`\n"
        f"• Last trained: `{stats['last_trained'][:19] if stats['last_trained'] != 'Never' else 'Never'}`\n\n"
        f"🔝 **Top User Patterns:**\n{top}\n\n"
        f"⚡ **All Bot Features:**\n{features}\n\n"
        f"_Use `/train` to trigger a new research session now._\n"
        f"_Bot auto-trains every 6 hours from the internet._"
    )
    await message.reply_text(text)
