"""Use real local file streams and a fake YouTube client; never upload media."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httplib2
from googleapiclient.errors import HttpError

import uploader


class UploadFileHandleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.folder.cleanup)
        self.video = Path(self.folder.name) / "recording.mp4"
        self.video.write_bytes(b"offline test recording")
        self.thumbnail = Path(self.folder.name) / "thumbnail.jpg"
        self.thumbnail.write_bytes(b"offline test thumbnail")
        self.youtube = MagicMock()
        self.request = self.youtube.videos.return_value.insert.return_value
        self.request.next_chunk.return_value = (None, {"id": "offline-id"})

    def upload(self):
        return uploader.upload_video(
            self.youtube, str(self.video), "File handle test", "Stonewarden",
            "The Maelstrom", "Restoration Shaman", mythic_plus=False,
        )

    def assert_video_released(self):
        # MagicMock deliberately retains media in call history. This checks
        # explicit closure rather than relying on destruction/garbage collection.
        media = self.youtube.videos.return_value.insert.call_args.kwargs["media_body"]
        self.assertTrue(media.stream().closed)
        self.video.unlink()
        self.assertFalse(self.video.exists())

    def test_completed_video_is_released_even_with_retained_request(self):
        self.assertEqual(self.upload(), "offline-id")
        self.assert_video_released()

    def test_failed_video_is_released_even_when_exception_retains_request(self):
        self.request.next_chunk.side_effect = HttpError(
            httplib2.Response({"status": "403"}), b"offline permission failure"
        )
        with self.assertLogs(level="ERROR"), self.assertRaises(HttpError) as caught:
            self.upload()
        self.assertIsNotNone(caught.exception)
        self.assert_video_released()

    def test_request_creation_failure_releases_video(self):
        self.youtube.videos.return_value.insert.side_effect = ValueError("offline request failure")
        with self.assertRaises(ValueError):
            self.upload()
        self.assert_video_released()

    def test_transient_retry_keeps_stream_open_until_completion(self):
        attempts = []

        def next_chunk():
            media = self.youtube.videos.return_value.insert.call_args.kwargs["media_body"]
            self.assertFalse(media.stream().closed)
            attempts.append(True)
            if len(attempts) == 1:
                raise OSError("offline transient failure")
            media.stream().seek(0)
            self.assertEqual(media.stream().read(), b"offline test recording")
            return None, {"id": "offline-id"}

        self.request.next_chunk.side_effect = next_chunk
        with patch.object(uploader.time, "sleep"), self.assertLogs(level="WARNING"):
            self.assertEqual(self.upload(), "offline-id")
        self.youtube.videos.return_value.insert.assert_called_once()
        self.assertEqual(len(attempts), 2)
        self.assert_video_released()

    def test_cancel_after_exhausted_retries_releases_video(self):
        self.request.next_chunk.side_effect = OSError("offline repeated failure")
        with (patch.object(uploader.time, "sleep"),
              patch.object(uploader, "show_error_dialog", return_value=False),
              self.assertLogs(level="WARNING"), self.assertRaises(OSError)):
            self.upload()
        self.youtube.videos.return_value.insert.assert_called_once()
        self.assertEqual(self.request.next_chunk.call_count, 7)
        self.assert_video_released()

    def test_thumbnail_released_on_success_or_failure(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                self.thumbnail.write_bytes(b"offline test thumbnail")
                request = self.youtube.thumbnails.return_value.set.return_value
                request.execute.side_effect = OSError("offline failure") if failure else None
                if failure:
                    with self.assertRaises(OSError):
                        uploader.upload_thumbnail(self.youtube, "offline-id", str(self.thumbnail))
                else:
                    uploader.upload_thumbnail(self.youtube, "offline-id", str(self.thumbnail))
                media = self.youtube.thumbnails.return_value.set.call_args.kwargs["media_body"]
                self.assertTrue(media.stream().closed)
                self.thumbnail.unlink()
                self.assertFalse(self.thumbnail.exists())


if __name__ == "__main__":
    unittest.main()
