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

@router.post("/analyze_receipt/")
async def analyze(file: UploadFile, friends: List[str]):
	try:
		receipt_data = await analyze_receipt(file)

		receipt_insert = {
      "user_id": SAMPLE_UUID,
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

		return {
      "message": "Receipt and items inserted successfully.",
      "data": {
        "receipt_id": receipt_id,
        "receipt_data": receipt_data,
      }
    }

	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
     
@router.post("/friend")
async def add_friend(name: str, photo: UploadFile):
  try:
    url, error = await upload_file_to_supabase(supabase, photo, "friend-photo")
    if error:
      raise HTTPException(
        status_code=400 if "must be an image" in error else 500,
        detail=error
      )

    friend_insert = {
      "user_id": SAMPLE_UUID,
      "name": name,
      "photo": url
    }
    supabase.table("friends").insert(friend_insert).execute()
    return { "message": "Friend uploaded successfully.", "data": friend_insert}
  except HTTPException as http_error:
    raise http_error
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Failed adding friend: {str(e)}")
  