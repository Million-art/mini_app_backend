from http.server import BaseHTTPRequestHandler
import os
import json
import asyncio
import requests
from telebot.async_telebot import AsyncTeleBot
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

load_dotenv()

# Initialize bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase
firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "mrjohn-8ee8b.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

def generate_language_keyboard():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(InlineKeyboardButton("🇬🇧 English", callback_data="language_english"))
    keyboard.add(InlineKeyboardButton("🇨🇳 Chinese", callback_data="language_chinese"))
    keyboard.add(InlineKeyboardButton("🇪🇸 Spanish", callback_data="language_spanish"))
    
    return keyboard

# Handle '/start' command
@bot.message_handler(commands=['start'])
async def start(message):
    # Send language selection keyboard
    user_id = str(message.from_user.id)
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            # Initialize user data without language selected yet
            user_data = {
                'firstName': message.from_user.first_name,
                'lastName': message.from_user.last_name,
                'username': message.from_user.username,
                'languageCode': None,
                'isPremium': message.from_user.is_premium,
                'balance': 0,
                'daily': {'claimedTime': None, 'claimedDay': 0},
                'WalletAddress': None
            }
            user_ref.set(user_data)

        # Ask user to select a language
        keyboard = generate_language_keyboard()
        await bot.reply_to(message, "Please select your language:", reply_markup=keyboard)

    except Exception as e:
        await bot.reply_to(message, "Error occurred. Please try again.")
        print(f"Error occurred: {str(e)}")

# Handle language selection callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('language_'))
async def language_selection(call):
    user_id = str(call.from_user.id)
    selected_language = call.data.split('_')[1]
    
    # Save the selected language in the user's data
    user_ref = db.collection('users').document(user_id)
    user_ref.update({'languageCode': selected_language})

    # Define welcome messages in different languages
    messages = {
        'english': f"Hello {call.from_user.first_name}! 👋\n\nWelcome to Mr. John.\nHere you can earn coins!\nInvite friends to earn more coins together, and level up faster! 🧨",
        'chinese': f"你好 {call.from_user.first_name}！👋\n\n欢迎来到Mr. John。\n在这里你可以赚取硬币！\n邀请朋友一起赚取更多硬币，快速升级！🧨",
        'spanish': f"¡Hola {call.from_user.first_name}! 👋\n\nBienvenido a Mr. John.\n¡Aquí puedes ganar monedas!\nInvita amigos para ganar más monedas juntos y subir de nivel más rápido! 🧨"
    }

    # Send the welcome message based on selected language
    welcome_message = messages.get(selected_language, messages['english'])

    # Send the message along with the web app link
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Open Web App", web_app=WebAppInfo(url="https://mr-beas-lab.github.io/miniApp")))
    await bot.send_message(call.from_user.id, welcome_message, reply_markup=keyboard)

# Handle incoming updates
class handler(BaseHTTPRequestHandler):
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
