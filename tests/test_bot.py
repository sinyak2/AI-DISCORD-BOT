import unittest

from bot import split_discord_message


class DiscordMessageTests(unittest.TestCase):
    def test_short_message_is_not_split(self) -> None:
        self.assertEqual(split_discord_message("hello", 100), ["hello"])

    def test_long_message_is_split_without_data_loss(self) -> None:
        text = " ".join(["word"] * 80)

        chunks = split_discord_message(text, 100)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 100 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text)


if __name__ == "__main__":
    unittest.main()
