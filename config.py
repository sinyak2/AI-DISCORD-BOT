from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
    """Raised when config.toml is missing or contains invalid values."""


@dataclass(frozen=True)
class DiscordSettings:
    token: str


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str
    model: str
    max_output_tokens: int
    request_timeout_seconds: float


@dataclass(frozen=True)
class BotSettings:
    persona: str
    reply_to_mentions: bool
    reply_to_replies: bool
    read_all_messages: bool
    random_response_chance: float
    decision_filter_enabled: bool
    context_messages: int
    max_discord_chars: int
    log_level: str


@dataclass(frozen=True)
class MediaSettings:
    analyze_images: bool
    analyze_gifs: bool
    analyze_videos: bool
    media_messages_are_candidates: bool
    max_download_mb: int
    max_media_per_message: int
    max_image_side: int
    image_detail: str
    gif_frames: int
    video_frames: int
    video_sample_interval_seconds: float
    download_timeout_seconds: float


@dataclass(frozen=True)
class AppConfig:
    discord: DiscordSettings
    openai: OpenAISettings
    bot: BotSettings
    media: MediaSettings


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing section [{name}] in config.toml")
    return value


def _required_string(section: dict[str, Any], key: str, section_name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"[{section_name}].{key} must be a non-empty string")
    return value.strip()


def _value(section: dict[str, Any], key: str, expected_type: type, section_name: str) -> Any:
    if key not in section:
        raise ConfigError(f"Missing [{section_name}].{key} in config.toml")

    value = section[key]
    if expected_type is int and isinstance(value, bool):
        raise ConfigError(f"[{section_name}].{key} must be an integer")
    if expected_type is float and isinstance(value, bool):
        raise ConfigError(f"[{section_name}].{key} must be a number")
    if expected_type is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, expected_type):
        type_name = "a number" if expected_type is float else expected_type.__name__
        raise ConfigError(f"[{section_name}].{key} must be {type_name}")
    return value


def _reject_placeholder(value: str, field_name: str) -> None:
    normalized = value.lower().replace("-", "_")
    placeholders = ("your_", "paste_", "change_me", "replace_me", "__migrate_")
    if normalized.startswith(placeholders):
        raise ConfigError(f"Set a real value for {field_name} in config.toml")


def load_config(path: str | Path = "config.toml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Copy config.example.toml to config.toml and fill in the tokens."
        )

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot read {config_path}: {exc}") from exc

    discord_data = _section(data, "discord")
    openai_data = _section(data, "openai")
    bot_data = _section(data, "bot")
    media_data = _section(data, "media")

    discord_token = _required_string(discord_data, "token", "discord")
    openai_api_key = _required_string(openai_data, "api_key", "openai")
    model = _required_string(openai_data, "model", "openai")
    persona = _required_string(bot_data, "persona", "bot")

    _reject_placeholder(discord_token, "[discord].token")
    _reject_placeholder(openai_api_key, "[openai].api_key")

    max_output_tokens = _value(openai_data, "max_output_tokens", int, "openai")
    request_timeout = _value(
        openai_data, "request_timeout_seconds", float, "openai"
    )
    response_chance = _value(
        bot_data, "random_response_chance", float, "bot"
    )
    context_messages = _value(bot_data, "context_messages", int, "bot")
    max_discord_chars = _value(bot_data, "max_discord_chars", int, "bot")
    log_level = _required_string(bot_data, "log_level", "bot").upper()

    max_download_mb = _value(media_data, "max_download_mb", int, "media")
    max_media = _value(media_data, "max_media_per_message", int, "media")
    max_image_side = _value(media_data, "max_image_side", int, "media")
    image_detail = _required_string(media_data, "image_detail", "media").lower()
    gif_frames = _value(media_data, "gif_frames", int, "media")
    video_frames = _value(media_data, "video_frames", int, "media")
    video_interval = _value(
        media_data, "video_sample_interval_seconds", float, "media"
    )
    download_timeout = _value(
        media_data, "download_timeout_seconds", float, "media"
    )

    if max_output_tokens <= 0:
        raise ConfigError("[openai].max_output_tokens must be greater than 0")
    if request_timeout <= 0:
        raise ConfigError("[openai].request_timeout_seconds must be greater than 0")
    if not 0.0 <= response_chance <= 1.0:
        raise ConfigError("[bot].random_response_chance must be between 0.0 and 1.0")
    if context_messages < 0:
        raise ConfigError("[bot].context_messages cannot be negative")
    if not 100 <= max_discord_chars <= 2000:
        raise ConfigError("[bot].max_discord_chars must be between 100 and 2000")
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("[bot].log_level must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
    if max_download_mb <= 0:
        raise ConfigError("[media].max_download_mb must be greater than 0")
    if not 1 <= max_media <= 10:
        raise ConfigError("[media].max_media_per_message must be between 1 and 10")
    if not 256 <= max_image_side <= 4096:
        raise ConfigError("[media].max_image_side must be between 256 and 4096")
    if image_detail not in {"low", "high", "auto", "original"}:
        raise ConfigError("[media].image_detail must be low, high, auto or original")
    if not 1 <= gif_frames <= 12:
        raise ConfigError("[media].gif_frames must be between 1 and 12")
    if not 1 <= video_frames <= 12:
        raise ConfigError("[media].video_frames must be between 1 and 12")
    if video_interval <= 0:
        raise ConfigError("[media].video_sample_interval_seconds must be greater than 0")
    if download_timeout <= 0:
        raise ConfigError("[media].download_timeout_seconds must be greater than 0")

    return AppConfig(
        discord=DiscordSettings(token=discord_token),
        openai=OpenAISettings(
            api_key=openai_api_key,
            model=model,
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=request_timeout,
        ),
        bot=BotSettings(
            persona=persona,
            reply_to_mentions=_value(
                bot_data, "reply_to_mentions", bool, "bot"
            ),
            reply_to_replies=_value(bot_data, "reply_to_replies", bool, "bot"),
            read_all_messages=_value(bot_data, "read_all_messages", bool, "bot"),
            random_response_chance=response_chance,
            decision_filter_enabled=_value(
                bot_data, "decision_filter_enabled", bool, "bot"
            ),
            context_messages=context_messages,
            max_discord_chars=max_discord_chars,
            log_level=log_level,
        ),
        media=MediaSettings(
            analyze_images=_value(media_data, "analyze_images", bool, "media"),
            analyze_gifs=_value(media_data, "analyze_gifs", bool, "media"),
            analyze_videos=_value(media_data, "analyze_videos", bool, "media"),
            media_messages_are_candidates=_value(
                media_data, "media_messages_are_candidates", bool, "media"
            ),
            max_download_mb=max_download_mb,
            max_media_per_message=max_media,
            max_image_side=max_image_side,
            image_detail=image_detail,
            gif_frames=gif_frames,
            video_frames=video_frames,
            video_sample_interval_seconds=video_interval,
            download_timeout_seconds=download_timeout,
        ),
    )
