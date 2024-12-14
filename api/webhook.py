from http.server import BaseHTTPRequestHandler
import os
import json
import asyncio
import requests
import datetime
from telebot.async_telebot import AsyncTeleBot
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables.")
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase
firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "mrjohn-8ee8b.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

# Helper: Generate Start Keyboard
def generate_start_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Open Web App", web_app=WebAppInfo(url="https://mini-app-frontend-bu51.vercel.app")))
    return keyboard

# Bot Command: /start
@bot.message_handler(commands=['start'])
async def start(message):
    user_id = str(message.from_user.id)
    user_first_name = message.from_user.first_name or "Unknown"
    user_last_name = message.from_user.last_name or ""
    user_username = message.from_user.username or "No Username"
    user_language_code = message.from_user.language_code or "Unknown"
    is_premium = getattr(message.from_user, 'is_premium', False)
    ref_code = message.text.split()[1] if len(message.text.split()) > 1 else None

    welcome_message = (
        f"Hello {user_first_name} {user_last_name}! 👋\n\n"
        f"Welcome to Mr. John.\n\n"
        f"Here you can earn coins!\n\n"
        f"Invite friends to earn more coins together and level up faster! 🧨\n"
    )

    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            # Attempt to fetch and store profile image
            user_image = None
            try:
                photos = await bot.get_user_profile_photos(user_id, limit=1)
                if photos.total_count > 0:
                    file_id = photos.photos[0][-1].file_id
                    file = await bot.download_file_by_id(file_id)
                    blob = bucket.blob(f"images/{user_id}.jpg")
                    blob.upload_from_string(file.read(), content_type="image/jpeg")
                    user_image = blob.generate_signed_url(datetime.timedelta(days=365), method='GET')
            except Exception as e:
                print(f"Profile picture upload failed: {e}")

            # Create user data
            user_data = {
                'userImage': user_image,
                'firstName': user_first_name,
                'lastName': user_last_name,
                'username': user_username,
                'languageCode': user_language_code,
                'isPremium': is_premium,
                'balance': 0,
                'daily': {'claimedTime': None, 'claimedDay': 0},
                'WalletAddress': None,
                'exchangeKey': {'apiKey': None, 'secretKey': None, 'exchange': None},
            }

            # Handle referral logic
            if ref_code and ref_code.startswith('ref_'):
                referrer_id = ref_code[4:]
                referrer_ref = db.collection('users').document(referrer_id)
                referrer_doc = referrer_ref.get()
                if referrer_doc.exists:
                    bonus = 500 if is_premium else 100
                    referrer_data = referrer_doc.to_dict()
                    referrals = referrer_data.get('referrals', {})
                    referrals[user_id] = {'bonus': bonus, 'firstName': user_first_name}
                    referrer_ref.update({'balance': referrer_data.get('balance', 0) + bonus, 'referrals': referrals})
                    user_data['referredBy'] = referrer_id

            user_ref.set(user_data)

        keyboard = generate_start_keyboard()
        await bot.send_message(message.chat.id, welcome_message, reply_markup=keyboard)

    except Exception as e:
        print(f"Error in /start: {e}")
        await bot.send_message(message.chat.id, "An error occurred. Please try again later.")

# Command: Add API Key
@bot.message_handler(commands=['addapikey'])
async def add_api_key(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Binance", callback_data='Binance'))
    markup.add(types.InlineKeyboardButton("BingX", callback_data='BingX'))
    markup.add(types.InlineKeyboardButton("Bybit", callback_data='Bybit'))
    await bot.send_message(message.chat.id, "Please select your exchange:", reply_markup=markup)

# Callback: Exchange Choice
@bot.callback_query_handler(func=lambda call: call.data in ['Binance', 'BingX', 'Bybit'])
async def handle_exchange_choice(call):
    exchange = call.data
    await bot.send_message(call.message.chat.id, f"Selected: {exchange}\nSend your API key:")
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, lambda msg: handle_api_key(msg, exchange))

# Handle API Key
async def handle_api_key(message, exchange):
    api_key = message.text
    await bot.send_message(message.chat.id, "API key received. Send your API secret:")
    bot.register_next_step_handler_by_chat_id(message.chat.id, lambda msg: handle_api_secret(msg, exchange, api_key))

# Handle API Secret
async def handle_api_secret(message, exchange, api_key):
    api_secret = message.text
    user_id = str(message.from_user.id)
    try:
        # Validate API key/secret with the exchange
        response = requests.get(f"https://api.{exchange.lower()}.com/api/v3/account", auth=(api_key, api_secret))
        if response.status_code == 200:
            db.collection('users').document(user_id).update({'exchangeKey': {'apiKey': api_key, 'secretKey': api_secret, 'exchange': exchange}})
            await bot.send_message(message.chat.id, "API key validated and saved.")
        else:
            await bot.send_message(message.chat.id, "Invalid API credentials. Try again.")
    except Exception as e:
        print(f"API validation error: {e}")
        await bot.send_message(message.chat.id, "Error validating API key. Please try again.")

# Webhook Handler
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        asyncio.run(self.process_update(json.loads(post_data.decode('utf-8'))))
        self.send_response(200)
        self.end_headers()

    async def process_update(self, update_dict):
        update = types.Update.de_json(update_dict)
        await bot.process_new_updates([update])

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hello, the bot is running!")
