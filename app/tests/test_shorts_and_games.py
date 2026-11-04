"""Dependency-free unit tests plus an optional FFmpeg integration smoke test.

The uploader imports Windows/Tk/Google APIs at module level; extracting its
pure helpers lets these tests run without a Windows desktop or credentials.
"""

import ast
import json
import logging
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).with_name("uploader_fixed.py")
if not SOURCE.is_file():
    SOURCE = Path(__file__).resolve().parents[1] / "uploader.py"


def load_helpers():
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {
        "get_hashtags", "get_tags", "build_description",
        "get_wow_characters", "_short_tools", "_probe_video",
        "make_vertical_short", "build_video_upload_body",
    }
    code = compile(
        ast.Module(body=[node for node in source.body
                         if isinstance(node, ast.FunctionDef) and node.name in names],
                   type_ignores=[]), str(SOURCE), "exec"
    )
    namespace = {
        "os": os, "json": json, "logging": logging, "math": math,
        "shutil": shutil, "subprocess": subprocess, "tempfile": tempfile,
        "BASE_DIR": str(SOURCE.parent),
        "GAME_LABELS": {"WoW Retail": "retail", "WoW Forever": "forever",
                        "Azeroth Survivors": "survivors"},
        "MAX_SHORT_SOURCE_SECONDS": 179.0,
        "SPECS": ["Restoration Shaman"],
        "get_role_from_spec": lambda _: "Healer",
    }
    exec(code, namespace)
    return namespace


class GameMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_helpers()

    def test_survivors_metadata_has_no_wow_words(self):
        h = self.helper
        game_labels = next(
            ast.literal_eval(node.value)
            for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "GAME_LABELS"
                    for target in node.targets)
        )
        self.assertEqual(game_labels["Azeroth Survivors"], "survivors")
        self.assertEqual(h["get_wow_characters"]("survivors"), [])
        description = h["build_description"]("", "", "", "Great run", game_version="survivors")
        self.assertIn("Great run", description)
        self.assertIn("#AzerothSurvivors", description)
        self.assertNotIn("World of Warcraft", description)
        self.assertNotIn("Character:", description)
        self.assertEqual(h["get_tags"]("", "", "", game_version="survivors")[0],
                         "Azeroth Survivors")

    def test_retail_and_forever_hashtags_are_relevant(self):
        h = self.helper
        retail = h["get_hashtags"]("Restoration Shaman", is_short=True)
        forever = h["get_hashtags"]("", game_version="forever")
        self.assertIn("#WoWMidnight", retail)
        self.assertIn("#Shorts", retail)
        self.assertIn("#MythicPlus", retail)
        self.assertNotIn("#WoWForever", retail)
        self.assertIn("#WoWForever", forever)
        self.assertNotIn("#WoWMidnight", forever)
        self.assertEqual(len(retail.split()), len(set(retail.split())))

    def test_youtube_upload_status_not_made_for_kids(self):
        body = self.helper["build_video_upload_body"]("Title", "Description", ["Gaming"])
        self.assertEqual(body["status"], {"privacyStatus": "public",
                                          "selfDeclaredMadeForKids": False})
        self.assertEqual(body["snippet"]["categoryId"], "20")


class ShortConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_helpers()

    def test_over_three_minutes_rejected_before_file_conversion(self):
        h = self.helper
        with (patch.dict(h, {"_short_tools": lambda: ("ffmpeg", "ffprobe"),
                             "_probe_video": lambda *_: (180.0, 1920, 1080)}),
              patch("tempfile.mkstemp") as make_temp):
            with self.assertRaisesRegex(ValueError, "trim"):
                h["make_vertical_short"]("recording.mp4")
            make_temp.assert_not_called()

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe not available")
    def test_real_vertical_conversion_preserves_source_and_audio(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "game.mp4")
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=320x180:rate=10", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=44100", "-t", "1.2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
            ], check=True)
            output = h["make_vertical_short"](source)
            try:
                self.assertTrue(os.path.isfile(source), "Original must remain intact")
                duration, width, height = h["_probe_video"](output, "ffprobe")
                self.assertEqual((width, height), (1080, 1920))
                self.assertLessEqual(duration, 180)
                audio = subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "a:0",
                    "-show_entries", "stream=codec_name", "-of", "json", output,
                ], check=True, capture_output=True, text=True)
                self.assertTrue(json.loads(audio.stdout)["streams"])
            finally:
                os.remove(output)


if __name__ == "__main__":
    unittest.main()
