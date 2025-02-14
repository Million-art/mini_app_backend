from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from firebase_admin import credentials, firestore
import firebase_admin
import json
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import logging
import uvicorn

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
firebase_config = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

# Initialize Firestore
db = firestore.client()

# FastAPI application
app = FastAPI()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define request model
class ClaimTaskRequest(BaseModel):
    user_id: str
    task_id: str

# Helper function to get Firestore document
def get_firestore_document(collection: str, doc_id: str):
    doc_ref = db.collection(collection).document(doc_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"{collection.capitalize()} not found")
    return doc_ref, doc.to_dict()

@app.post("/claim-task/")
async def claim_task(request: ClaimTaskRequest):
    try:
        # Get user document
        user_ref, user_data = get_firestore_document("users", request.user_id)
        if "completedTasks" in user_data and request.task_id in user_data["completedTasks"]:
            raise HTTPException(status_code=400, detail="Task already claimed")
        
        # Get task document
        task_ref, task_data = get_firestore_document("tasks", request.task_id)
        task_points = task_data.get("point", 0)
        if not isinstance(task_points, (int, float)):
            raise HTTPException(status_code=400, detail="Task points must be a valid number")
        
        # Update user's balance and completed tasks
        user_ref.update({
            "balance": firestore.Increment(task_points),
            "completedTasks": firestore.ArrayUnion([request.task_id])
        })

        # Fetch updated user data
        updated_user_data = user_ref.get().to_dict()
        return {
            "message": "Task claimed successfully",
            "new_balance": updated_user_data.get("balance", 0),
            "completed_tasks": updated_user_data.get("completedTasks", [])
        }
    except HTTPException as e:
        logger.error(f"HTTP Error: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

# Run the application when executed directly
if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=PORT)