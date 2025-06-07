import os
import json
import requests
import asyncio
import datetime
import logging
from telebot.async_telebot import AsyncTeleBot
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from dotenv import load_dotenv
from http.server import BaseHTTPRequestHandler, HTTPServer
from .message import get_welcome_messages

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase
try:
    firebase_config = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred, {'storageBucket': "mrjohn-8ee8b.appspot.com"})
    db = firestore.client()
    bucket = storage.bucket()
    logger.info("Firebase initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {str(e)}")
    raise

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
    logger.info(f"Processing start command for user {user_id}")
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        # Safely extract user data
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        username = message.from_user.username or ""
        is_premium = getattr(message.from_user, 'is_premium', False)
        language_code = None

        logger.info(f"User data extracted - Name: {first_name}, Username: {username}")

        # Initialize user data
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

        # Handle referral link
        try:
            text = message.text.split()
            logger.info(f"Message text: {message.text}")
            logger.info(f"Split text: {text}")
            
            if len(text) > 1 and text[1].startswith('ref_'):
                referrer_id = text[1][4:]
                logger.info(f"Extracted referrer_id: {referrer_id}")
                
                if referrer_id and referrer_id != user_id:  # Prevent self-referral
                    referrer_ref = db.collection('users').document(referrer_id)
                    referrer_doc = referrer_ref.get()
                    logger.info(f"Referrer document exists: {referrer_doc.exists}")

                    if referrer_doc.exists:
                        # Set referral data
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
                            'timestamp': firestore.SERVER_TIMESTAMP
                        }

                        logger.info(f"Updating referrer {referrer_id} with new balance: {new_balance}")
                        # Update referrer's data
                        referrer_ref.update({
                            'balance': new_balance,
                            'referrals': referrals
                        })
                        
                        # Send confirmation to referrer
                        try:
                            await bot.send_message(
                                referrer_id,
                                f"🎉 Congratulations! You received {bonus_amount} points for referring {first_name}!"
                            )
                            logger.info(f"Sent referral notification to {referrer_id}")
                        except Exception as e:
                            logger.error(f"Failed to send referral notification: {str(e)}")
                    else:
                        logger.warning(f"Referrer {referrer_id} not found in database")
                        user_data['referredBy'] = None
                else:
                    logger.warning(f"Invalid referral ID or self-referral attempt: {referrer_id}")
                    user_data['referredBy'] = None
        except Exception as e:
            logger.error(f"Error processing referral: {str(e)}")
            user_data['referredBy'] = None

        # Create or update user document
        if not user_doc.exists:
            logger.info(f"Creating new user document for {user_id}")
            user_ref.set(user_data)
        else:
            # Update existing user data
            existing_data = user_doc.to_dict()
            logger.info(f"Existing user data: {existing_data}")
            
            # Only update referral if it's not already set
            if not existing_data.get('referredBy') and user_data.get('referredBy'):
                logger.info(f"Updating referral for existing user {user_id}")
                update_data = {
                    'referredBy': user_data['referredBy'],
                    'firstName': first_name,
                    'lastName': last_name,
                    'username': username,
                    'isPremium': is_premium
                }
                user_ref.update(update_data)
                logger.info(f"Updated user data: {update_data}")

        # Set default language to English if not set
        selected_language = user_data.get('languageCode', 'english')

        # Retrieve welcome message
        welcome_messages = get_welcome_messages(first_name)
        welcome_message = welcome_messages.get(selected_language, welcome_messages['english'])

        keyboard = generate_main_keyboard(selected_language)
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)
        logger.info(f"Successfully processed start command for user {user_id}")

    except Exception as e:
        error_message = "An error occurred. Please try again later!"
        logger.error(f"Error in start command: {str(e)}", exc_info=True)
        await bot.send_message(message.chat.id, error_message)

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
        logger.info(f"Received webhook update: {update_dict}")

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
