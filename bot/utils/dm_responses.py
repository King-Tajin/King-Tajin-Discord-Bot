import random
import re
import discord

OK_TEXTS = [
    "ok",
    "okay",
    "okie",
    "ok.",
    "okay.",
    "okie dokie",
    "oki",
    "okk",
    "k",
    "sure",
    "alright",
    "ok ok",
    "mhmm okaaaaay",
    "yep",
    "yeah ok",
]

OK_EMOJIS = [
    "👍",
    "👌",
    "✅",
    "🆗",
    "😐",
    "😶",
    "😑",
    "👍👍",
]

OK_GIFS = [
    "https://klipy.com/gifs/ok-20293",
    "https://klipy.com/gifs/spongebob-wink-1",
    "https://klipy.com/gifs/be-happy-129",
]

SUPPORT_KEYWORDS = [
    "feedback",
    "support",
    "bug",
    "issue",
    "problem",
    "report",
    "help",
    "suggest",
    "complaint",
    "contact",
    "review",
]

GIF_DOMAINS = re.compile(
    r'https?://(?:www\.)?(?:'
    r'tenor\.com|c\.tenor\.com|media\.tenor\.com'
    r'|giphy\.com|i\.giphy\.com|media\.giphy\.com'
    r'|klipy\.com'
    r')\S*',
    re.IGNORECASE
)

CUSTOM_EMOJI_RE = re.compile(r'<a?:[a-zA-Z0-9_]+:[0-9]+>')

UNICODE_EMOJI_RE = re.compile(
    '['
    '\U0001F000-\U0001FFFF'
    '\U00002300-\U000027BF'
    '\U00002900-\U00002BFF'
    '\U0001F1E0-\U0001F1FF'
    '\U0001F3FB-\U0001F3FF'
    '\u20E3'
    ']+',
    flags=re.UNICODE
)

RESIDUAL_RE = re.compile(r'[\uFE00-\uFE0F\u200D\uFEFF\u20D0-\u20FF\s]+')

GIF_EMBED_TYPES = {"gifv", "gif"}
GIF_CONTENT_TYPES = {"image/gif", "video/mp4"}


def _is_gif_embed(embed) -> bool:
    if embed.type in GIF_EMBED_TYPES:
        return True
    url = str(embed.url or "")
    if GIF_DOMAINS.search(url):
        return True
    return False


def is_support_message(message) -> bool:
    content = message.content.strip()
    if re.match(r'^https?://\S+$', content):
        return False
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in SUPPORT_KEYWORDS)


def analyze_message(message) -> tuple[bool, bool, bool]:
    has_gif = False
    has_emoji = False
    has_text = False

    for embed in message.embeds:
        if _is_gif_embed(embed):
            has_gif = True

    for attachment in message.attachments:
        ct = attachment.content_type or ""
        if any(ct.startswith(t) for t in GIF_CONTENT_TYPES):
            has_gif = True
        elif attachment.filename.lower().endswith(".gif"):
            has_gif = True

    content = message.content
    content = GIF_DOMAINS.sub("", content)

    if CUSTOM_EMOJI_RE.search(content):
        has_emoji = True
    content = CUSTOM_EMOJI_RE.sub("", content)

    if UNICODE_EMOJI_RE.search(content):
        has_emoji = True
    content = UNICODE_EMOJI_RE.sub("", content)

    content = RESIDUAL_RE.sub("", content).strip()

    if content:
        has_text = True

    return has_text, has_emoji, has_gif


def get_text_response() -> str:
    return random.choice(OK_TEXTS)


def get_emoji_response() -> str:
    return random.choice(OK_EMOJIS)


def get_gif_response() -> str:
    return random.choice(OK_GIFS)


def get_support_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Need help or want to leave feedback?",
        description="You can reach out through either of these:",
        color=0xFFD700
    )
    embed.add_field(
        name="📧 Email",
        value="[support@king-tajin.dev](mailto:support@king-tajin.dev)",
        inline=False
    )
    embed.add_field(
        name="🌐 Feedback Form",
        value="https://king-tajin.dev/feedback",
        inline=False
    )
    embed.set_footer(text="All feedback is reviewed and directly influences future updates!")
    return embed