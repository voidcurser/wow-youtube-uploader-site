"""Offline tests for serial recording detection and crash recovery."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import uploader


class RecordingQueueTests(unittest.TestCase):
    def test_created_events_only_enqueue_once_without_creating_windows(self):
        handler = uploader.RecordingHandler(MagicMock(), [])
        event = SimpleNamespace(is_directory=False, src_path="recording.mp4")

        with (patch.object(uploader, "show_title_popup") as popup,
              patch.object(uploader.threading, "Thread") as thread):
            handler.on_created(event)
            handler.on_created(event)

        popup.assert_not_called()
        thread.assert_not_called()
        self.assertEqual(handler.pending.qsize(), 1)
        file_path = handler.pending.get_nowait()
        self.assertEqual(file_path, os.path.abspath("recording.mp4"))
        handler.completed_path(file_path)

        handler.on_created(event)
        self.assertEqual(handler.pending.qsize(), 1)

    def test_upload_journal_preserves_uncertain_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            journal_file = os.path.join(folder, "upload_journal.json")
            recording = os.path.join(folder, "recording.mp4")
            with patch.object(uploader, "UPLOAD_JOURNAL_FILE", journal_file):
                uploader.record_upload_state(recording, "My recording", "uploading")
                self.assertEqual(
                    uploader.load_upload_journal()[os.path.normcase(recording)]["state"],
                    "uploading",
                )
                uploader.record_upload_state(recording, "My recording", "uploaded", "video123")
                self.assertEqual(
                    uploader.load_upload_journal()[os.path.normcase(recording)]["video_id"],
                    "video123",
                )
                uploader.clear_upload_state(recording)
                self.assertEqual(uploader.load_upload_journal(), {})

    def test_crash_recovery_is_opt_in_and_skips_known_uploaded_video(self):
        with tempfile.TemporaryDirectory() as folder:
            new_file = Path(folder) / "needs-review.mp4"
            known_file = Path(folder) / "already-uploaded.mp4"
            new_file.touch()
            known_file.touch()
            with (patch.object(uploader, "WATCH_FOLDER", folder),
                  patch.object(uploader, "UPLOAD_JOURNAL_FILE", str(Path(folder) / "journal.json"))):
                uploader.record_upload_state(str(known_file), "Existing", "uploaded", "video123")
                handler = uploader.RecordingHandler(MagicMock(), [])
                dialog = MagicMock()
                with (patch.object(uploader.tk, "Tk", return_value=dialog),
                      patch.object(uploader.messagebox, "askyesno", return_value=False) as ask):
                    uploader.offer_existing_recordings(handler)
                    self.assertTrue(handler.pending.empty())
                    self.assertEqual(ask.call_args.kwargs["default"], uploader.messagebox.NO)

                with (patch.object(uploader.tk, "Tk", return_value=dialog),
                      patch.object(uploader.messagebox, "askyesno", return_value=True)):
                    uploader.offer_existing_recordings(handler)
                    self.assertEqual(handler.pending.qsize(), 1)
                    self.assertEqual(handler.pending.get_nowait(), str(new_file))


if __name__ == "__main__":
    unittest.main()
