import os
import json
import requests
import asyncio
import datetime
from telebot.async_telebot import AsyncTeleBot
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from dotenv import load_dotenv
from http.server import BaseHTTPRequestHandler, HTTPServer
from .message import get_welcome_messages

# Load environment variables
load_dotenv()

# Initialize Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase
firebase_config = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "mrjohn-8ee8b.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

# Function to generate main keyboard with language selection
def generate_main_keyboard(selected_language=None):
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    languages = {
        "language_english": "🇬🇧 English",
        "language_chinese": "🇨🇳 Chinese",
        "language_spanish": "🇪🇸 Spanish"
    }

    buttons = []
    for callback_data, label in languages.items():
        if selected_language and callback_data.endswith(selected_language):
            label += " ✅"
        buttons.append(types.InlineKeyboardButton(label, callback_data=callback_data))

    keyboard.add(*buttons)
    keyboard.add(
        types.InlineKeyboardButton("📢 Join Channel", url="https://t.me/mrbeas_group"),
        types.InlineKeyboardButton("🚀 Launch App", web_app=types.WebAppInfo(url="https://mrb-theta.vercel.app")),
        types.InlineKeyboardButton("🌐 Visit Website", url="https://www.mrbeas.net")
    )
    return keyboard


@bot.message_handler(commands=['start'])
async def start(message):
    user_id = str(message.from_user.id)
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        # Safely extract user data
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        username = message.from_user.username or ""
        is_premium = getattr(message.from_user, 'is_premium', False)  # Handle missing attribute
        language_code = None  # Default to None, to be set later

        user_data = {
            'firstName': first_name,
            'lastName': last_name,
            'username': username,
            'languageCode': language_code,
            'isPremium': is_premium,
            'referrals': {},
            'balance': 0,
            'completedTasks': [],
            'daily': {'claimedTime': None, 'claimedDay': 0},
            'WalletAddress': None,
        }

        text = message.text.split()

        if len(text) > 1 and text[1].startswith('ref_'):
            referrer_id = text[1][4:]
            referrer_ref = db.collection('users').document(referrer_id)
            referrer_doc = referrer_ref.get()

            if referrer_doc.exists:
                user_data['referredBy'] = referrer_id
                referrer_data = referrer_doc.to_dict()
                bonus_amount = 500 if is_premium else 100
                current_balance = referrer_data.get('balance', 0)
                new_balance = current_balance + bonus_amount

                referrals = referrer_data.get('referrals', {})
                referrals[user_id] = {
                    'addedValue': bonus_amount,
                    'firstName': first_name,
                    'lastName': last_name,
                }

                referrer_ref.update({
                    'balance': new_balance,
                    'referrals': referrals
                })
            else:
                user_data['referredBy'] = None

        if not user_doc.exists:
            user_ref.set(user_data)
        else:
            user_data = user_doc.to_dict()

        # Set default language to English if not set
        selected_language = user_data.get('languageCode', 'english')

        # Retrieve welcome message
        welcome_messages = get_welcome_messages(first_name)
        welcome_message = welcome_messages.get(selected_language, welcome_messages['english'])

        keyboard = generate_main_keyboard(selected_language)
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)

    except Exception as e:
        error_message = "Error. Please try again!"
        await bot.send_message(message.chat.id, error_message)
        print(f"Error occurred: {str(e)}")

# Handle language selection callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('language_'))
async def language_selection(call):
    user_id = str(call.from_user.id)
    selected_language = call.data.split('_')[1]

    user_ref = db.collection('users').document(user_id)
    user_ref.update({'languageCode': selected_language})

    # Use the imported function to get the welcome messages
    welcome_messages = get_welcome_messages(call.from_user.first_name)

    welcome_message = welcome_messages.get(selected_language, welcome_messages['english'])
    keyboard = generate_main_keyboard(selected_language)
    await bot.edit_message_text(welcome_message, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=keyboard)

# HTTP Server to handle updates from Telegram Webhook
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])  
        post_data = self.rfile.read(content_length)
        update_dict = json.loads(post_data.decode('utf-8'))

        asyncio.run(self.process_update(update_dict))

        self.send_response(200)
        self.end_headers()

    async def process_update(self, update_dict):
        update = types.Update.de_json(update_dict)
        await bot.process_new_updates([update])

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write('Hello, BOT is running!'.encode('utf-8'))

# Start polling
# if __name__ == '__main__':
#     print("Bot is polling...")
#     asyncio.run(bot.polling())
