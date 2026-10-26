"""Unit tests for the official VK catalog API adapter."""
import json
import unittest
from unittest.mock import patch

from vk_catalog import VKCatalogError, search_vk_audio, track_url


class VKCatalogTests(unittest.TestCase):
    def test_track_url_is_canonical(self):
        self.assertEqual(track_url(-123, 456), "https://vk.com/audio-123_456")

    def test_empty_query_is_rejected(self):
        with self.assertRaises(VKCatalogError):
            search_vk_audio("   ", "test-token")

    def test_missing_token_is_rejected(self):
        with self.assertRaises(VKCatalogError):
            search_vk_audio("Queen", "")

    @patch("urllib.request.urlopen")
    def test_parses_audio_search_results_without_using_media_url(self, urlopen):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({"response": {"items": [
                    {"id": 77, "owner_id": -10, "title": "Song", "artist": "Artist",
                     "duration": 125, "url": "https://media.example/audio.mp3"}
                ]}}).encode()
        urlopen.return_value = Response()
        results = search_vk_audio("Artist Song", "test-token")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Song")
        self.assertEqual(results[0]["artist"], "Artist")
        self.assertEqual(results[0]["url"], "https://vk.com/audio-10_77")
        self.assertNotIn("https://media.example", results[0]["url"])
        urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_vk_api_error_is_reported_without_token(self, urlopen):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({"error": {"error_code": 15, "error_msg": "Access denied"}}).encode()
        urlopen.return_value = Response()
        with self.assertRaisesRegex(VKCatalogError, "error 15"):
            search_vk_audio("Song", "secret-token")


if __name__ == "__main__":
    unittest.main()
