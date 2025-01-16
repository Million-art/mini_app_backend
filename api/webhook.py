from http.server import BaseHTTPRequestHandler
import os
import json
import asyncio
from telebot.async_telebot import AsyncTeleBot  
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

# Load environment variables
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

def generate_start_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Open Web App", web_app=WebAppInfo(url="https://mrb-crypto.vercel.app")))
    return keyboard

@bot.message_handler(commands=['start'])  
async def start(message):
    user_id = str(message.from_user.id)
    
    # Fetch user data from Firestore
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    # If the user doesn't exist in Firestore, create a new user
    if not user_doc.exists:
        user_data = {
            'userImage': None,
            'firstName': message.from_user.first_name,
            'lastName': message.from_user.last_name,
            'username': message.from_user.username,
            'languageCode': None,  # Set languageCode to None initially
            'isPremium': message.from_user.is_premium,
            'balance': 0,
            'daily': {'claimedTime': None, 'claimedDay': 0},
            'WalletAddress': None,
        }

        # Check for referral ID
        referrer_id = extract_referrer_id(message.text)
        if referrer_id:
            await handle_referral(referrer_id, user_data, user_id)

        await save_user_data(user_id, user_data)
        
        # Ask the user to select a language
        keyboard = generate_language_keyboard()
        welcome_message = "Welcome! Please select your language."
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)

    else:
        # If the user already exists, check if language is set
        user_data = user_doc.to_dict()
        if user_data.get('languageCode') is None:
            # If no language is set, prompt them to select one
            keyboard = generate_language_keyboard()
            welcome_message = "Welcome! Please select your language."
            await bot.reply_to(message, welcome_message, reply_markup=keyboard)
        else:
            # If language is already set, send the welcome message
            language_code = user_data['languageCode']
            welcome_message = get_welcome_message(language_code, message.from_user.first_name)
            keyboard = generate_start_keyboard()
            await bot.reply_to(message, welcome_message, reply_markup=keyboard)

def extract_referrer_id(text):
    if len(text.split()) > 1 and text.split()[1].startswith('ref_'):
        return text.split()[1][4:]
    return None

async def handle_referral(referrer_id, user_data, user_id):
    referrer_ref = db.collection('users').document(referrer_id)
    referrer_doc = referrer_ref.get()

    if referrer_doc.exists:
        referrer_data = referrer_doc.to_dict()
        bonus_amount = 500 if user_data['isPremium'] else 100
        new_balance = referrer_data.get('balance', 0) + bonus_amount

        referrals = referrer_data.get('referrals', {})
        referrals[user_id] = {'addedValue': bonus_amount, 'firstName': user_data['firstName'], 'lastName': user_data['lastName'], 'userImage': None}

        referrer_ref.update({'balance': new_balance, 'referrals': referrals})
        user_data['referredBy'] = referrer_id
    else:
        user_data['referredBy'] = None

async def save_user_data(user_id, user_data):
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        user_ref.set(user_data)

@bot.callback_query_handler(func=lambda call: call.data.startswith('language_'))
async def language_selection(call):
    user_id = str(call.from_user.id)
    selected_language = call.data.split('_')[1]

    user_ref = db.collection('users').document(user_id)
    user_ref.update({'languageCode': selected_language})

    welcome_message = get_welcome_message(selected_language, call.from_user.first_name)
    keyboard = generate_start_keyboard()
    await bot.send_message(user_id, welcome_message, reply_markup=keyboard)

def get_welcome_message(language_code, first_name):
    messages = {
        'english': f"Hello {first_name}! 👋\n\nWelcome to Mr. John.\nHere you can earn coins!\nInvite friends to earn more coins together, and level up faster! 🧨",
        'chinese': f"你好 {first_name}！👋\n\n欢迎来到Mr. John。\n在这里你可以赚取硬币！\n邀请朋友一起赚取更多硬币，快速升级！🧨",
        'spanish': f"¡Hola {first_name}! 👋\n\nBienvenido a Mr. John.\n¡Aquí puedes ganar monedas!\nInvita amigos para ganar más monedas juntos y subir de nivel más rápido! 🧨"
    }
    return messages.get(language_code, messages['english'])

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
