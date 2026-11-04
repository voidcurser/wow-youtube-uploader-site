# YouTube Uploader: Azeroth Survivors and Shorts

The recording popup now supports **WoW Retail**, **WoW Forever**, and
**Azeroth Survivors**. Captures whose filename contains `Azeroth Survivors`
automatically start with that game selected; you can change it manually.

## Using the Short option on Windows

1. Install **FFmpeg**, including `ffmpeg.exe` and `ffprobe.exe`.
   Both must be available on the Windows PATH, or put both executables
   beside `uploader.py` in `C:\Users\giova\Desktop\desktopApp\YouTubeUploader`.
2. Restart the scheduled **YouTube Uploader** task after installation, so it
   receives the new PATH if necessary.
3. Select **Upload as YouTube Short** when reviewing a recording.
   The app generates a vertical 1080×1920 temporary video using the original
   uncropped gameplay in the center and a blurred version behind it.

The original MP4 is kept if conversion/upload fails. A Short longer than
approximately 179 seconds is refused; trim the source manually first. The app
does **not** silently discard gameplay or shorten the video.

The Short conversion may take several minutes, depending on the PC and source
length. No Shorts-specific thumbnail is uploaded; YouTube chooses the frame.

All new uploads declare `selfDeclaredMadeForKids: false` to YouTube. This only
applies to videos that are genuinely not directed at children, and it does not
override channel-wide comment restrictions or YouTube moderation decisions.

**Note:** As with the existing uploader, update the local `uploader.py` file and
restart the task to activate new code; merging to GitHub does not deploy it to
Windows automatically.
