from fastapi import APIRouter, UploadFile, HTTPException, Form, File
from app.services import analyze_receipt
from db.init import create_supabase_client
from pydantic import BaseModel, RootModel
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

        receipt_insert = {
            "user_id": user_id,
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
  
        for friend in friends:
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

        receipt_ids = [receipt["id"] for receipt in receipts]

        # --- Fetch and organize receipt friends ---
        friends_data = supabase.table("receipt_friends").select("receipt_id, friend_id").in_("receipt_id", receipt_ids).execute().data
        friend_ids = list(set(friend["friend_id"] for friend in friends_data))
        friends_details = supabase.table("friends").select("id, name, photo").in_("id", friend_ids).execute().data
        friends_map = {friend["id"]: friend for friend in friends_details}

        receipt_friends_map = {}
        for entry in friends_data:
            rid = entry["receipt_id"]
            fid = entry["friend_id"]
            if rid not in receipt_friends_map:
                receipt_friends_map[rid] = []
            if fid in friends_map:
                receipt_friends_map[rid].append(friends_map[fid])

        # --- Fetch and organize receipt items ---
        items_data = supabase.table("items").select("*").in_("receipt_id", receipt_ids).execute().data
        items_map = {}
        for item in items_data:
            rid = item["receipt_id"]
            if rid not in items_map:
                items_map[rid] = []
            items_map[rid].append(item)

        # --- Fetch and organize item friends ---
        item_ids = [item["id"] for items in items_map.values() for item in items]
        friend_items_data = supabase.table("friend_items").select("item_id, friend_id, share_percentage, amount").in_("item_id", item_ids).execute().data
        
        item_friends_map = {}
        for entry in friend_items_data:
            item_id = entry["item_id"]
            friend_id = entry["friend_id"]
            if item_id not in item_friends_map:
                item_friends_map[item_id] = []
            if friend_id in friends_map:
                friend_data = {
                    **friends_map[friend_id],
                    "share_percentage": entry["share_percentage"],
                    "amount": entry["amount"]
                }
                item_friends_map[item_id].append(friend_data)

        print(item_friends_map)
        # --- Combine everything ---
        receipts = [{
            **receipt,
            "friends": receipt_friends_map.get(receipt["id"], []),
            "items": [{
                **item,
                "friends": item_friends_map.get(item["id"], [])
            } for item in items_map.get(receipt["id"], [])]
        } for receipt in receipts]

        return {"receipts": receipts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get receipts: {str(e)}")

# handle remove friend fromm the items
@router.post("/receipts/{receipt_id}/items/split")
async def split_receipt_items(receipt_id: str, items_data: List[dict]):
	try:
		print(f"Starting split for receipt_id: {receipt_id}")
		print(f"Received items_data: {items_data}")
		
		receipt = supabase.table("receipts").select("*").eq("id", receipt_id).execute().data
		print(f"Receipt query result: {receipt}")
		if not receipt:
			raise HTTPException(status_code=404, detail="Receipt not found")
        
		current_friend_items = supabase.table("friend_items").select("*").eq("receipt_id", receipt_id).execute().data
		print(f"Current friend relations: {current_friend_items}")
		
		# friend relations as (item_id, friend_id) pairs
		current_friend_relations = {
			(entry["item_id"], entry["friend_id"]) 
			for entry in current_friend_items
		}
		print(f"Current friend relations: {current_friend_relations}")
		
		# new friend relations from items_data
		new_friend_relations = {
			(item["id"], friend["id"]) 
			for item in items_data 
			for friend in item.get("friends", [])
		}
		print(f"New friend relations: {new_friend_relations}")
		
		#  riend relations that need to be removed (in current but not in new)
		friend_relations_to_remove = current_friend_relations - new_friend_relations
		print(f"Friend relations to remove: {friend_relations_to_remove}")
		
		if friend_relations_to_remove:
			print(f"Removing friend relations: {friend_relations_to_remove}")
			for item_id, friend_id in friend_relations_to_remove:
				supabase.table("friend_items").delete()\
					.eq("receipt_id", receipt_id)\
					.eq("item_id", item_id)\
					.eq("friend_id", friend_id)\
					.execute()

		for item_data in items_data:
			item_id = item_data["id"]
			friends = item_data["friends"]
			print(f"\nProcessing item_id: {item_id}")
			print(f"Friends: {friends}")
			
			# calculate amounts
			item = supabase.table("items").select("id, receipt_id, item_name, quantity, unit_price").eq("id", item_id).execute().data
			print(f"Item query result: {item}")
			if not item:
				raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
			
			item = item[0]
			total_price = float(item["unit_price"]) * int(item["quantity"])
			
			if not friends:
				continue
				
			num_friends = len(friends)
			share_percentage = 100 / num_friends
			amount_per_friend = total_price / num_friends
			
			print(f"Total Price: {total_price}, Share %: {share_percentage}, Amount per friend: {amount_per_friend}")

			# friend_item entries for each friend
			for friend in friends:
				# if friend_item entry already exists
				existing_entry = supabase.table("friend_items").select("*").eq("item_id", item_id).eq("friend_id", friend["id"]).execute().data
				
				if not existing_entry:
					friend_item = {
						"receipt_id": receipt_id,
						"friend_id": friend["id"],
						"item_id": item_id,
						"share_percentage": share_percentage,
						"amount": amount_per_friend
					}
					print(f"Creating friend_item entry: {friend_item}")
					result = supabase.table("friend_items").insert(friend_item).execute()
					print(f"Insert result: {result}")
				else:
					print(f"Friend item entry already exists for friend {friend['id']} and item {item_id}")

		friend_items = supabase.table("friend_items").select("*").eq("receipt_id", receipt_id).execute().data
		
		friend_summary = {}
		for fi in friend_items:
			friend_id = fi["friend_id"]
			if friend_id not in friend_summary:
				friend_summary[friend_id] = {
					"total_amount": 0,
					"items": []
				}
			
			item = supabase.table("items").select("*").eq("id", fi["item_id"]).execute().data[0]
			
			# tax for this item's share
			item_tax = (float(item["unit_price"]) * int(item["quantity"]) * (fi["share_percentage"] / 100)) * (receipt[0]["tax"] / 100)
			
			item_service_charge = 0
			if receipt[0].get("service_charge"):
				item_service_charge = (float(item["unit_price"]) * int(item["quantity"]) * (fi["share_percentage"] / 100)) * (receipt[0]["service_charge"] / 100)
			
			friend_summary[friend_id]["total_amount"] += fi["amount"] + item_tax + item_service_charge
			friend_summary[friend_id]["items"].append({
				"item_name": item["item_name"],
				"quantity": item["quantity"],
				"share_percentage": fi["share_percentage"],
				"amount": fi["amount"],
				"tax": item_tax,
				"service_charge": item_service_charge
			})
		
		for friend_id in friend_summary:
			friend = supabase.table("friends").select("name").eq("id", friend_id).execute().data[0]
			friend_summary[friend_id]["name"] = friend["name"]
			
			print(f"\nSummary for {friend['name']}:")
			print(f"Total Amount: ${friend_summary[friend_id]['total_amount']:.2f}")
			print("Items:")
			for item in friend_summary[friend_id]["items"]:
				print(f"- {item['item_name']} (Qty: {item['quantity']}, Share: {item['share_percentage']}%)")
				print(f"  Amount: ${item['amount']:.2f}, Tax: ${item['tax']:.2f}")
		
		return {
			"message": "Items split successfully",
			"summary": friend_summary
		}

	except Exception as e:
		print(f"Error occurred: {str(e)}")
		raise HTTPException(status_code=500, detail=f"Failed to split items: {str(e)}")
