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


load_dotenv()
# Initialize bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
print(BOT_TOKEN)
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase

firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "mrjohn-8ee8b.appspot.com"})
db = firestore.client()
bucket = storage.bucket()


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
                    if response.status_code == 200:
                        # Upload to Firebase storage
                        blob = bucket.blob(f"images/{user_id}.jpg")
                        blob.upload_from_string(response.content, content_type="image/jpeg")

                        # Generate the public URL
                        user_image = blob.generate_signed_url(datetime.timedelta(days=365), method='GET')
            except Exception as e:
                print(f"Profile picture processing failed for user {user_id}: {str(e)}")

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
                'exchangeKey':{
                    'apiKey':None,
                    'secretKey':None,
                    'exchange': None,
                },
            }

            if len(text) > 1 and text[1].startswith('ref_'):
                referrer_id = text[1][4:]
                referrer_ref = db.collection('users').document(referrer_id)
                referrer_doc = referrer_ref.get()

                if referrer_doc.exists():
                    user_data['referredBy'] = referrer_id
                    referrer_data = referrer_doc.to_dict()
                    bonus_amount = 500 if is_premium else 100
                    current_balance = referrer_data.get('balance', 0)
                    new_balance = current_balance + bonus_amount

                    referrals = referrer_data.get('referrals', {})
                    if referrals is None:
                        referrals = {}
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
        print(f"Error occurred: {str(e)}")
@bot.message_handler(commands=['addapikey'])
async def add_api_key(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Binance", callback_data='Binance'))
    markup.add(types.InlineKeyboardButton("BingX", callback_data='BingX'))
    markup.add(types.InlineKeyboardButton("Bybit", callback_data='Bybit'))
    await bot.send_message(message.chat.id, "Please choose your exchange:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['Binance', 'BingX', 'Bybit'])
async def handle_exchange_choice(call):
    exchange = call.data
    await bot.send_message(call.message.chat.id, f"Selected exchange: {exchange}\nPlease send me your API key.")
    bot.register_next_step_handler(call.message, lambda msg: handle_api_key(msg, exchange))

async def handle_api_key(message, exchange):
    api_key = message.text
    context = {
        'exchange': exchange,
        'api_key': api_key
    }
    await bot.send_message(message.chat.id, "API key received. Now, please send me your API secret.")
    bot.register_next_step_handler(message, lambda msg: handle_api_secret(msg, context))

async def handle_api_secret(message, context):
    user_id = message.from_user.id
    api_secret = message.text
    exchange = context['exchange']
    api_key = context['api_key']

    await bot.send_message(message.chat.id, "Validating...")

    # Verify the API key and secret for the selected exchange
    headers = {
        'X-MBX-APIKEY': api_key
    }
    try:
        if exchange == 'Binance':
            response = requests.get('https://api.binance.com/api/v3/account', headers=headers, auth=(api_key, api_secret))
        elif exchange == 'BingX':
            response = requests.get('https://api.bingx.com/api/v3/account', headers=headers, auth=(api_key, api_secret))
        elif exchange == 'Bybit':
            response = requests.get('https://api.bybit.com/v2/private/account', headers=headers, auth=(api_key, api_secret))

        if response.status_code == 200:
            db.collection('users').document(str(user_id)).update({
                'exchangeKey': {
                    'apiKey': api_key,
                    'secretKey': api_secret,
                    'exchange': exchange
                }
            })
            await bot.send_message(message.chat.id, 'API key and secret verified and stored successfully.')
        else:
            await bot.send_message(message.chat.id, 'Invalid API key or secret. Please try again with /addapikey.')
    except Exception as e:
        await bot.send_message(message.chat.id, f'Error verifying API key: {e}')

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

 