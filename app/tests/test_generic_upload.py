"""Offline checks: no Google sign-in, network requests, or real recordings."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageChops, ImageOps

import thumbnail_generator as thumbnails
import uploader


class ThumbnailTests(unittest.TestCase):
    def test_layout_fits_without_shrinking_below_readable_size(self):
        headlines = [
            "Raid night", "Testing a new restoration build",
            "Testing a new restoration shaman build with friends tonight!!!"[:60],
            "New build: healing, damage & survival!",
        ]
        for headline in headlines:
            with self.subTest(headline=headline):
                lines, font, _, bbox = thumbnails.layout_generic_headline(headline)
                self.assertLessEqual(len(lines.splitlines()), 3)
                self.assertGreaterEqual(font.size, 44)
                self.assertEqual(" ".join(lines.split()), headline.upper())
                x1, y1, x2, y2 = thumbnails.GENERIC_HEADLINE_AREA
                self.assertLessEqual(bbox[2] - bbox[0], x2 - x1)
                self.assertLessEqual(bbox[3] - bbox[1], y2 - y1)

    def test_rejects_overlong_and_unbreakable_headlines(self):
        for headline in ("a" * 61, "W" * 60, "   "):
            with self.subTest(headline=headline), self.assertRaises(ValueError):
                thumbnails.layout_generic_headline(headline)

    def test_only_headline_area_changes_and_template_is_preserved(self):
        template = Path(thumbnails.get_generic_template("Stonewarden"))
        original_hash = hashlib.sha256(template.read_bytes()).hexdigest()
        with Image.open(template) as source:
            base = ImageOps.fit(source.convert("RGB"), (1280, 720))
        result = thumbnails.render_generic_thumbnail("Stonewarden", "Raid night")
        bbox = ImageChops.difference(base, result).getbbox()
        self.assertIsNotNone(bbox)
        x1, y1, x2, y2 = thumbnails.GENERIC_HEADLINE_AREA
        self.assertGreaterEqual(bbox[0], x1)
        self.assertGreaterEqual(bbox[1], y1)
        self.assertLessEqual(bbox[2], x2)
        self.assertLessEqual(bbox[3], y2)
        self.assertEqual(hashlib.sha256(template.read_bytes()).hexdigest(), original_hash)

    def test_export_is_unique_sized_jpeg(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder, patch.object(thumbnails, "OUTPUT_FOLDER", folder):
            paths = [thumbnails.generate_generic_thumbnail("Stonewarden", "Raid night") for _ in range(2)]
            self.assertNotEqual(*paths)
            for path in paths:
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1280, 720))
                    self.assertEqual(image.format, "JPEG")
                self.assertLessEqual(Path(path).stat().st_size, 2_000_000)

    def test_never_falls_back_to_another_character(self):
        self.assertIsNone(thumbnails.get_generic_template("NoTemplateCharacter"))


class MetadataTests(unittest.TestCase):
    def test_default_mythic_description_is_preserved(self):
        description = uploader.build_description("Stonewarden", "The Maelstrom", "Restoration Shaman")
        self.assertEqual(description,
            "World of Warcraft gameplay.\n\nCharacter: Stonewarden\n"
            "Realm: The Maelstrom\nSpec: Restoration Shaman\nRole: Healer\n\n"
            "#WorldOfWarcraft #WoW #RestorationShaman #MythicPlus #HealerPOV\n")
        self.assertIn("Mythic+", uploader.get_tags("Restoration Shaman", "Stonewarden", "The Maelstrom"))

    def test_general_upload_metadata_and_public_status(self):
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "test-video"})
        with patch.object(uploader, "MediaFileUpload"):
            result = uploader.upload_video(youtube, "fake.mp4", "Raid night", "Stonewarden",
                                           "The Maelstrom", "Restoration Shaman",
                                           notes="Trying a new build.", mythic_plus=False)
        body = youtube.videos.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(result, "test-video")
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertEqual(body["snippet"]["title"], "Raid night")
        self.assertIn("Trying a new build.", body["snippet"]["description"])
        self.assertIn("#WoWGameplay", body["snippet"]["description"])
        self.assertNotIn("Mythic", str(body))
        youtube.videos.return_value.insert.assert_called_once()

    def test_optional_spec_does_not_invent_role(self):
        description = uploader.build_description("Stonewarden", "The Maelstrom", "", mythic_plus=False)
        self.assertNotIn("Role:", description)
        self.assertNotIn("Spec:", description)
        self.assertNotIn("DPS", description)
        self.assertNotIn("Mythic", description)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class PopupTests(unittest.TestCase):
    def run_popup(self, *, character="Stonewarden", headline="", title="Raid night",
                  general=True, upload_error=None, thumbnail_error=None, back=False,
                  game_version="retail", initial_game="retail", forever_characters=None,
                  round_trip=False):
        # Exercise actual Tk form callbacks while keeping every test window hidden.
        original_tk = tk.Tk
        roots = []
        state = {}
        uploaded = []
        pending = {}
        settings_data = {
            "last_game_version": initial_game,
            "last_character": f"{character} - The Maelstrom",
            "character_specs": {f"{character} - The Maelstrom": "Restoration Shaman"},
            "last_dungeon": "The Blinding Vale", "last_key_level": "12",
            "forever": {"last_character": "", "character_specs": {}},
        }

        def scan_characters(version="retail"):
            if version == "forever":
                return forever_characters or []
            return [{"character": character, "realm": "The Maelstrom",
                     "display": f"{character} - The Maelstrom"}]

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            source = Path(folder) / "recording.mp4"
            source.write_bytes(b"test recording, never uploaded")

            def create_root():
                root = original_tk()
                root.withdraw()
                roots.append(root)
                return root

            def pending_save(data):
                pending.clear()
                pending.update(data)

            def mock_mythic_thumbnail(**_):
                path = Path(folder) / "mythic.jpg"
                path.write_bytes(b"mock thumbnail")
                return str(path)

            def drive_form(root):
                widgets = list(descendants(root))
                buttons = {w.cget("text"): w for w in widgets if isinstance(w, tk.Button)}
                game_combo = next(w for w in widgets if w.winfo_name() == "game_version")
                root.update_idletasks()
                target = "WoW Forever" if game_version == "forever" else "WoW Retail"
                sequence = ["WoW Forever", "WoW Retail"] if round_trip else [target]
                for label in sequence:
                    if game_combo.get() != label:
                        game_combo.set(label)
                        game_combo.event_generate("<<ComboboxSelected>>", when="now")
                title_entry = next(w for w in root.winfo_children() if type(w) is tk.Entry)
                title_entry.insert(0, title)
                if general and game_version == "retail":
                    buttons["Other WoW video…"].invoke()
                    if back:
                        buttons["Other WoW video…"].invoke()
                    else:
                        next(w for w in widgets if isinstance(w, tk.Text)).insert("1.0", "A new adventure.")
                        entries = [w for w in widgets if type(w) is tk.Entry]
                        entries[-1].insert(0, headline)
                root.update_idletasks()
                character_combo = next(w for w in root.winfo_children() if isinstance(w, ttk.Combobox))
                state["character_choices"] = character_combo.cget("values")
                state["character"] = character_combo.get()
                state["modal_title"] = root.title()
                state["mythic_frame_manager"] = next(w for w in widgets if isinstance(w, tk.Spinbox)).master.winfo_manager()
                state["required_height"] = root.winfo_reqheight()
                state["available_height"] = 750 if game_version == "forever" or general and not back else 630
                buttons["Upload"].invoke()
                try:
                    if root.winfo_exists():
                        root.destroy()
                except tk.TclError:
                    pass  # A successful upload already destroyed the popup.

            with (
                patch.object(tk, "Tk", side_effect=create_root),
                patch.object(original_tk, "mainloop", lambda root: drive_form(root)),
                patch.object(uploader, "get_wow_characters", side_effect=scan_characters),
                patch.object(uploader, "load_settings", return_value=settings_data),
                patch.object(uploader, "save_settings") as settings_save,
                patch.object(uploader, "UPLOAD_JOURNAL_FILE", str(Path(folder) / "upload_journal.json")),
                patch.object(uploader, "save_uploaded") as history_save,
                patch.object(uploader, "load_pending_thumbnails", side_effect=lambda: dict(pending)),
                patch.object(uploader, "save_pending_thumbnails", side_effect=pending_save),
                patch.object(uploader, "generate_thumbnail", side_effect=mock_mythic_thumbnail) as mythic_generator,
                patch.object(uploader, "generate_generic_thumbnail", wraps=thumbnails.generate_generic_thumbnail) as general_generator,
                patch.object(thumbnails, "OUTPUT_FOLDER", folder),
                patch.object(uploader, "upload_video", return_value="offline-id", side_effect=upload_error) as upload,
                patch.object(uploader, "upload_thumbnail", side_effect=thumbnail_error) as thumbnail_upload,
                patch.object(uploader, "show_error_dialog", return_value=False),
                patch.object(uploader.messagebox, "showwarning") as warning,
                patch.object(uploader.messagebox, "showerror") as error,
            ):
                try:
                    uploader.show_title_popup(str(source), MagicMock(), uploaded)
                    state.update(upload=upload, thumbnail_upload=thumbnail_upload, pending=dict(pending),
                                 warning=warning, error=error, history_save=history_save,
                                 settings_save=settings_save, mythic_generator=mythic_generator,
                                 general_generator=general_generator, settings_data=settings_data,
                                 recordings=list(Path(folder).glob("*.mp4")),
                                 thumbnails=list(Path(folder).glob("*.jpg")), uploaded=uploaded)
                finally:
                    for root in roots:
                        try:
                            root.destroy()
                        except tk.TclError:
                            pass
        return state

    def test_stonewarden_upload_uses_generic_thumbnail(self):
        state = self.run_popup()
        state["upload"].assert_called_once()
        state["thumbnail_upload"].assert_called_once()
        state["mythic_generator"].assert_not_called()
        state["error"].assert_not_called()
        self.assertFalse(state["upload"].call_args.kwargs["mythic_plus"])
        self.assertEqual(state["upload"].call_args.args[2], "Raid night")
        self.assertFalse(state["pending"])
        self.assertFalse(state["recordings"])
        self.assertFalse(state["thumbnails"])
        self.assertLessEqual(state["required_height"], state["available_height"])

    def test_other_character_finishes_without_thumbnail(self):
        state = self.run_popup(character="Harahara")
        state["upload"].assert_called_once()
        state["thumbnail_upload"].assert_not_called()
        self.assertFalse(state["pending"])
        self.assertFalse(state["recordings"])
        state["history_save"].assert_called_once()

    def test_thumbnail_failure_keeps_files_for_existing_video(self):
        state = self.run_popup(thumbnail_error=OSError("offline failure"))
        state["upload"].assert_called_once()
        self.assertIn("offline-id", state["pending"])
        self.assertEqual(len(state["recordings"]), 1)
        self.assertEqual(len(state["thumbnails"]), 1)

    def test_failed_video_keeps_files_without_marking_uploaded(self):
        state = self.run_popup(upload_error=OSError("offline failure"))
        state["history_save"].assert_not_called()
        state["thumbnail_upload"].assert_not_called()
        self.assertEqual(len(state["recordings"]), 1)
        self.assertEqual(len(state["thumbnails"]), 1)

    def test_long_video_title_can_have_short_headline(self):
        state = self.run_popup(title="A long title about my adventures in Azeroth with friends " + "today " * 5,
                               headline="Adventures with friends")
        state["upload"].assert_called_once()

    def test_long_headline_blocks_upload_and_keeps_recording(self):
        state = self.run_popup(headline="a" * 61)
        state["upload"].assert_not_called()
        state["error"].assert_called_once()
        self.assertEqual(len(state["recordings"]), 1)

    def test_original_mythic_flow_and_switching_back(self):
        for general, back in [(False, False), (True, True)]:
            with self.subTest(general=general, back=back):
                state = self.run_popup(general=general, back=back)
                state["mythic_generator"].assert_called_once()
                self.assertTrue(state["upload"].call_args.kwargs["mythic_plus"])
                self.assertIn("Stonewarden | Restoration Shaman", state["upload"].call_args.args[2])
                self.assertFalse(state["pending"])
                self.assertLessEqual(state["required_height"], state["available_height"])


class ForeverPopupTests(unittest.TestCase):
    def test_selecting_forever_hides_mythic_and_uses_approved_template_without_character(self):
        state = PopupTests().run_popup(game_version="forever")
        state["upload"].assert_called_once()
        call = state["upload"].call_args
        self.assertEqual(call.kwargs["game_version"], "forever")
        self.assertFalse(call.kwargs["mythic_plus"])
        self.assertEqual(call.args[3:6], ("", "", ""))
        self.assertEqual(state["character_choices"], ("",))
        self.assertEqual(state["mythic_frame_manager"], "")
        self.assertIn("Forever", state["modal_title"])
        self.assertEqual(state["general_generator"].call_args.args[2], "forever")
        state["mythic_generator"].assert_not_called()
        self.assertFalse(state["pending"])
        self.assertLessEqual(state["required_height"], state["available_height"])
        self.assertEqual(state["settings_data"]["last_game_version"], "forever")
        self.assertEqual(state["settings_data"]["last_character"], "Stonewarden - The Maelstrom")

    def test_forever_lists_only_forever_characters(self):
        char = {"character": "NewHero", "realm": "ForeverRealm", "display": "NewHero - ForeverRealm"}
        state = PopupTests().run_popup(game_version="forever", forever_characters=[char])
        self.assertIn(char["display"], state["character_choices"])
        self.assertNotIn("Stonewarden - The Maelstrom", state["character_choices"])
        state["upload"].assert_called_once()

    def test_remembers_forever_version_on_next_recording(self):
        state = PopupTests().run_popup(game_version="forever", initial_game="forever")
        self.assertIn("Forever", state["modal_title"])
        state["upload"].assert_called_once()
        self.assertEqual(state["upload"].call_args.kwargs["game_version"], "forever")

    def test_switching_back_restores_retail_character_and_spec(self):
        state = PopupTests().run_popup(round_trip=True, general=False)
        state["upload"].assert_called_once()
        self.assertEqual(state["upload"].call_args.args[3:6], ("Stonewarden", "The Maelstrom", "Restoration Shaman"))
        self.assertEqual(state["upload"].call_args.kwargs["game_version"], "retail")
        state["mythic_generator"].assert_called_once()

    def test_forever_still_enforces_headline_limit(self):
        state = PopupTests().run_popup(game_version="forever", title="a" * 61)
        state["upload"].assert_not_called()
        state["error"].assert_called_once()
        self.assertEqual(len(state["recordings"]), 1)


if __name__ == "__main__":
    unittest.main()
