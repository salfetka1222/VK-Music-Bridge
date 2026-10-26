"""Tests for VK URL handling and per-user library search."""
import os
import tempfile
import unittest

_temp_dir = tempfile.TemporaryDirectory()
os.environ.setdefault("BOT_TOKEN", "test-token-not-for-real-use")
os.environ["DATABASE_PATH"] = os.path.join(_temp_dir.name, "test.db")

from bot import extract_vk_links, normalize_vk_url, save_link, search_links  # noqa: E402


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


class LibrarySearchTests(unittest.TestCase):
    def setUp(self):
        self.user_a = 1001
        self.user_b = 2002
        save_link(self.user_a, "https://vk.com/artist/alpha")
        save_link(self.user_a, "https://music.vk.com/track/123")
        save_link(self.user_b, "https://vk.com/artist/secret")

    def test_search_matches_part_of_saved_url(self):
        rows = search_links(self.user_a, "alpha")
        self.assertEqual([row["url"] for row in rows], ["https://vk.com/artist/alpha"])

    def test_search_isolated_per_user(self):
        rows = search_links(self.user_a, "secret")
        self.assertEqual(rows, [])

    def test_search_returns_no_rows_for_empty_or_long_query(self):
        self.assertEqual(search_links(self.user_a, "  "), [])
        self.assertEqual(search_links(self.user_a, "x" * 81), [])

    def test_like_wildcards_are_treated_literally(self):
        save_link(self.user_a, "https://vk.com/track/100%_real")
        self.assertEqual(search_links(self.user_a, "%_real")[0]["url"], "https://vk.com/track/100%_real")


if __name__ == "__main__":
    unittest.main()
