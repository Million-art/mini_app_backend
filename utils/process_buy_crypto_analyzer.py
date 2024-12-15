from firebase_admin import credentials, firestore, storage
import datetime

# Initialize Firestore client
db = firestore.client()

def process_buy_crypto_analyzer(user_id):
    try:
        # Start a Firestore transaction
        def update_transaction(transaction):
            # Retrieve the user document in a transaction
            user_ref = db.collection('users').document(user_id)
            user_doc = transaction.get(user_ref)
            
            if not user_doc.exists:
                raise Exception("User not found.")
            
            user_data = user_doc.to_dict()

            # Check if the user has enough balance (assuming 'balance' field in user data)
            if user_data['balance'] < 5:
                raise Exception("Insufficient balance.")

            # Subtract the 5$ from user's balance
            user_data['balance'] -= 5
            
            # Set BuyAnalyzerTool data
            now = datetime.datetime.now()
            expiration_date = now + datetime.timedelta(days=30)  # Add 1 month for the tool's duration

            user_data['BuyAnalyzerTool'] = {
                'duration': expiration_date,
                'amount': 5  # Record the amount paid
            }

            # Update the user document with the new balance and BuyAnalyzerTool data
            transaction.update(user_ref, user_data)

        # Execute the transaction to ensure atomicity
        db.run_transaction(update_transaction)

        # Return success response
        return {"message": "Purchase successful! Premium access granted."}

    except Exception as e:
        # Log and return error
        print(f"Error occurred: {str(e)}")
        return {"error": f"Error processing purchase: {str(e)}"}

