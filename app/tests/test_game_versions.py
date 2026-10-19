"""Verify version-specific metadata and account folders without network access."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image, ImageChops, ImageOps

import uploader
import thumbnail_generator as thumbnails


class GameVersionTests(unittest.TestCase):
    def test_forever_upload_is_public_and_has_no_retail_or_mythic_metadata(self):
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "offline-id"})
        with patch.object(uploader, "MediaFileUpload"):
            # Default mythic_plus=True is ignored for Forever, even outside the UI.
            uploader.upload_video(youtube, "fake.mp4", "My journey begins", "", "", "",
                                  game_version="forever")
        body = youtube.videos.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertIn("World of Warcraft: Forever gameplay.", body["snippet"]["description"])
        self.assertIn("#WoWForever", body["snippet"]["description"])
        self.assertIn("#JourneyTo60", body["snippet"]["description"])
        self.assertIn("WoW Forever", body["snippet"]["tags"])
        self.assertNotIn("Midnight", str(body))
        self.assertNotIn("Mythic", str(body))
        self.assertNotIn("Character:", body["snippet"]["description"])
        self.assertNotIn("Realm:", body["snippet"]["description"])
        self.assertNotIn("", body["snippet"]["tags"])

    def test_optional_free_text_spec_does_not_invent_a_role(self):
        description = uploader.build_description("NewHero", "NewRealm", "My leveling build",
                                                game_version="forever")
        self.assertIn("Spec: My leveling build", description)
        self.assertNotIn("Role:", description)
        self.assertNotIn("DPSPOV", description)

    def test_invalid_version_never_starts_upload(self):
        youtube = MagicMock()
        with patch.object(uploader, "MediaFileUpload") as media, self.assertRaises(ValueError):
            uploader.upload_video(youtube, "fake.mp4", "Title", "", "", "", game_version="invalid")
        media.assert_not_called()
        youtube.videos.assert_not_called()

    def test_each_version_reads_only_its_own_account_folder(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            retail = Path(folder) / "retail" / "Account"
            forever = Path(folder) / "forever" / "Account"
            (retail / "AccountOne" / "RetailRealm" / "RetailHero").mkdir(parents=True)
            (forever / "AccountTwo" / "ForeverRealm" / "ForeverHero").mkdir(parents=True)
            with (patch.object(uploader, "WOW_ACCOUNT_FOLDER", str(retail)),
                  patch.object(uploader, "WOW_FOREVER_ACCOUNT_FOLDER", str(forever))):
                self.assertEqual([x["character"] for x in uploader.get_wow_characters()], ["RetailHero"])
                self.assertEqual([x["character"] for x in uploader.get_wow_characters("forever")], ["ForeverHero"])

    def test_missing_forever_account_folder_never_falls_back_to_retail(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            retail = Path(folder) / "retail"
            (retail / "AccountOne" / "Realm" / "RetailHero").mkdir(parents=True)
            with (patch.object(uploader, "WOW_ACCOUNT_FOLDER", str(retail)),
                  patch.object(uploader, "WOW_FOREVER_ACCOUNT_FOLDER", str(Path(folder) / "missing"))):
                self.assertEqual(uploader.get_wow_characters("forever"), [])

    def test_forever_uses_approved_background_even_with_same_character_name(self):
        forever = thumbnails.get_generic_template("Stonewarden", "forever")
        retail = thumbnails.get_generic_template("Stonewarden", "retail")
        self.assertNotEqual(forever, retail)
        self.assertEqual(Path(forever).name, "JourneyTo60-v3.png")
        self.assertEqual(thumbnails.get_generic_template("", "forever"), forever)
        with Image.open(forever) as source:
            base = ImageOps.fit(source.convert("RGB"), (1280, 720))
        output = thumbnails.render_generic_thumbnail("", "My journey begins", "forever")
        changed = ImageChops.difference(base, output).getbbox()
        self.assertIsNotNone(changed)
        x1, y1, x2, y2 = thumbnails.GENERIC_HEADLINE_AREA
        self.assertGreaterEqual(changed[0], x1)
        self.assertGreaterEqual(changed[1], y1)
        self.assertLessEqual(changed[2], x2)
        self.assertLessEqual(changed[3], y2)


if __name__ == "__main__":
    unittest.main()
