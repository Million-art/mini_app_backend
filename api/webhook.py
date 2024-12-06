from fastapi import FastAPI, Request
from telebot import TeleBot, types
import os
import json
import requests
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, storage
import datetime

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Initialize Telegram Bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = TeleBot(BOT_TOKEN)

# Initialize Firebase
firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "telegrambot-e70ab.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

# Generate Start Keyboard
def generate_start_keyboard():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Open Web App", web_app=WebAppInfo(url="https://mrjohnsart.netlify.app")))
    return keyboard

# Webhook route to receive updates from Telegram
@app.post("/webhook")
async def webhook(request: Request):
    # Parse incoming update from Telegram
    json_update = await request.json()
    update = types.Update.de_json(json_update)
    # Process the update
    bot.process_new_updates([update])
    return {"status": "ok"}

# Set the webhook URL dynamically based on your environment
def set_webhook():
    # Replace this with the correct URL of your app or ngrok URL during development
    webhook_url = "https://mini-app-backend-mu.vercel.app/webhook"  # Replace with your actual public URL
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)

# Call this function during startup to set the webhook
set_webhook()

# Telegram bot command handler
@bot.message_handler(commands=['start'])
def start(message):
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
            photos = bot.get_user_profile_photos(user_id, limit=1)   
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id  
                file_info = bot.get_file(file_id)
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
                else:
                    user_image = None
            else:
                user_image = None

            # Prepare user data
            user_data = {
                'userImage': user_image,
                'firstName': user_first_name,
                'lastName': user_last_name,
                'username': user_username,
                'languageCode': user_language_code,
                'isPremium': is_premium,
                'balance': 0,
                'mineRate': 0.001,
                'isMining': False,
                'miningStartTime': None,
                'daily': {
                    'claimedTime': None,
                    'claimedDay': 0
                },
                'links': None
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

        # Send the welcome message with the keyboard
        keyboard = generate_start_keyboard()
        bot.reply_to(message, welcome_message, reply_markup=keyboard)  
    except Exception as e:
        error_message = "Error. Please try again!"
        bot.reply_to(message, error_message)  
        print(f"Error occurred: {str(e)}")

# Start FastAPI app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
