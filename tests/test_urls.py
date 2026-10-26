"""Tests for VK URL handling and per-user library search."""
import os
import tempfile
import unittest

_temp_dir = tempfile.TemporaryDirectory()
os.environ.setdefault("BOT_TOKEN", "test-token-not-for-real-use")
os.environ["DATABASE_PATH"] = os.path.join(_temp_dir.name, "test.db")

from bot import (database, extract_vk_links, get_favorites, get_playlists, normalize_vk_url, save_link, search_links)  # noqa: E402


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


    def test_like_escape_character_and_backslash_are_treated_literally(self):
        url = "https://vk.com/track/a!b\\\\c"
        save_link(self.user_a, url)
        rows = search_links(self.user_a, "a!b\\\\c")
        self.assertEqual([row["url"] for row in rows], [url])



class PlaylistAndFavoriteTests(unittest.TestCase):
    def setUp(self):
        self.user_a = 3003
        self.user_b = 4004
        # Use a distinct URL per test because the temporary SQLite database is shared by the test run.
        test_url = f"https://vk.com/audio/playlist-test-{self._testMethodName}"
        self.added, self.link_id = save_link(self.user_a, test_url)
        self.assertTrue(self.added)

    def test_additive_schema_preserves_existing_link(self):
        with database() as connection:
            row = connection.execute(
                "SELECT telegram_user_id, url FROM saved_links WHERE id = ?",
                (self.link_id,),
            ).fetchone()
            self.assertEqual(row["telegram_user_id"], self.user_a)
            self.assertEqual(row["url"], f"https://vk.com/audio/playlist-test-{self._testMethodName}")
            tables = {
                r["name"] for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertTrue({"saved_links", "favorites", "playlists", "playlist_links"} <= tables)

    def test_favorites_are_scoped_to_user(self):
        with database() as connection:
            connection.execute(
                "INSERT INTO favorites (telegram_user_id, link_id) VALUES (?, ?)",
                (self.user_a, self.link_id),
            )
        self.assertEqual([r["id"] for r in get_favorites(self.user_a)], [self.link_id])
        self.assertEqual(get_favorites(self.user_b), [])

    def test_playlists_are_scoped_to_user(self):
        with database() as connection:
            connection.execute(
                "INSERT INTO playlists (telegram_user_id, name) VALUES (?, ?)",
                (self.user_a, "Test playlist"),
            )
        self.assertEqual([r["name"] for r in get_playlists(self.user_a)], ["Test playlist"])
        self.assertEqual(get_playlists(self.user_b), [])

if __name__ == "__main__":
    unittest.main()
