import tempfile
import textwrap
import unittest
from pathlib import Path

from config import ConfigError, load_config


VALID_CONFIG = textwrap.dedent(
    """
    [discord]
    token = "discord-test-token"

    [openai]
    api_key = "sk-test-key"
    model = "gpt-5.4-nano"
    max_output_tokens = 800
    request_timeout_seconds = 30.0

    [bot]
    persona = "A concise test persona"
    reply_to_mentions = true
    reply_to_replies = true
    read_all_messages = false
    random_response_chance = 0.25
    decision_filter_enabled = true
    context_messages = 0
    max_discord_chars = 1900
    log_level = "INFO"

    [media]
    analyze_images = true
    analyze_gifs = true
    analyze_videos = true
    media_messages_are_candidates = true
    max_download_mb = 25
    max_media_per_message = 3
    max_image_side = 1280
    image_detail = "low"
    gif_frames = 4
    video_frames = 4
    video_sample_interval_seconds = 1.0
    download_timeout_seconds = 20.0
    """
)


class ConfigTests(unittest.TestCase):
    def _write_config(self, content: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "config.toml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_loads_valid_config(self) -> None:
        config = load_config(self._write_config(VALID_CONFIG))

        self.assertEqual(config.openai.model, "gpt-5.4-nano")
        self.assertEqual(config.bot.context_messages, 0)
        self.assertTrue(config.media.analyze_gifs)

    def test_rejects_invalid_probability(self) -> None:
        content = VALID_CONFIG.replace(
            "random_response_chance = 0.25", "random_response_chance = 1.5"
        )

        with self.assertRaisesRegex(ConfigError, "between 0.0 and 1.0"):
            load_config(self._write_config(content))

    def test_rejects_placeholder_token(self) -> None:
        content = VALID_CONFIG.replace(
            'token = "discord-test-token"',
            'token = "paste_discord_bot_token_here"',
        )

        with self.assertRaisesRegex(ConfigError, "Set a real value"):
            load_config(self._write_config(content))


if __name__ == "__main__":
    unittest.main()
