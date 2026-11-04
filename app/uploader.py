import ctypes
import sys
import os
import time
import json
import threading
import queue
import uuid
import logging
import faulthandler
from contextlib import closing
import tkinter as tk
from tkinter import messagebox, ttk

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.exceptions import TransportError, RefreshError
import httplib2
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from thumbnail_generator import (
    generate_thumbnail, generate_generic_thumbnail, get_generic_template,
    render_generic_thumbnail, normalize_headline, GENERIC_HEADLINE_LIMIT,
)


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
WOW_FOREVER_ACCOUNT_FOLDER = os.path.join(
    os.path.dirname(WOW_RETAIL_FOLDER), "_forever_", "WTF", "Account"
)
GAME_LABELS = {"WoW Retail": "retail", "WoW Forever": "forever"}

CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
UPLOADED_FILE = os.path.join(BASE_DIR, "uploaded.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
PENDING_THUMBNAILS_FILE = os.path.join(BASE_DIR, "pending_thumbnails.json")
UPLOAD_JOURNAL_FILE = os.path.join(BASE_DIR, "upload_journal.json")

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


def get_hashtags(spec, mythic_plus=True, game_version="retail"):
    hashtags = ["#WorldOfWarcraft", "#WoW"]
    if spec:
        hashtags.append("#" + spec.replace(" ", ""))
    if game_version == "forever":
        hashtags.extend(["#WoWForever", "#JourneyTo60", "#WoWLeveling"])
    else:
        hashtags.append("#MythicPlus" if mythic_plus else "#WoWGameplay")
    if spec not in SPECS:
        return " ".join(hashtags)
    role = get_role_from_spec(spec)

    if role == "Healer":
        hashtags.append("#HealerPOV")

    elif role == "Tank":
        hashtags.append("#TankPOV")

    else:
        hashtags.append("#DPSPOV")

    return " ".join(hashtags)


def get_tags(spec, character, realm, mythic_plus=True, game_version="retail"):
    tags = [
        "World of Warcraft",
        "WoW",
        "WoW Gameplay",
        "WoW POV",
    ]
    if game_version == "forever":
        tags.extend(["World of Warcraft Forever", "WoW Forever", "Journey to 60", "WoW Leveling"])
    else:
        tags.extend(["World of Warcraft Midnight", "WoW Midnight"])
    tags.extend(value for value in (character, realm) if value)
    if mythic_plus and game_version == "retail":
        tags.extend(["Mythic Plus", "Mythic+"])
    if spec:
        tags.append(spec)
        if spec in SPECS:
            tags.append(f"{get_role_from_spec(spec)} POV")
        class_name = spec.rsplit(" ", 1)[-1]
        if class_name not in tags:
            tags.append(class_name)

    return tags


def build_description(character, realm, spec, notes="", mythic_plus=True, game_version="retail"):
    details = []
    if character:
        details.append(f"Character: {character}")
    if realm:
        details.append(f"Realm: {realm}")
    if spec:
        details.append(f"Spec: {spec}")
        if spec in SPECS:
            details.append(f"Role: {get_role_from_spec(spec)}")
    gameplay = ("World of Warcraft: Forever gameplay.\nJourney to level 60."
                if game_version == "forever" else "World of Warcraft gameplay.")
    sections = [notes.strip(), gameplay, "\n".join(details),
                get_hashtags(spec, mythic_plus=mythic_plus, game_version=game_version)]
    return "\n\n".join(section for section in sections if section) + "\n"


# ============================================================
# YOUTUBE AUTHENTICATION
# ============================================================

def _save_token(creds):
    """Write OAuth credentials atomically so a crash cannot corrupt token.json."""
    temp_file = TOKEN_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as token:
        token.write(creds.to_json())
    os.replace(temp_file, TOKEN_FILE)


def _backup_invalid_token():
    """Keep a revoked token for diagnostics without blocking a fresh login."""
    if not os.path.isfile(TOKEN_FILE):
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(BASE_DIR, f"token_revoked_{stamp}.json")
    os.replace(TOKEN_FILE, backup)
    logging.warning("Revoked Google OAuth token moved to %s", backup)


def get_youtube():
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except (ValueError, json.JSONDecodeError, OSError):
            logging.exception("Saved Google OAuth token could not be loaded")
            _backup_invalid_token()
            creds = None

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            # Normal path after the one-time login: refresh silently.
            creds.refresh(Request())
            _save_token(creds)
            logging.info("Google OAuth access token refreshed silently")
        except RefreshError as exc:
            if "invalid_grant" not in str(exc).lower():
                raise
            # Revoked/expired refresh token: discard it and perform one new consent flow.
            logging.warning("Google OAuth refresh token is no longer valid; starting one-time reauthorization")
            _backup_invalid_token()
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        # Force offline consent on recovery so Google returns a reusable refresh token.
        creds = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )
        _save_token(creds)
        logging.info("Google OAuth authorization saved successfully")

    return build("youtube", "v3", credentials=creds)


# ============================================================
# VISIBLE ERROR DIALOGS (the uploader normally runs via pythonw.exe)
# ============================================================

def show_error_dialog(title, message, retry=False):
    """Show a topmost modal error even when no application window is open."""
    dialog = tk.Tk()
    dialog.withdraw()
    dialog.attributes("-topmost", True)
    try:
        if retry:
            return messagebox.askretrycancel(title, message, parent=dialog)
        messagebox.showerror(title, message, parent=dialog)
        return False
    finally:
        dialog.destroy()


def connect_with_recovery():
    """Offer reauthorization instead of silently exiting on an invalid token."""
    while True:
        try:
            return get_youtube()
        except RefreshError as exc:
            logging.exception("Google authorization refresh failed")
            invalid = "invalid_grant" in str(exc).lower()
            if invalid:
                retry = show_error_dialog(
                    "YouTube Uploader - Google sign-in required",
                    "Your Google authorization has expired or been revoked.\n\n"
                    "Retry: back up the old token as token_old.json and open "
                    "Google sign-in again.\nCancel: close the uploader without "
                    "changing any recordings.",
                    retry=True,
                )
                if not retry:
                    raise
                try:
                    if os.path.isfile(TOKEN_FILE):
                        os.replace(TOKEN_FILE, os.path.join(BASE_DIR, "token_old.json"))
                except OSError as backup_error:
                    logging.exception("Could not back up revoked OAuth token")
                    show_error_dialog("YouTube Uploader - Token backup failed", str(backup_error))
                    raise
            elif not show_error_dialog(
                "YouTube Uploader - Google authorization error",
                f"Could not refresh Google authorization:\n{exc}\n\n"
                "Check your connection and choose Retry, or Cancel to exit.",
                retry=True,
            ):
                raise
        except Exception as exc:
            logging.exception("YouTube connection failed during startup")
            if not show_error_dialog(
                "YouTube Uploader - Startup error",
                f"Could not connect to YouTube:\n{type(exc).__name__}: {exc}\n\n"
                "Check your network or Google account. Retry to try again; "
                "Cancel to exit. See uploader.log for details.",
                retry=True,
            ):
                raise


# ============================================================
# SETTINGS
# ============================================================

def load_settings():
    default_settings = {
        "last_character": "",
        "character_specs": {},
        "last_dungeon": "",
        "last_key_level": "12",
        "last_game_version": "retail",
        "forever": {"last_character": "", "character_specs": {}},
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

def get_wow_characters(game_version="retail"):
    characters = []
    if game_version not in GAME_LABELS.values():
        raise ValueError("Please select WoW Retail or WoW Forever.")
    account_folder = WOW_FOREVER_ACCOUNT_FOLDER if game_version == "forever" else WOW_ACCOUNT_FOLDER
    if not os.path.exists(account_folder):
        print(f"WoW {game_version} Account folder not found.")
        return characters

    for account_name in os.listdir(account_folder):

        account_path = os.path.join(
            account_folder,
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
            uploaded = json.load(f)
        if not isinstance(uploaded, list):
            raise ValueError("uploaded.json must contain a JSON list")
        return uploaded
    except Exception as exc:
        logging.exception("Upload history unreadable; refusing unsafe reuploads")
        raise RuntimeError(
            "uploaded.json could not be read. Fix the file before restarting "
            "to avoid duplicate uploads."
        ) from exc


def save_uploaded(uploaded):
    # A native crash must not leave a truncated history and cause reuploads.
    temporary = UPLOADED_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(uploaded, f, indent=2)
    os.replace(temporary, UPLOADED_FILE)


def load_upload_journal():
    """Videos with an uncertain outcome must never be silently retried."""
    if not os.path.isfile(UPLOAD_JOURNAL_FILE):
        return {}
    with open(UPLOAD_JOURNAL_FILE, "r", encoding="utf-8") as f:
        journal = json.load(f)
    if not isinstance(journal, dict):
        raise ValueError("upload_journal.json must contain a JSON object")
    return journal


def save_upload_journal(journal):
    temporary = UPLOAD_JOURNAL_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False)
    os.replace(temporary, UPLOAD_JOURNAL_FILE)


def record_upload_state(path, title, state, video_id=None):
    journal = load_upload_journal()
    journal[os.path.normcase(os.path.abspath(path))] = {
        "title": title,
        "state": state,
        "video_id": video_id,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_upload_journal(journal)


def clear_upload_state(path):
    journal = load_upload_journal()
    journal.pop(os.path.normcase(os.path.abspath(path)), None)
    save_upload_journal(journal)


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
    spec,
    notes="",
    mythic_plus=True,
    game_version="retail",
):
    if game_version not in GAME_LABELS.values():
        raise ValueError("Please select WoW Retail or WoW Forever.")
    if game_version == "forever":
        mythic_plus = False
    print()
    print(f"Uploading: {title}")
    logging.info("Starting video upload: %s - %s", title, file_path)

    tags = get_tags(
        spec,
        character,
        realm,
        mythic_plus=mythic_plus,
        game_version=game_version,
    )
    description = build_description(character, realm, spec, notes, mythic_plus, game_version)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "20",
            "tags": tags
        },

        "status": {
            "privacyStatus": "public"
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

    # Close explicitly on success and failure. Requests/tracebacks may retain
    # media references, so its destructor cannot reliably release Windows locks.
    # Keep the stream open throughout retries of this same resumable session.
    with closing(media.stream()):
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
                    "Upload error after %s automatic retries: %s - %s",
                    max_retries, title, error
                )
                retry = show_error_dialog(
                    "YouTube Uploader - Upload interrupted",
                    f"Upload interrupted: {title}\n\n"
                    f"{type(error).__name__}: {error}\n\n"
                    "Retry will continue the SAME in-memory resumable upload "
                    "request. Cancel keeps the MP4 and thumbnail for later.\n\n"
                    "If the video already appears in YouTube Studio, choose Cancel "
                    "to avoid starting another upload later.",
                    retry=True,
                )
                if not retry:
                    raise error
                logging.info("User requested retry of current upload session: %s", title)
                consecutive_failures = 0
                continue

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
    media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg", resumable=False)
    with closing(media.stream()):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
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
    settings = load_settings()
    initial_game = settings.get("last_game_version", "retail")
    if initial_game not in GAME_LABELS.values():
        initial_game = "retail"
    characters = get_wow_characters(initial_game)
    active_game = None
    game_drafts = {}

    root = tk.Tk()

    root.title(
        "New WoW Recording"
    )

    root.geometry(
        "620x670"
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
    general_mode = tk.BooleanVar(root, value=False)


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

    tk.Label(
        root,
        text=os.path.basename(file_path),
        fg="#555555",
        wraplength=580,
    ).pack(pady=(0, 8))

    game_frame = tk.Frame(root)
    game_frame.pack(pady=(0, 12))
    tk.Label(game_frame, text="Game:").pack(side="left", padx=(0, 8))
    game_var = tk.StringVar(root, value=next(label for label, key in GAME_LABELS.items() if key == initial_game))
    game_combo = ttk.Combobox(game_frame, name="game_version", textvariable=game_var,
                              values=list(GAME_LABELS), state="readonly", width=24)
    game_combo.pack(side="left")

    def selected_game():
        return GAME_LABELS[game_var.get()]

    def character_profile():
        if selected_game() == "retail":
            return settings
        return settings.setdefault("forever", {"last_character": "", "character_specs": {}})


    # TITLE

    tk.Label(
        root,
        text="Video title:"
    ).pack()

    title_var = tk.StringVar(root)
    title_entry = tk.Entry(
        root,
        textvariable=title_var,
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

    character_label = tk.Label(
        root,
        text="Character:"
    )
    character_label.pack()

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

    spec_label = tk.Label(
        root,
        text="Spec:"
    )
    spec_label.pack()

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

    mythic_frame = tk.Frame(root)
    mythic_frame.pack()
    tk.Label(mythic_frame, text="Dungeon:").pack()
    dungeon_combo = ttk.Combobox(
        mythic_frame, values=[name for name, _ in DUNGEONS],
        state="readonly", width=55
    )
    dungeon_combo.pack(pady=(5, 10))
    last_dungeon = settings.get("last_dungeon", "")
    if last_dungeon in DUNGEON_IDS:
        dungeon_combo.set(last_dungeon)

    # KEY LEVEL

    tk.Label(mythic_frame, text="Mythic+ key level:").pack()
    key_entry = tk.Spinbox(mythic_frame, from_=2, to=99, width=8, font=("Segoe UI", 11))
    key_entry.pack(pady=(5, 10))
    key_entry.delete(0, tk.END)
    key_entry.insert(0, str(settings.get("last_key_level", "12")))

    general_frame = tk.Frame(root)
    tk.Label(general_frame, text="Description (optional):").pack()
    description_entry = tk.Text(general_frame, width=64, height=3, wrap="word")
    description_entry.pack(pady=(5, 8))
    tk.Label(general_frame, text="Thumbnail headline (optional; uses video title if blank):").pack()
    headline_var = tk.StringVar(root)
    headline_entry = tk.Entry(general_frame, textvariable=headline_var, width=60,
                              font=("Segoe UI", 11))
    headline_entry.pack(pady=(5, 3))
    headline_hint = tk.Label(general_frame, wraplength=550)
    headline_hint.pack()
    thumbnail_status = tk.Label(general_frame, wraplength=550)
    thumbnail_status.pack(pady=(4, 4))

    def selected_character_name():
        return next((item["character"] for item in characters
                     if item["display"] == character_combo.get()), "")

    def effective_headline():
        return normalize_headline(headline_var.get().strip() or title_entry.get())

    def update_headline_hint(*_):
        count = len(effective_headline())
        headline_hint.config(
            text=f"{count}/{GENERIC_HEADLINE_LIMIT} characters · Up to 3 lines · Aim for 20–45 characters",
            fg="#B42318" if count > GENERIC_HEADLINE_LIMIT else "#555555",
        )

    def update_thumbnail_status():
        available = bool(get_generic_template(selected_character_name(), selected_game()))
        headline_entry.config(state="normal" if available else "disabled")
        preview_button.config(state="normal" if available else "disabled")
        if selected_game() == "forever":
            status = ("Forever: Journey to 60 thumbnail and hashtags. Character artwork can be added later."
                      if available else "Forever thumbnail is missing. Restore the approved template before uploading.")
        else:
            status = ("Character thumbnail available. WoW hashtags are added automatically."
                      if available else "No generic template for this character yet. Uploads without a custom thumbnail.")
        thumbnail_status.config(text=status)
        update_headline_hint()

    def preview_thumbnail():
        from PIL import ImageTk
        try:
            image = render_generic_thumbnail(selected_character_name(), effective_headline(), selected_game())
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Thumbnail headline", str(exc), parent=root)
            return
        preview = tk.Toplevel(root)
        preview.title("Thumbnail preview")
        preview.attributes("-topmost", True)
        preview_image = ImageTk.PhotoImage(image.resize((960, 540)), master=preview)
        label = tk.Label(preview, image=preview_image)
        label.image = preview_image
        label.pack()

    preview_button = tk.Button(general_frame, text="Preview thumbnail", command=preview_thumbnail)
    preview_button.pack(pady=(0, 8))
    headline_var.trace_add("write", update_headline_hint)
    title_var.trace_add("write", update_headline_hint)


    # DEFAULT CHARACTER

    last_character = character_profile().get(
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

        remembered_specs = character_profile().get(
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
            and (remembered_spec in SPECS or selected_game() == "forever")
        ):
            spec_combo.set(
                remembered_spec
            )

        else:
            spec_combo.set(character_profile().get("last_spec", "")
                           if selected_game() == "forever" and not selected_character else "")
        update_thumbnail_status()


    character_combo.bind(
        "<<ComboboxSelected>>",
        character_changed
    )

    character_changed()


    # UPLOAD

    def upload():
        nonlocal file_path
        base_title = (
            title_entry
            .get()
            .strip()
        )

        selected_character = (
            character_combo.get()
        )

        selected_spec = (
            spec_combo.get().strip()
        )

        selected_dungeon = dungeon_combo.get()
        key_raw = key_entry.get().strip()
        game_version = selected_game()
        is_forever = game_version == "forever"
        is_general = general_mode.get() or is_forever
        if not is_general:
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

        if not selected_character and not is_forever:

            messagebox.showwarning(
                "Missing character",
                "Please select a character."
            )

            return

        if not selected_spec and not is_general:

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

        if not character_data and (selected_character or not is_forever):

            messagebox.showerror(
                "Character error",
                "Could not find character information."
            )

            return

        character = character_data["character"] if character_data else ""
        realm = character_data["realm"] if character_data else ""

        youtube_title = (
            f"{base_title} | "
            f"{character} | "
            f"{selected_spec}"
        ) if not is_general else base_title
        if len(youtube_title) > 100:
            messagebox.showwarning("Title too long", "The full YouTube title must be 100 characters or fewer.")
            return
        notes = description_entry.get("1.0", "end-1c").strip() if is_general else ""
        if len(notes) > 2000:
            messagebox.showwarning("Description too long", "Keep your description to 2,000 characters or fewer.")
            return

        settings["last_game_version"] = game_version
        profile = character_profile()
        profile["last_character"] = selected_character
        if selected_spec:
            if selected_character:
                profile.setdefault("character_specs", {})[selected_character] = selected_spec
        if is_forever:
            profile["last_spec"] = selected_spec
            if selected_character and not selected_spec:
                profile.setdefault("character_specs", {}).pop(selected_character, None)
        if not is_general:
            settings["last_dungeon"] = selected_dungeon
            settings["last_key_level"] = str(key_level)

        safe_filename = clean_filename(
            youtube_title
        )

        new_path = os.path.join(
            os.path.dirname(
                file_path
            ),
            safe_filename + ".mp4"
        )
        original_path = file_path

        # The previous process may have crashed after YouTube created a video.
        # Never start a new upload for a known successful video, and require
        # explicit confirmation for a previous upload with an unknown outcome.
        try:
            journal = load_upload_journal()
            # A user may change the title after restarting. Check the actual
            # source file too, not just the future renamed destination.
            old_attempt = (
                journal.get(os.path.normcase(os.path.abspath(file_path)))
                or journal.get(os.path.normcase(os.path.abspath(new_path)))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logging.exception("Cannot read upload journal safely")
            messagebox.showerror("Upload history error", str(exc), parent=root)
            return
        if old_attempt and old_attempt.get("video_id"):
            messagebox.showerror(
                "Video already uploaded",
                "This recording has an existing YouTube video ID:\n"
                f"{old_attempt['video_id']}\n\n"
                "Check YouTube Studio. This app will not upload it twice.",
                parent=root,
            )
            return
        if old_attempt and not messagebox.askyesno(
            "Previous upload may exist",
            "An earlier upload of this recording was interrupted. YouTube "
            "may already have received it.\n\n"
            "Have you checked YouTube Studio and confirmed that a NEW "
            "upload is needed?",
            parent=root,
            default=messagebox.NO,
        ):
            return

        # Prepare thumbnail BEFORE uploading so missing assets don't create
        # a video without its requested thumbnail. Do not touch base templates.
        thumbnail_path = None
        try:
            if is_general:
                if is_forever or get_generic_template(character, game_version):
                    thumbnail_path = generate_generic_thumbnail(character, effective_headline(), game_version)
            else:
                thumbnail_path = generate_thumbnail(
                    character=character,
                    dungeon=dungeon_id,
                    key_level=key_level,
                    spec=selected_spec,
                )
            # The generator uses a predictable filename; give this recording
            # its own filename so a later recording can't overwrite a pending one.
            if thumbnail_path and not is_general:
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
            save_settings(settings)
            if new_path != file_path:
                if os.path.exists(new_path):
                    messagebox.showerror(
                        "File already exists",
                        "A recording with this name already exists."
                    )
                    # Keep the generated thumbnail for diagnosis.
                    return
                os.rename(file_path, new_path)
                file_path = new_path
        except Exception as e:
            logging.exception("Could not rename video")
            messagebox.showerror("File error", str(e))
            return

        # Persist uncertainty BEFORE the first network request. A native crash
        # cannot be caught by the Python exception handler.
        try:
            record_upload_state(new_path, youtube_title, "uploading")
        except Exception as exc:
            logging.exception("Cannot persist upload state; upload not started")
            messagebox.showerror("Upload safety error", str(exc), parent=root)
            return

        root.destroy()
        try:
            video_id = upload_video(
                youtube, new_path, youtube_title, character, realm, selected_spec,
                notes=notes, mythic_plus=not is_general,
                game_version=game_version,
            )
        except Exception as exc:
            logging.exception("Video upload failed: %s", new_path)
            try:
                record_upload_state(new_path, youtube_title, "needs_review")
            except Exception:
                logging.exception("Cannot mark upload for manual review")
            print("Video upload failed. Local files were retained.")
            logging.error("Local files retained for manual recovery: %s | %s", new_path, thumbnail_path)
            show_error_dialog(
                "YouTube Uploader - Upload not completed",
                f"The upload of {youtube_title} stopped.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "The local recording and any generated thumbnail were kept. Check YouTube "
                "Studio before trying a NEW upload: the server may have "
                "received the video even if confirmation was lost.\n\n"
                "See uploader.log for details."
            )
            return

        try:
            record_upload_state(new_path, youtube_title, "uploaded", video_id)
        except Exception:
            logging.exception("Uploaded video ID %s could not be journaled", video_id)

        # The video was created. Record its ID BEFORE attempting the thumbnail;
        # a thumbnail failure must never trigger a second video upload.
        record = {
            "video_path": new_path,
            "thumbnail_path": thumbnail_path,
        }
        try:
            if thumbnail_path:
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
            clear_upload_state(new_path)
            if original_path != new_path:
                clear_upload_state(original_path)
        except Exception:
            logging.exception("Could not clear upload journal for %s", video_id)

        while thumbnail_path:
            try:
                upload_thumbnail(youtube, video_id, thumbnail_path)
                break
            except Exception as exc:
                logging.exception(
                    "Video %s uploaded, but thumbnail failed. Files retained.", video_id
                )
                retry = show_error_dialog(
                    "YouTube Uploader - Thumbnail upload failed",
                    f"The video is ALREADY uploaded:\n"
                    f"https://www.youtube.com/watch?v={video_id}\n\n"
                    f"Thumbnail error: {type(exc).__name__}: {exc}\n\n"
                    "Retry uploads ONLY the thumbnail to this video. "
                    "Cancel retains the MP4 and thumbnail; the thumbnail "
                    "will be retried next time the uploader starts.",
                    retry=True,
                )
                if not retry:
                    return

        delete_after_thumbnail_success(record)
        try:
            if thumbnail_path:
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

    # Unlike Skip, Later keeps the file eligible for recovery on next launch.
    tk.Button(
        button_frame,
        text="Later",
        width=12,
        command=root.destroy,
    ).pack(side="left", padx=5)

    def apply_upload_mode():
        is_forever = selected_game() == "forever"
        if is_forever:
            general_mode.set(True)
        if general_mode.get():
            mythic_frame.pack_forget()
            general_frame.pack(before=button_frame)
            root.geometry("620x790")
            root.title("WoW Forever — Journey to 60" if is_forever else "Other WoW Video — Retail")
            spec_label.config(text="Class/spec (optional):" if is_forever else "Spec (optional):")
            other_button.config(text="Back to Mythic+")
        else:
            general_frame.pack_forget()
            mythic_frame.pack(before=button_frame)
            root.geometry("620x670")
            root.title("New WoW Recording — Retail")
            spec_label.config(text="Spec:")
            other_button.config(text="Other WoW video…")
        if is_forever:
            other_button.pack_forget()
        else:
            other_button.pack(pady=(8, 12))
        update_thumbnail_status()

    def toggle_upload_mode():
        if selected_game() == "forever":
            return
        general_mode.set(not general_mode.get())
        apply_upload_mode()

    other_button = tk.Button(root, text="Other WoW video…", width=25, command=toggle_upload_mode)
    other_button.pack(pady=(8, 12))

    def game_changed(event=None):
        nonlocal characters, active_game
        if active_game:
            game_drafts[active_game] = (character_combo.get(), spec_combo.get(), general_mode.get())
        active_game = selected_game()
        characters = get_wow_characters(active_game)
        values = [item["display"] for item in characters]
        is_forever = active_game == "forever"
        character_combo.config(values=([""] + values) if is_forever else values)
        character_label.config(text="Character (optional until created):" if is_forever else "Character:")
        spec_combo.config(values=[] if is_forever else SPECS, state="normal" if is_forever else "readonly")
        profile = character_profile()
        saved_character = profile.get("last_character", "")
        draft = game_drafts.get(active_game)
        selection = draft[0] if draft else saved_character
        character_combo.set(selection if selection in values else ("" if is_forever or not values else values[0]))
        character_changed()
        if draft:
            spec_combo.set(draft[1])
        general_mode.set(True if is_forever else (draft[2] if draft else False))
        apply_upload_mode()

    game_combo.bind("<<ComboboxSelected>>", game_changed)
    game_changed()

    def enter_pressed(event):
        # Enter inserts a newline while writing the optional description.
        if event.widget is description_entry:
            return
        upload()
        return "break"

    root.bind("<Return>", enter_pressed)

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
        self.pending = queue.Queue()
        self._queued_paths = set()
        self._queue_lock = threading.Lock()

    def enqueue_path(self, file_path, reason="watchdog"):
        """Watchdog only enqueues paths; it must never create a Tk window."""
        if not file_path.lower().endswith(".mp4"):
            return False
        file_path = os.path.abspath(file_path)
        key = os.path.normcase(file_path)
        with self._queue_lock:
            known = {os.path.normcase(os.path.abspath(path)) for path in self.uploaded}
            if key in known or key in self._queued_paths:
                return False
            self._queued_paths.add(key)
        self.pending.put(file_path)
        logging.info("Recording queued (%s): %s", reason, file_path)
        return True

    def completed_path(self, file_path):
        with self._queue_lock:
            self._queued_paths.discard(os.path.normcase(os.path.abspath(file_path)))
        self.pending.task_done()

    def on_created(
        self,
        event
    ):
        if event.is_directory:
            return
        self.enqueue_path(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        # A recording deliberately moved OUT and BACK IN may be recovered.
        # Do not treat our own in-folder rename as a new recording.
        source_parent = os.path.normcase(os.path.abspath(os.path.dirname(event.src_path)))
        watch_parent = os.path.normcase(os.path.abspath(WATCH_FOLDER))
        if source_parent != watch_parent:
            self.enqueue_path(event.dest_path, reason="moved into Captures")


def offer_existing_recordings(handler):
    """Recover after a crash only with explicit user approval (no auto-reupload)."""
    existing = []
    journal = load_upload_journal()
    known = {os.path.normcase(os.path.abspath(p)) for p in handler.uploaded}
    for name in sorted(os.listdir(WATCH_FOLDER)):
        if name.lower().endswith(".mp4"):
            path = os.path.join(WATCH_FOLDER, name)
            key = os.path.normcase(os.path.abspath(path))
            if journal.get(key, {}).get("video_id"):
                logging.warning(
                    "Not requeuing %s: already has YouTube video ID %s",
                    path, journal[key]["video_id"],
                )
            elif key not in known:
                existing.append(path)
    if not existing:
        return

    logging.warning("Found %s pre-existing recordings not in uploaded history", len(existing))
    examples = "\n".join("  " + os.path.basename(p) for p in existing[:5])
    if len(existing) > 5:
        examples += f"\n  ... and {len(existing) - 5} more"
    dialog = tk.Tk()
    dialog.withdraw()
    dialog.attributes("-topmost", True)
    try:
        approved = messagebox.askyesno(
            "YouTube Uploader - Recover recordings?",
            f"Found {len(existing)} recordings left in Captures:\n\n{examples}\n\n"
            "Some may have reached YouTube before the previous crash. "
            "Check YouTube Studio before uploading one again.\n\n"
            "Queue these files for review? Uploads will only start if you "
            "choose Upload in each recording window. Use Later to leave a "
            "file untouched. Default is No.",
            parent=dialog,
            default=messagebox.NO,
        )
    finally:
        dialog.destroy()
    if approved:
        for path in existing:
            handler.enqueue_path(path, reason="approved crash recovery")


# ============================================================
# MAIN
# ============================================================

def main():
    logging.info("Uploader process started: pid=%s, executable=%s", os.getpid(), sys.executable)
    print(
        "Connecting to YouTube..."
    )

    youtube = connect_with_recovery()

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
        # Watchdog runs on its own thread. Tkinter, all popups, and the YouTube
        # API client run exclusively on this main thread, one recording at a time.
        offer_existing_recordings(event_handler)
        while True:
            try:
                file_path = event_handler.pending.get(timeout=1)
            except queue.Empty:
                continue

            try:
                if file_path in uploaded or not os.path.isfile(file_path):
                    continue
                if not wait_until_finished(file_path):
                    logging.warning("Recording disappeared while waiting: %s", file_path)
                    continue
                logging.info("Opening recording popup: %s", file_path)
                show_title_popup(file_path, youtube, uploaded)
            except Exception as exc:
                logging.exception("Could not process recording: %s", file_path)
                show_error_dialog(
                    "YouTube Uploader - Recording error",
                    f"Could not handle {os.path.basename(file_path)}:\n"
                    f"{type(exc).__name__}: {exc}\n\n"
                    "The local recording was not intentionally deleted. "
                    "Check uploader.log and restart to review the recording again.",
                )
            finally:
                event_handler.completed_path(file_path)

    except KeyboardInterrupt:
        logging.info("Uploader stopped via KeyboardInterrupt")
    finally:
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
    # A native crash (e.g. 0xc0000005 in Tk/ntdll) bypasses normal Python
    # exceptions. Keep a dedicated traceback of all Python threads for it.
    crash_log = open(os.path.join(BASE_DIR, "uploader_crash.log"), "a", encoding="utf-8")
    faulthandler.enable(file=crash_log, all_threads=True)
    try:
        main()
    except Exception as exc:
        logging.exception("Uploader stopped due to an unexpected error")
        show_error_dialog(
            "YouTube Uploader - Stopped",
            f"The uploader stopped: {type(exc).__name__}: {exc}\n\n"
            "Your recordings have not been intentionally deleted. "
            "See uploader.log for details. Restart the scheduled task "
            "after resolving the error."
        )
        raise
    finally:
        faulthandler.disable()
        crash_log.close()
        ctypes.windll.kernel32.CloseHandle(mutex)
