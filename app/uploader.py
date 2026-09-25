import ctypes
import sys
import os
import time
import json
import threading
import uuid
import logging
import tkinter as tk
from tkinter import messagebox, ttk

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.exceptions import TransportError
import httplib2
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from thumbnail_generator import generate_thumbnail


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = r"C:\Users\giova\Desktop\desktopApp\YouTubeUploader"
WATCH_FOLDER = r"C:\Users\giova\Videos\Captures"

WOW_RETAIL_FOLDER = r"C:\Program Files (x86)\World of Warcraft\_retail_"
WOW_ACCOUNT_FOLDER = os.path.join(
    WOW_RETAIL_FOLDER,
    "WTF",
    "Account"
)

CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
UPLOADED_FILE = os.path.join(BASE_DIR, "uploaded.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
PENDING_THUMBNAILS_FILE = os.path.join(BASE_DIR, "pending_thumbnails.json")

DUNGEONS = [
    ("Altar of Fangs", "AltarOfFangs"),
    ("The Blinding Vale", "BlindingVale"),
    ("Den of Nalorakk", "DenOfNalorakk"),
    ("King’s Rest", "KingsRest"),
    ("Murder Row", "MurderRow"),
    ("Ruby Life Pools", "RubyLifePools"),
    ("Temple of Sethraliss", "TempleOfSethraliss"),
    ("Voidscar Arena", "VoidscarArena"),
]
DUNGEON_IDS = dict(DUNGEONS)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]


# ============================================================
# WOW SPECS
# ============================================================

SPECS = [
    # Death Knight
    "Blood Death Knight",
    "Frost Death Knight",
    "Unholy Death Knight",

    # Demon Hunter
    "Havoc Demon Hunter",
    "Vengeance Demon Hunter",
    "Devourer Demon Hunter",

    # Druid
    "Balance Druid",
    "Feral Druid",
    "Guardian Druid",
    "Restoration Druid",

    # Evoker
    "Devastation Evoker",
    "Preservation Evoker",
    "Augmentation Evoker",

    # Hunter
    "Beast Mastery Hunter",
    "Marksmanship Hunter",
    "Survival Hunter",

    # Mage
    "Arcane Mage",
    "Fire Mage",
    "Frost Mage",

    # Monk
    "Brewmaster Monk",
    "Mistweaver Monk",
    "Windwalker Monk",

    # Paladin
    "Holy Paladin",
    "Protection Paladin",
    "Retribution Paladin",

    # Priest
    "Discipline Priest",
    "Holy Priest",
    "Shadow Priest",

    # Rogue
    "Assassination Rogue",
    "Outlaw Rogue",
    "Subtlety Rogue",

    # Shaman
    "Elemental Shaman",
    "Enhancement Shaman",
    "Restoration Shaman",

    # Warlock
    "Affliction Warlock",
    "Demonology Warlock",
    "Destruction Warlock",

    # Warrior
    "Arms Warrior",
    "Fury Warrior",
    "Protection Warrior",
]


# ============================================================
# ROLE DETECTION
# ============================================================

def get_role_from_spec(spec):
    healer_specs = {
        "Restoration Shaman",
        "Restoration Druid",
        "Holy Paladin",
        "Holy Priest",
        "Discipline Priest",
        "Mistweaver Monk",
        "Preservation Evoker",
    }

    tank_specs = {
        "Protection Warrior",
        "Protection Paladin",
        "Blood Death Knight",
        "Guardian Druid",
        "Brewmaster Monk",
        "Vengeance Demon Hunter",
    }

    if spec in healer_specs:
        return "Healer"

    if spec in tank_specs:
        return "Tank"

    return "DPS"


def get_hashtags(spec):
    role = get_role_from_spec(spec)

    spec_hashtag = "#" + spec.replace(" ", "")

    hashtags = [
        "#WorldOfWarcraft",
        "#WoW",
        spec_hashtag,
        "#MythicPlus",
    ]

    if role == "Healer":
        hashtags.append("#HealerPOV")

    elif role == "Tank":
        hashtags.append("#TankPOV")

    else:
        hashtags.append("#DPSPOV")

    return " ".join(hashtags)


def get_tags(spec, character, realm):
    role = get_role_from_spec(spec)

    tags = [
        "World of Warcraft",
        "WoW",
        "World of Warcraft Midnight",
        "WoW Midnight",
        "Mythic Plus",
        "Mythic+",
        spec,
        character,
        realm,
        "WoW Gameplay",
        "WoW POV",
        f"{role} POV",
    ]

    # Add class name separately
    class_name = spec.split(" ")[-1]

    if class_name not in tags:
        tags.append(class_name)

    return tags


# ============================================================
# YOUTUBE AUTHENTICATION
# ============================================================

def get_youtube():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE,
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build(
        "youtube",
        "v3",
        credentials=creds
    )


# ============================================================
# SETTINGS
# ============================================================

def load_settings():
    default_settings = {
        "last_character": "",
        "character_specs": {},
        "last_dungeon": "",
        "last_key_level": "12"
    }

    if not os.path.exists(SETTINGS_FILE):
        return default_settings

    try:
        with open(
            SETTINGS_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        default_settings.update(data)

        return default_settings

    except Exception:
        return default_settings


def save_settings(settings):
    with open(
        SETTINGS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            settings,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# CHARACTER SCANNING
# ============================================================

def get_wow_characters():
    characters = []

    if not os.path.exists(WOW_ACCOUNT_FOLDER):
        print("WoW Account folder not found.")
        return characters

    for account_name in os.listdir(WOW_ACCOUNT_FOLDER):

        account_path = os.path.join(
            WOW_ACCOUNT_FOLDER,
            account_name
        )

        if not os.path.isdir(account_path):
            continue

        for realm_name in os.listdir(account_path):

            realm_path = os.path.join(
                account_path,
                realm_name
            )

            if not os.path.isdir(realm_path):
                continue

            if realm_name.lower() in [
                "savedvariables"
            ]:
                continue

            for character_name in os.listdir(realm_path):

                character_path = os.path.join(
                    realm_path,
                    character_name
                )

                if not os.path.isdir(character_path):
                    continue

                characters.append({
                    "character": character_name,
                    "realm": realm_name,
                    "display": f"{character_name} - {realm_name}"
                })

    unique = {}

    for char in characters:
        unique[char["display"]] = char

    characters = list(unique.values())

    characters.sort(
        key=lambda x: x["character"].lower()
    )

    return characters


# ============================================================
# UPLOADED HISTORY
# ============================================================

def load_uploaded():
    if not os.path.exists(UPLOADED_FILE):
        return []

    try:
        with open(
            UPLOADED_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return []


def save_uploaded(uploaded):
    with open(
        UPLOADED_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            uploaded,
            f,
            indent=2
        )


# ============================================================
# WAIT FOR GAME BAR FILE TO FINISH
# ============================================================

def wait_until_finished(file_path):
    print(
        f"Waiting for recording to finish: "
        f"{file_path}"
    )

    last_size = -1
    stable_count = 0

    while stable_count < 3:

        if not os.path.exists(file_path):
            return False

        try:
            current_size = os.path.getsize(
                file_path
            )

        except Exception:
            time.sleep(2)
            continue

        if current_size == last_size:
            stable_count += 1

        else:
            stable_count = 0

        last_size = current_size

        time.sleep(2)

    return True


# ============================================================
# FILE NAME CLEANUP
# ============================================================

def clean_filename(title):
    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        title = title.replace(
            char,
            "-"
        )

    return title.strip()


# ============================================================
# YOUTUBE UPLOAD
# ============================================================

def upload_video(
    youtube,
    file_path,
    title,
    character,
    realm,
    spec
):
    print()
    print(f"Uploading: {title}")
    logging.info("Starting video upload: %s - %s", title, file_path)

    role = get_role_from_spec(spec)
    hashtags = get_hashtags(spec)
    tags = get_tags(
        spec,
        character,
        realm
    )

    description = f"""World of Warcraft gameplay.

Character: {character}
Realm: {realm}
Spec: {spec}
Role: {role}

{hashtags}
"""

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "20",
            "tags": tags
        },

        "status": {
            "privacyStatus": "private"
        }
    }

    # Upload in 8 MiB chunks instead of sending the entire recording as one
    # chunk. This allows the same resumable session to continue after a brief
    # connection failure without restarting a large recording from zero.
    media = MediaFileUpload(
        file_path,
        chunksize=8 * 1024 * 1024,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    consecutive_failures = 0
    max_retries = 6

    while response is None:
        try:
            # Retry the SAME resumable request, never create a second insert
            # request automatically. The library checks the server's position
            # when recovering from a transport error.
            status, response = request.next_chunk()
            consecutive_failures = 0
        except HttpError as exc:
            # Most 4xx errors (auth, quota, permissions, invalid requests)
            # are not transient. Retrying them just wastes time/quota.
            if exc.resp.status not in (408, 429, 500, 502, 503, 504):
                logging.exception("Permanent YouTube upload HTTP error")
                raise
            consecutive_failures += 1
            error = exc
        except (OSError, httplib2.HttpLib2Error, TransportError) as exc:
            # Includes WinError 10053/10054, timeouts, SSL/socket errors,
            # and temporary failures while refreshing an access token.
            consecutive_failures += 1
            error = exc
        else:
            if status:
                progress = int(status.progress() * 100)
                logging.info("Upload progress: %s%% - %s", progress, title)
                print(f"Upload progress: {progress}%")
            continue

        if consecutive_failures > max_retries:
            logging.error(
                "Upload failed after %s consecutive retries: %s - %s",
                max_retries, title, error
            )
            raise error

        delay = min(5 * (2 ** (consecutive_failures - 1)), 120)
        logging.warning(
            "Temporary upload error (%s: %s). Retry %s/%s in %ss: %s",
            type(error).__name__, error,
            consecutive_failures, max_retries, delay, title
        )
        time.sleep(delay)

    video_id = response["id"]

    print()
    print("Upload complete.")
    print(f"Video ID: {video_id}")
    logging.info("Video upload completed: %s - %s", video_id, title)

    return video_id


# ============================================================
# CUSTOM THUMBNAILS AND SAFE RETRY
# ============================================================

def load_pending_thumbnails():
    if not os.path.isfile(PENDING_THUMBNAILS_FILE):
        return {}
    with open(PENDING_THUMBNAILS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pending_thumbnails(pending):
    # Atomic replacement avoids leaving a partial JSON file on a normal write failure.
    temp_path = PENDING_THUMBNAILS_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, PENDING_THUMBNAILS_FILE)


def upload_thumbnail(youtube, video_id, thumbnail_path):
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(
            thumbnail_path, mimetype="image/jpeg", resumable=False
        ),
    ).execute()
    print(f"Custom thumbnail uploaded for video {video_id}")


def delete_after_thumbnail_success(record):
    # Never delete source templates or icon/spec assets: only this job's output.
    for field in ("thumbnail_path", "video_path"):
        path = record.get(field)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
                print(f"Deleted {field}: {path}")
            except OSError:
                logging.exception("Could not delete %s: %s", field, path)


def retry_pending_thumbnails(youtube):
    # Only retry thumbnails for an existing video ID; NEVER reupload the MP4.
    pending = load_pending_thumbnails()
    for video_id, record in list(pending.items()):
        thumbnail_path = record.get("thumbnail_path")
        if not thumbnail_path or not os.path.isfile(thumbnail_path):
            logging.error("Missing pending thumbnail for %s: %s", video_id, thumbnail_path)
            continue
        try:
            upload_thumbnail(youtube, video_id, thumbnail_path)
        except Exception:
            logging.exception("Thumbnail retry failed for %s", video_id)
            continue
        delete_after_thumbnail_success(record)
        del pending[video_id]
        save_pending_thumbnails(pending)


# ============================================================
# RECORDING POPUP
# ============================================================

def show_title_popup(
    file_path,
    youtube,
    uploaded
):
    characters = get_wow_characters()
    settings = load_settings()

    root = tk.Tk()

    root.title(
        "New WoW Recording"
    )

    root.geometry(
        "620x470"
    )

    root.resizable(
        False,
        False
    )

    root.attributes(
        "-topmost",
        True
    )

    root.lift()
    root.focus_force()


    # HEADER

    tk.Label(
        root,
        text="Recording finished",
        font=(
            "Segoe UI",
            15,
            "bold"
        )
    ).pack(
        pady=(15, 12)
    )


    # TITLE

    tk.Label(
        root,
        text="Video title:"
    ).pack()

    title_entry = tk.Entry(
        root,
        font=(
            "Segoe UI",
            11
        ),
        width=60
    )

    title_entry.pack(
        pady=(5, 12)
    )


    # CHARACTER

    tk.Label(
        root,
        text="Character:"
    ).pack()

    character_values = [
        x["display"]
        for x in characters
    ]

    character_combo = ttk.Combobox(
        root,
        values=character_values,
        state="readonly",
        width=55
    )

    character_combo.pack(
        pady=(5, 12)
    )


    # SPEC

    tk.Label(
        root,
        text="Spec:"
    ).pack()

    spec_combo = ttk.Combobox(
        root,
        values=SPECS,
        state="readonly",
        width=55
    )

    spec_combo.pack(
        pady=(5, 15)
    )


    # DUNGEON

    tk.Label(root, text="Dungeon:").pack()
    dungeon_combo = ttk.Combobox(
        root, values=[name for name, _ in DUNGEONS],
        state="readonly", width=55
    )
    dungeon_combo.pack(pady=(5, 10))
    last_dungeon = settings.get("last_dungeon", "")
    if last_dungeon in DUNGEON_IDS:
        dungeon_combo.set(last_dungeon)

    # KEY LEVEL

    tk.Label(root, text="Mythic+ key level:").pack()
    key_entry = tk.Spinbox(root, from_=2, to=99, width=8, font=("Segoe UI", 11))
    key_entry.pack(pady=(5, 10))
    key_entry.delete(0, tk.END)
    key_entry.insert(0, str(settings.get("last_key_level", "12")))


    # DEFAULT CHARACTER

    last_character = settings.get(
        "last_character",
        ""
    )

    if (
        last_character
        and last_character
        in character_values
    ):
        character_combo.set(
            last_character
        )

    elif character_values:
        character_combo.current(0)


    # REMEMBER SPEC PER CHARACTER

    def character_changed(event=None):
        selected_character = (
            character_combo.get()
        )

        remembered_specs = settings.get(
            "character_specs",
            {}
        )

        remembered_spec = (
            remembered_specs.get(
                selected_character
            )
        )

        if (
            remembered_spec
            and remembered_spec in SPECS
        ):
            spec_combo.set(
                remembered_spec
            )

        else:
            spec_combo.set("")


    character_combo.bind(
        "<<ComboboxSelected>>",
        character_changed
    )

    character_changed()


    # UPLOAD

    def upload():
        base_title = (
            title_entry
            .get()
            .strip()
        )

        selected_character = (
            character_combo.get()
        )

        selected_spec = (
            spec_combo.get()
        )

        selected_dungeon = dungeon_combo.get()
        key_raw = key_entry.get().strip()
        if selected_dungeon not in DUNGEON_IDS:
            messagebox.showwarning("Missing dungeon", "Please select a dungeon.")
            return
        try:
            key_level = int(key_raw)
            if not 2 <= key_level <= 99:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Invalid key", "Enter a key level from 2 to 99.")
            return
        dungeon_id = DUNGEON_IDS[selected_dungeon]

        if not base_title:

            messagebox.showwarning(
                "Missing title",
                "Please enter a video title."
            )

            return

        if not selected_character:

            messagebox.showwarning(
                "Missing character",
                "Please select a character."
            )

            return

        if not selected_spec:

            messagebox.showwarning(
                "Missing spec",
                "Please select a spec."
            )

            return

        character_data = next(
            (
                x for x in characters
                if x["display"]
                == selected_character
            ),
            None
        )

        if not character_data:

            messagebox.showerror(
                "Character error",
                "Could not find character information."
            )

            return

        character = (
            character_data["character"]
        )

        realm = (
            character_data["realm"]
        )

        youtube_title = (
            f"{base_title} | "
            f"{character} | "
            f"{selected_spec}"
        )

        settings["last_character"] = (
            selected_character
        )

        if "character_specs" not in settings:
            settings["character_specs"] = {}

        settings[
            "character_specs"
        ][
            selected_character
        ] = selected_spec

        settings["last_dungeon"] = selected_dungeon
        settings["last_key_level"] = str(key_level)
        save_settings(
            settings
        )

        safe_filename = clean_filename(
            youtube_title
        )

        new_path = os.path.join(
            os.path.dirname(
                file_path
            ),
            safe_filename + ".mp4"
        )

        # Prepare thumbnail BEFORE uploading so missing assets don't create
        # a video without its requested thumbnail. Do not touch base templates.
        try:
            thumbnail_path = generate_thumbnail(
                character=character,
                dungeon=dungeon_id,
                key_level=key_level,
                spec=selected_spec,
            )
            # The generator uses a predictable filename; give this recording
            # its own filename so a later recording can't overwrite a pending one.
            unique_thumb_path = os.path.join(
                os.path.dirname(thumbnail_path),
                f"upload_{uuid.uuid4().hex}.jpg",
            )
            os.replace(thumbnail_path, unique_thumb_path)
            thumbnail_path = unique_thumb_path
        except Exception as e:
            logging.exception("Thumbnail generation failed")
            messagebox.showerror(
                "Thumbnail error",
                f"Could not generate the thumbnail:\n{e}\n\n"
                "The video was NOT uploaded or deleted."
            )
            return

        try:
            if new_path != file_path:
                if os.path.exists(new_path):
                    messagebox.showerror(
                        "File already exists",
                        "A recording with this name already exists."
                    )
                    # Keep the generated thumbnail for diagnosis.
                    return
                os.rename(file_path, new_path)
        except Exception as e:
            logging.exception("Could not rename video")
            messagebox.showerror("File error", str(e))
            return

        root.destroy()
        try:
            video_id = upload_video(
                youtube, new_path, youtube_title, character, realm, selected_spec
            )
        except Exception:
            logging.exception("Video upload failed: %s", new_path)
            print("Video upload failed. Local MP4 and thumbnail were retained.")
            logging.error("Local MP4 and thumbnail retained for manual recovery: %s | %s", new_path, thumbnail_path)
            return

        # The video was created. Record its ID BEFORE attempting the thumbnail;
        # a thumbnail failure must never trigger a second video upload.
        record = {
            "video_path": new_path,
            "thumbnail_path": thumbnail_path,
        }
        try:
            pending = load_pending_thumbnails()
            pending[video_id] = record
            save_pending_thumbnails(pending)
            if new_path not in uploaded:
                uploaded.append(new_path)
                save_uploaded(uploaded)
        except Exception:
            logging.exception(
                "Video %s is uploaded but local upload history could not be saved. "
                "Do NOT reupload it; YouTube video ID: %s",
                video_id, video_id
            )
            return

        try:
            upload_thumbnail(youtube, video_id, thumbnail_path)
        except Exception:
            logging.exception(
                "Video %s uploaded, but thumbnail failed. "
                "Files retained; thumbnail will retry at next startup.", video_id
            )
            print(f"Video uploaded: https://www.youtube.com/watch?v={video_id}")
            print("Thumbnail failed. Both local files retained for retry.")
            return

        delete_after_thumbnail_success(record)
        try:
            pending = load_pending_thumbnails()
            pending.pop(video_id, None)
            save_pending_thumbnails(pending)
        except Exception:
            logging.exception("Could not clear completed pending entry for %s", video_id)

        print(f"Completed: https://www.youtube.com/watch?v={video_id}")

    # SKIP

    def skip():
        print(
            f"Skipped: "
            f"{file_path}"
        )

        uploaded.append(
            file_path
        )

        save_uploaded(
            uploaded
        )

        root.destroy()


    # BUTTONS

    button_frame = tk.Frame(
        root
    )

    button_frame.pack(
        pady=5
    )

    tk.Button(
        button_frame,
        text="Upload",
        width=18,
        command=upload
    ).pack(
        side="left",
        padx=10
    )

    tk.Button(
        button_frame,
        text="Skip",
        width=18,
        command=skip
    ).pack(
        side="left",
        padx=10
    )

    root.bind(
        "<Return>",
        lambda event: upload()
    )

    root.bind(
        "<Escape>",
        lambda event: skip()
    )

    title_entry.focus_set()

    root.mainloop()


# ============================================================
# WATCHDOG
# ============================================================

class RecordingHandler(
    FileSystemEventHandler
):

    def __init__(
        self,
        youtube,
        uploaded
    ):
        self.youtube = youtube
        self.uploaded = uploaded

    def on_created(
        self,
        event
    ):
        if event.is_directory:
            return

        file_path = (
            event.src_path
        )

        if not file_path.lower().endswith(
            ".mp4"
        ):
            return

        if file_path in self.uploaded:
            return

        print()
        print(
            "New recording detected:"
        )

        print(
            file_path
        )

        threading.Thread(
            target=self.process_recording,
            args=(file_path,),
            daemon=True
        ).start()

    def process_recording(
        self,
        file_path
    ):
        if wait_until_finished(
            file_path
        ):
            show_title_popup(
                file_path,
                self.youtube,
                self.uploaded
            )


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "Connecting to YouTube..."
    )

    youtube = get_youtube()

    retry_pending_thumbnails(youtube)

    uploaded = load_uploaded()

    characters = get_wow_characters()

    print()
    print(
        f"Found {len(characters)} "
        f"WoW characters."
    )

    print()

    print(
        "Game Bar uploader running."
    )

    print(
        "Watching:"
    )

    print(
        WATCH_FOLDER
    )

    print()

    print(
        "Waiting for new recordings..."
    )

    print()

    event_handler = RecordingHandler(
        youtube,
        uploaded
    )

    observer = Observer()

    observer.schedule(
        event_handler,
        WATCH_FOLDER,
        recursive=False
    )

    observer.start()

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:

        observer.stop()

    observer.join()


if __name__ == "__main__":

    # Create a Windows mutex to prevent multiple instances
    mutex = ctypes.windll.kernel32.CreateMutexW(
        None,
        False,
        "Local\\WoWYouTubeUploader"
    )

    ERROR_ALREADY_EXISTS = 183

    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        print("YouTube Uploader is already running.")
        sys.exit(0)

    logging.basicConfig(
        filename=os.path.join(BASE_DIR, "uploader.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    try:
        main()
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)