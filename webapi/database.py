# webapi/database.py

import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK (Make sure you have the correct path to the Firebase service account key JSON file)
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

# Firestore collection
COLLECTION_NAME = "tasks"
