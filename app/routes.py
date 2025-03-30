from fastapi import APIRouter, UploadFile, HTTPException
from app.services import analyze_receipt
from db.init import create_supabase_client
from pydantic import BaseModel
from typing import List
from app.config import SAMPLE_UUID
from app.services import upload_file_to_supabase

router = APIRouter()
supabase = create_supabase_client()
class LoginRequest(BaseModel):
  email: str
  password: str

class AnalyzeRequest(BaseModel):
  user_id: str
  friends: List[str]

@router.post("/login/")
async def login(user: LoginRequest):
  try:
    auth_response = supabase.auth.sign_in_with_password({
      "email": user.email,
      "password": user.password
    })

    if "error" in auth_response and auth_response["error"]:
      raise HTTPException(status_code=401, detail="Invalid credentials.")

    return {
      "message": "Login successful",
      "access_token": auth_response.session.access_token,
      "refresh_token": auth_response.session.refresh_token,
      "user_id": auth_response.user.id
    }

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.post("/logout/")
async def logout():
    try:
        auth_response = supabase.auth.sign_out()
        return {"message": "Logout successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")

@router.post("/analyze_receipt/")
async def analyze(data: AnalyzeRequest, file: UploadFile):
	try:
		receipt_data = await analyze_receipt(file)

		receipt_insert = {
			"user_id": data.user_id,
			"restaurant_name": receipt_data["restaurant_name"],
			"total_amount": receipt_data["total_amount"],
			"tax": receipt_data["tax"],
			"service_charge": receipt_data["service_charge"],
			"currency": receipt_data["currency"]
		}

		receipt_response = supabase.table("receipts").insert(receipt_insert).execute()
		print(receipt_response)
		if not receipt_response.data:
			raise Exception("Failed to insert receipt.")

		receipt_id = receipt_response.data[0]["id"] 

		for item in receipt_data["items"]:
			item_insert = {
				"receipt_id": receipt_id,
				"item_name": item["item_name"],
				"quantity": item["quantity"],
				"unit_price": item["unit_price"],
				"variation": item.get("variation", [])
			}
			supabase.table("items").insert(item_insert).execute()
  
		for friend in data.friends:
			receipt_friends_insert = {
				"receipt_id": receipt_id,
        "friend_id": friend,
        "amount_paid": 0
			}
			supabase.table("receipt_friends").insert(receipt_friends_insert).execute()

		return {
			"message": "Receipt and items inserted successfully.",
			"data": {
				"receipt_id": receipt_id,
				"receipt_data": receipt_data,
			}
		}

	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
         
from fastapi import UploadFile, File, Form, Depends

@router.post("/friend")
async def add_friend(
    user_id: str = Form(...),
    name: str = Form(...),
    photo: UploadFile = File(None)
):
    try:
        url = None
        if photo:
            url, error = await upload_file_to_supabase(supabase, photo, "friend-photo")
            if error:
                raise HTTPException(
                    status_code=400 if "must be an image" in error else 500,
                    detail=error
                )

        friend_insert = {
            "user_id": user_id,
            "name": name,
            "photo": url
        }

        supabase.table("friends").insert(friend_insert).execute()
        return {"message": "Friend uploaded successfully.", "data": friend_insert}

    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed adding friend: {str(e)}")

@router.get("/friends/")
async def get_all_friends(user_id: str):
  try:
      friends = supabase.table("friends").select("*").eq("user_id", user_id).execute().data
      return {"friends": friends}
  except Exception as e:
      raise HTTPException(status_code=500, detail=f"Failed to get friends: {str(e)}")

@router.get("/receipts/")
async def get_all_receipts(user_id: str):
    try:
        receipts = supabase.table("receipts").select("*").eq("user_id", user_id).execute().data
        if not receipts:
            return {"receipts": []}

        # Get all receipt IDs
        receipt_ids = [receipt["id"] for receipt in receipts]

        friends_data = supabase.table("receipt_friends").select("receipt_id, friend_id").in_("receipt_id", receipt_ids).execute().data

        # Get all unique friend IDs
        friend_ids = list(set(friend["friend_id"] for friend in friends_data))

        friends_details = supabase.table("friends").select("id, name, photo").in_("id", friend_ids).execute().data

        # Convert friends_details into a lookup dictionary
        friends_map = {friend["id"]: friend for friend in friends_details}

        # Organize friends by receipt_id
        receipt_friends_map = {}
        for entry in friends_data:
            receipt_id = entry["receipt_id"]
            friend_id = entry["friend_id"]
            if receipt_id not in receipt_friends_map:
                receipt_friends_map[receipt_id] = []
            if friend_id in friends_map:  # Ensure the friend exists in the friends table
                receipt_friends_map[receipt_id].append(friends_map[friend_id])

        # Merge friends into receipts
        receipts = [{**receipt, "friends": receipt_friends_map.get(receipt["id"], [])} for receipt in receipts]

        return {"receipts": receipts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get receipts: {str(e)}")
    
