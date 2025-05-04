from fastapi import APIRouter, UploadFile, HTTPException, Form, File
from app.services import analyze_receipt
from db.init import supabase
from pydantic import BaseModel
from typing import List
from app.services import (
    upload_file_to_supabase,
    get_current_friend_relations,
    generate_friend_summary,
    get_receipt_or_404,
    extract_new_friend_relations,
    remove_old_friend_relations,
    process_friend_items,
    insert_items,
    insert_receipt,
    insert_receipt_friends,
    get_receipt_friends,
    get_receipts_by_user,
    get_item_friends,
    get_receipt_items,
    combine_receipt_data,
)

router = APIRouter()
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

@router.post("/logout/")
async def logout():
    try:
        auth_response = supabase.auth.sign_out()
        return {"message": "Logout successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")

@router.post("/analyze_receipt/")
async def analyze(user_id: str, friends: List[str], file: UploadFile):
    print(f"Received user_id: {user_id}")
    print(f"Received friends: {friends}")
    print(f"Received file: {file.filename}, Content-Type: {file.content_type}")
    try:
        receipt_data = await analyze_receipt(file)
        receipt_id = insert_receipt(user_id, receipt_data)
        insert_items(receipt_id, receipt_data["items"])
        insert_receipt_friends(receipt_id, friends)

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
async def add_friend(
    user_id: str = Form(...),
    name: str = Form(...),
    photo: UploadFile = File(None)
):
    try:
        url = None
        if photo:
            url, error = await upload_file_to_supabase(photo, "friend-photo")
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
        receipts = get_receipts_by_user(user_id)
        if not receipts:
            return {"receipts": []}

        receipt_ids = [r["id"] for r in receipts]
        friends_map, receipt_friends_map = get_receipt_friends(receipt_ids)
        items_map = get_receipt_items(receipt_ids)
        item_friends_map = get_item_friends(items_map, friends_map)

        receipts = combine_receipt_data(receipts, receipt_friends_map, items_map, item_friends_map)
        return {"receipts": receipts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get receipts: {str(e)}")

@router.post("/receipts/{receipt_id}/items/split")
async def split_receipt_items(receipt_id: str, items_data: List[dict]):
    try:
        receipt = get_receipt_or_404(receipt_id)

        current_relations = get_current_friend_relations(receipt_id)
        new_relations = extract_new_friend_relations(items_data)

        to_remove = current_relations - new_relations
        remove_old_friend_relations(receipt_id, to_remove)

        process_friend_items(receipt_id, items_data)
        summary = generate_friend_summary(receipt_id, receipt)

        return {
            "message": "Items split successfully",
            "summary": summary
        }

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to split items: {str(e)}")
