from http.server import BaseHTTPRequestHandler
import os
import sys
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
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), '../utils'))
from validation import validate_api_keys # Import the validation function
# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))

# Initialize bot
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "mrjohn-8ee8b.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

# Configure logging
logging.basicConfig(level=logging.INFO)

def generate_start_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Open Web App", web_app=WebAppInfo(url="https://mini-app-frontend-bu51.vercel.app")))
    return keyboard

@bot.message_handler(commands=['start'])  
async def start(message):
    user_id = str(message.from_user.id)
    user_first_name = str(message.from_user.first_name)
    user_last_name = message.from_user.last_name
    user_username = message.from_user.username
    user_language_code = str(message.from_user.language_code)
    is_premium = message.from_user.is_premium
    text = message.text.split()
    welcome_message = (
        f"Hello {user_first_name} {user_last_name}! 👋\n\n"
        f"Welcome to Mr. John.\n\n"
        f"Here you can earn coins!\n\n"
        f"Invite friends to earn more coins together, and level up faster! 🧨\n"
    )

    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            user_image = None
            try:
                # Attempt to retrieve the profile picture
                photos = await bot.get_user_profile_photos(user_id, limit=1)
                if photos.total_count > 0:
                    file_id = photos.photos[0][-1].file_id
                    file_info = await bot.get_file(file_id)
                    file_path = file_info.file_path
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

                    # Download the image
                    response = requests.get(file_url)
                    response.raise_for_status()
                    
                    # Upload to Firebase storage
                    blob = bucket.blob(f"images/{user_id}.jpg")
                    blob.upload_from_string(response.content, content_type="image/jpeg")

                    # Generate the public URL
                    user_image = blob.generate_signed_url(datetime.timedelta(days=365), method='GET')
            except Exception as e:
                logging.error(f"Profile picture processing failed for user {user_id}: {str(e)}")

            # Prepare user data
            user_data = {
                'userImage': user_image,
                'firstName': user_first_name,
                'lastName': user_last_name,
                'username': user_username,
                'languageCode': user_language_code,
                'isPremium': is_premium,
                'balance': 0,
                'daily': {
                    'claimedTime': None,
                    'claimedDay': 0
                },
                'WalletAddress': None,
                'exchangeKey': {
                    'apiKey': None,
                    'secretKey': None,
                },
            }

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
                        'firstName': user_first_name,
                        'lastName': user_last_name,
                        'userImage': user_image,
                    }

                    referrer_ref.update({
                        'balance': new_balance,
                        'referrals': referrals
                    })
                else:
                    user_data['referredBy'] = None

            user_ref.set(user_data)

        keyboard = generate_start_keyboard()
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)
    except Exception as e:
        error_message = "Error. Please try again!"
        await bot.reply_to(message, error_message)
        logging.error(f"Error occurred: {str(e)}")


def generate_add_api_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Binance", callback_data='add_api_keys_binance'))
    keyboard.add(types.InlineKeyboardButton("BingX", callback_data='add_api_keys_bingx'))
    keyboard.add(types.InlineKeyboardButton("Bybit", callback_data='add_api_keys_bybit'))
    return keyboard

@bot.message_handler(commands=['addapikey'])
async def add_api_keys(message):
    keyboard = generate_add_api_keyboard()
    await bot.reply_to(message, "Please select an exchange to add API keys:", reply_markup=keyboard)

# Dictionary to store user states
user_states = {}

# Define available exchanges
AVAILABLE_EXCHANGES = ['binance', 'bingx', 'bybit']

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_api_keys'))
async def handle_api_key_selection(call):
    exchange = call.data.split('_')[-1].lower()

    if exchange not in AVAILABLE_EXCHANGES:
        await bot.answer_callback_query(call.id, "The selected exchange is not available. ❌")
        await bot.send_message(call.message.chat.id, "Please choose a valid exchange from the list.")
        return

    user_states[call.from_user.id] = {'step': 'api_key', 'exchange': exchange}

    await bot.answer_callback_query(call.id, f"You selected {exchange}. Please provide your API key.")
    await bot.send_message(call.message.chat.id, f"Please enter your {exchange} API key:")

@bot.message_handler(func=lambda message: message.chat.id in user_states)
async def handle_api_and_secret_keys(message):
    user_id = message.chat.id
    user_state = user_states.get(user_id)

    if not user_state:
        return

    step = user_state.get('step')
    exchange = user_state.get('exchange')

    if step == 'api_key':
        user_state['api_key'] = message.text
        user_state['step'] = 'secret_key'
        await bot.send_message(user_id, f"API Key received. Now, please provide your {exchange} Secret Key:")
    
    elif step == 'secret_key':
        user_state['secret_key'] = message.text
        is_valid = await validate_api_keys(user_state['api_key'], user_state['secret_key'], exchange)

        if is_valid:
            await bot.send_message(user_id, "API keys are valid! ✅")
        else:
            await bot.send_message(user_id, "Invalid API keys. Please try again. ❌")
        
        del user_states[user_id]

@bot.message_handler(commands=['help'])
async def send_help(message):
    help_text = (
        "/start - Start the bot\n"
        "/addapikey - Add your API keys\n"
        "/help - Show available commands"
    )
    await bot.reply_to(message, help_text)

# Define the bot commands
async def set_bot_commands():
    commands = [
        types.BotCommand("/start", "Start the bot"),
        types.BotCommand("/addapikey", "Add your API keys"),
        types.BotCommand("/help", "Show available commands")
    ]
    await bot.set_my_commands(commands)

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

if __name__ == '__main__':
    from http.server import HTTPServer
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, handler)
    print('Running server...')
    httpd.serve_forever()
