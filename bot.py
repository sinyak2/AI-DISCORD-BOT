from __future__ import annotations

import argparse
import logging
import random

import discord

from config import AppConfig, ConfigError, load_config
from media import message_has_enabled_media, prepare_media
from openai_service import OpenAIService, ReplyGenerationError


logger = logging.getLogger(__name__)


def split_discord_message(text: str, limit: int) -> list[str]:
    """Split a reply without cutting words when possible."""
    remaining = text.strip()
    chunks: list[str] = []

    while len(remaining) > limit:
        newline_at = remaining.rfind("\n", 0, limit + 1)
        space_at = remaining.rfind(" ", 0, limit + 1)
        split_at = max(newline_at, space_at)
        if split_at < limit // 2:
            split_at = limit

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


class DiscordAIBot(discord.Client):
    def __init__(self, config: AppConfig) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.config = config
        self.ai = OpenAIService(config.openai, config.bot)

    async def close(self) -> None:
        await self.ai.close()
        await super().close()

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s | model=%s | read_all_messages=%s | decision_filter=%s",
            self.user,
            self.config.openai.model,
            self.config.bot.read_all_messages,
            self.config.bot.decision_filter_enabled,
        )

    async def _is_reply_to_me(self, message: discord.Message) -> bool:
        if self.user is None or message.reference is None:
            return False

        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author.id == self.user.id

        cached = getattr(message.reference, "cached_message", None)
        if isinstance(cached, discord.Message):
            return cached.author.id == self.user.id

        message_id = message.reference.message_id
        fetch_message = getattr(message.channel, "fetch_message", None)
        if message_id is None or fetch_message is None:
            return False

        try:
            referenced = await fetch_message(message_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return False
        return referenced.author.id == self.user.id

    async def _recent_context(self, message: discord.Message) -> str:
        requested = self.config.bot.context_messages
        if requested == 0:
            return ""

        rows: list[str] = []
        try:
            async for item in message.channel.history(
                limit=max(requested * 2, requested), before=message
            ):
                text = item.clean_content.strip()
                if item.attachments or item.embeds:
                    media_count = len(item.attachments) + len(item.embeds)
                    text = f"{text} [media: {media_count}]".strip()
                if not text:
                    continue

                rows.append(f"{item.author.display_name}: {text}")
                if len(rows) == requested:
                    break
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not read message history in channel %s", message.channel)
            return ""

        rows.reverse()
        return "\n".join(rows)

    async def _select_message(
        self, message: discord.Message
    ) -> tuple[bool, bool, str]:
        if message.author.bot:
            return False, False, "message author is a bot"

        replied_to_bot = await self._is_reply_to_me(message)
        if replied_to_bot and self.config.bot.reply_to_replies:
            return True, True, "reply to the bot"

        mentioned = self.user is not None and self.user in message.mentions
        if mentioned and self.config.bot.reply_to_mentions:
            return True, True, "bot mention"

        has_text = bool(message.clean_content.strip())
        has_media = message_has_enabled_media(message, self.config.media)
        if not has_text and not has_media:
            return False, False, "no supported content"

        if has_media and self.config.media.media_messages_are_candidates:
            return True, False, "enabled media"

        if has_text and self.config.bot.read_all_messages:
            return True, False, "read_all_messages is enabled"

        chance = self.config.bot.random_response_chance
        roll = random.random()
        if roll < chance:
            return True, False, f"random selection ({roll:.3f} < {chance:.3f})"
        return False, False, f"random skip ({roll:.3f} >= {chance:.3f})"

    async def on_message(self, message: discord.Message) -> None:
        selected, force_reply, reason = await self._select_message(message)
        if not selected:
            logger.debug("Skipped message %s: %s", message.id, reason)
            return

        logger.info(
            "Selected message %s from %s: %s",
            message.id,
            message.author.display_name,
            reason,
        )

        async with message.channel.typing():
            try:
                context = await self._recent_context(message)
                media = await prepare_media(message, self.config.media)
                reply = await self.ai.create_reply(
                    author_name=message.author.display_name,
                    message_text=message.clean_content.strip(),
                    recent_context=context,
                    media=media,
                    force_reply=force_reply,
                )
            except ReplyGenerationError as exc:
                logger.error("Could not generate a reply for message %s: %s", message.id, exc)
                return
            except Exception:
                logger.exception("Unexpected error while handling message %s", message.id)
                return

        if reply is None:
            logger.info("The model chose not to reply to message %s", message.id)
            return

        chunks = split_discord_message(reply, self.config.bot.max_discord_chars)
        if not chunks:
            logger.warning("Generated reply for message %s was empty", message.id)
            return

        try:
            await message.reply(chunks[0], mention_author=False)
            for chunk in chunks[1:]:
                await message.channel.send(chunk)
        except discord.HTTPException as exc:
            logger.error("Discord could not send the reply to message %s: %s", message.id, exc)
            return

        logger.info("Sent %s reply chunk(s) for message %s", len(chunks), message.id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multimodal Discord bot powered by OpenAI")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="path to the TOML config file (default: config.toml)",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate the config and exit without connecting to Discord",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    logging.basicConfig(
        level=getattr(logging, config.bot.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.check_config:
        logger.info("Config is valid. Selected model: %s", config.openai.model)
        return

    bot = DiscordAIBot(config)
    bot.run(config.discord.token, log_handler=None)


if __name__ == "__main__":
    main()
