from aiohttp import web
import asyncio
import json
from telebot.async_telebot import AsyncTeleBot
import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
import requests
import datetime

# Initialize bot
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = AsyncTeleBot(BOT_TOKEN)

# Initialize Firebase
firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred, {'storageBucket': "telegrambot-e70ab.appspot.com"})
db = firestore.client()
bucket = storage.bucket()

async def start(message):
    user_id = str(message.from_user.id)  
    user_first_name = str(message.from_user.first_name) 
    user_last_name = message.from_user.last_name
    user_username = message.from_user.username
    user_language_code = str(message.from_user.language_code)
    is_premium = message.from_user.is_premium

    welcome_message = (  
        f"Hello {user_first_name} {user_last_name}! 👋\n\n"
        f"Welcome to Mr. John.\n\n"
        f"Here you can earn coins!\n\n"
        f"Invite friends to earn more coins together, and level up faster! 🧨\n"
    )

    await bot.send_message(message.chat.id, welcome_message)

    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            photos = await bot.get_user_profile_photos(user_id, limit=1)   
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id  
                file_info = await bot.get_file(file_id)
                file_path = file_info.file_path
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

                response = requests.get(file_url)
                if response.status_code == 200:
                    blob = bucket.blob(f"images/{user_id}.jpg")
                    blob.upload_from_string(response.content, content_type="image/jpeg")

                    user_image = blob.generate_signed_url(datetime.timedelta(days=365), method='GET')
                else:
                    user_image = None
            else:
                user_image = None

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

            user_ref.set(user_data)

        keyboard = generate_start_keyboard()
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)  
    except Exception as e:
        error_message = "Error. Please try again!"
        await bot.send_message(message.chat.id, error_message)  
        print(f"Error occurred: {str(e)}")

async def handle_webhook(request):
    update_dict = await request.json()  
    await bot.process_new_updates([types.Update.de_json(update_dict)])
    return web.Response(status=200)

app = web.Application()
app.router.add_post('/webhook', handle_webhook)

if __name__ == '__main__':
    web.run_app(app, port=5000)
