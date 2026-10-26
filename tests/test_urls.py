"""Tests for VK link validation and extraction."""
import os
import tempfile
import unittest

# Set configuration before importing the bot module.
_temp_dir = tempfile.TemporaryDirectory()
os.environ.setdefault("BOT_TOKEN", "test-token-not-for-real-use")
os.environ["DATABASE_PATH"] = os.path.join(_temp_dir.name, "test.db")

from bot import extract_vk_links, normalize_vk_url  # noqa: E402


class VKURLTests(unittest.TestCase):
    def test_accepts_vk_url(self):
        self.assertEqual(
            normalize_vk_url("https://vk.com/artist"),
            "https://vk.com/artist",
        )

    def test_adds_scheme_to_plain_vk_link(self):
        self.assertEqual(
            normalize_vk_url("vk.com/music/track"),
            "https://vk.com/music/track",
        )

    def test_rejects_lookalike_domain(self):
        self.assertIsNone(normalize_vk_url("https://vk.com.example.org/track"))
        self.assertIsNone(normalize_vk_url("https://evil-vk.com/track"))

    def test_rejects_credentials_in_url(self):
        self.assertIsNone(normalize_vk_url("https://user:pass@vk.com/track"))

    def test_extracts_only_allowed_vk_links(self):
        links = extract_vk_links(
            "Listen https://vk.com/artist and vk.ru/music/123 "
            "but ignore https://example.com/track"
        )
        self.assertEqual(
            links,
            ["https://vk.com/artist", "https://vk.ru/music/123"],
        )

    def test_removes_trailing_punctuation(self):
        self.assertEqual(
            extract_vk_links("Link: https://vk.com/artist."),
            ["https://vk.com/artist"],
        )


if __name__ == "__main__":
    unittest.main()
