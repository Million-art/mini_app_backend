import os
import json
import datetime
from dotenv import load_dotenv
from firebase_admin import credentials, firestore, storage
import firebase_admin
from telethon import TelegramClient, events
from fastapi import FastAPI, Request

# Load environment variables
load_dotenv()

# Firebase Initialization
firebase_config = json.loads(os.environ.get("FIREBASE_SERVICE_ACCOUNT"))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "telegrambot-e70ab.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

# Telegram Client Setup
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# FastAPI Setup
app = FastAPI()


@app.post("/")
async def telegram_webhook(request: Request):
    """Handles incoming webhook updates."""
    try:
        update = await request.json()
        update = client._build_update(update)
        await client.updates_handler(update)
    except Exception as e:
        print(f"Error processing update: {e}")
    return {"ok": True}


@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    """Handles the /start command."""
    user = await client.get_entity(event.sender_id)
    user_id = str(user.id)
    user_first_name = user.first_name or ""
    user_last_name = user.last_name or ""
    user_username = user.username or ""
    user_image = None

    welcome_message = (
        f"Hello {user_first_name} {user_last_name}!\n\n"
        "Welcome to the bot! 🎉\n\n"
        "Start earning coins, invite friends, and have fun!"
    )

    # Check Firebase for user data
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        # Attempt to retrieve the user's profile photo
        photos = await client.get_profile_photos(user)
        if photos.total > 0:
            profile_photo = await client.download_media(photos[0])
            # Upload to Firebase storage
            blob = bucket.blob(f"images/{user_id}.jpg")
            blob.upload_from_filename(profile_photo)
            user_image = blob.generate_signed_url(datetime.timedelta(days=365), method="GET")

        # Create user data in Firebase
        user_data = {
            "userImage": user_image,
            "firstName": user_first_name,
            "lastName": user_last_name,
            "username": user_username,
            "balance": 0,
            "mineRate": 0.001,
            "isMining": False,
            "miningStartTime": None,
            "daily": {"claimedTime": None, "claimedDay": 0},
        }

        user_ref.set(user_data)

    await event.respond(welcome_message)


@app.get("/")
def root():
    return {"message": "Bot is running!"}
