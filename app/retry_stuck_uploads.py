import os
import uploader

files = [
    r"C:\Users\giova\Videos\Captures\Temple of Sethraliss - Harahara - Arcane Mage.mp4",
    r"C:\Users\giova\Videos\Captures\King's Rest +10 - Harahara - Arcane Mage.mp4",
]

youtube = uploader.connect_with_recovery()
uploaded = uploader.load_uploaded()

for path in files:
    if os.path.isfile(path):
        uploader.show_title_popup(path, youtube, uploaded)

# Return to normal watcher mode after the recovery uploads are handled.
uploader.main()
