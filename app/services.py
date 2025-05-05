from PIL import Image
import io
import json
from fastapi import UploadFile
from app.ai_model import get_ai_response
from app.prompt import create_analysis_prompt
from app.schemas import Receipt
import uuid
from fastapi import UploadFile
from app.config import SAMPLE_UUID
from db.init import supabase
from fastapi import APIRouter, UploadFile, HTTPException, Form, File
from typing import List

async def analyze_receipt(file: UploadFile):
  image_data = await file.read()
  image = Image.open(io.BytesIO(image_data))

  prompt = create_analysis_prompt()
  response = get_ai_response(contents=[prompt, image], response_schema=Receipt)
  return json.loads(response)

async def upload_file_to_supabase(file: UploadFile, bucket_name: str):
  try:
    if not file.content_type.startswith('image/'):
      return None, "File must be an image"
    
    file_content = await file.read()
    unique_filename = f"{SAMPLE_UUID}/{uuid.uuid4()}-{file.filename}"

    response = supabase.storage.from_(bucket_name).upload(unique_filename, file_content)
    
    if response:
      url = supabase.storage.from_(bucket_name).get_public_url(unique_filename)
      return url, None
    return None, "Failed to upload file to Supabase storage"
  except Exception as e:
      return None, str(e)

def get_receipts_by_user(user_id: str) -> list:
    return supabase.table("receipts").select("*").eq("user_id", user_id).execute().data


def get_receipt_friends(receipt_ids: list[str]) -> tuple[dict, dict]:
    friends_data = supabase.table("receipt_friends") \
        .select("receipt_id, friend_id").in_("receipt_id", receipt_ids).execute().data

    friend_ids = list(set(f["friend_id"] for f in friends_data))
    friends_details = supabase.table("friends") \
        .select("id, name, photo").in_("id", friend_ids).execute().data
    friends_map = {f["id"]: f for f in friends_details}

    receipt_friends_map = {}
    for entry in friends_data:
        rid = entry["receipt_id"]
        fid = entry["friend_id"]
        if rid not in receipt_friends_map:
            receipt_friends_map[rid] = []
        if fid in friends_map:
            receipt_friends_map[rid].append(friends_map[fid])
    
    return friends_map, receipt_friends_map


def get_receipt_items(receipt_ids: list[str]) -> dict:
    items_data = supabase.table("items").select("*").in_("receipt_id", receipt_ids).execute().data
    items_map = {}
    for item in items_data:
        rid = item["receipt_id"]
        items_map.setdefault(rid, []).append(item)
    return items_map


def get_item_friends(items_map: dict, friends_map: dict) -> dict:
    item_ids = [item["id"] for items in items_map.values() for item in items]
    friend_items_data = supabase.table("friend_items") \
        .select("item_id, friend_id, share_percentage, amount").in_("item_id", item_ids).execute().data

    item_friends_map = {}
    for entry in friend_items_data:
        item_id = entry["item_id"]
        fid = entry["friend_id"]
        if fid in friends_map:
            friend_data = {
                **friends_map[fid],
                "share_percentage": entry["share_percentage"],
                "amount": entry["amount"]
            }
            item_friends_map.setdefault(item_id, []).append(friend_data)
    return item_friends_map


def combine_receipt_data(receipts, receipt_friends_map, items_map, item_friends_map):
    return [{
        **receipt,
        "friends": receipt_friends_map.get(receipt["id"], []),
        "items": [{
            **item,
            "friends": item_friends_map.get(item["id"], [])
        } for item in items_map.get(receipt["id"], [])]
    } for receipt in receipts]

def insert_receipt(user_id: str, receipt_data: dict) -> str:
    receipt_insert = {
        "user_id": user_id,
        "restaurant_name": receipt_data["restaurant_name"],
        "total_amount": receipt_data["total_amount"],
        "tax": receipt_data["tax"],
        "service_charge": receipt_data["service_charge"],
        "currency": receipt_data["currency"]
    }

    response = supabase.table("receipts").insert(receipt_insert).execute()
    print(response)
    if not response.data:
        raise Exception("Failed to insert receipt.")

    return response.data[0]["id"]


def insert_items(receipt_id: str, items: List[dict]):
    for item in items:
        item_insert = {
            "receipt_id": receipt_id,
            "item_name": item["item_name"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "variation": item.get("variation", [])
        }
        supabase.table("items").insert(item_insert).execute()


def insert_receipt_friends(receipt_id: str, friends: List[str]):
    for friend_id in friends:
        entry = {
            "receipt_id": receipt_id,
            "friend_id": friend_id,
            "amount_paid": 0
        }
        supabase.table("receipt_friends").insert(entry).execute()

  
def get_receipt_or_404(receipt_id):
    receipt = supabase.table("receipts").select("*").eq("id", receipt_id).execute().data
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt[0]

def get_current_friend_relations(receipt_id):
    current_friend_items = supabase.table("friend_items").select("*").eq("receipt_id", receipt_id).execute().data
    return {
        (entry["item_id"], entry["friend_id"]) for entry in current_friend_items
    }

def extract_new_friend_relations(items_data):
    return {
        (item["id"], friend["id"]) 
        for item in items_data 
        for friend in item.get("friends", [])
    }

def remove_old_friend_relations(receipt_id, to_remove):
    for item_id, friend_id in to_remove:
        supabase.table("friend_items").delete()\
            .eq("receipt_id", receipt_id)\
            .eq("item_id", item_id)\
            .eq("friend_id", friend_id)\
            .execute()

def process_friend_items(receipt_id, items_data):
    for item_data in items_data:
        item_id = item_data["id"]
        friends = item_data.get("friends", [])
        if not friends:
            continue
        
        item = supabase.table("items").select("id, quantity, unit_price").eq("id", item_id).execute().data
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
        item = item[0]

        total_price = float(item["unit_price"]) * int(item["quantity"])
        num_friends = len(friends)
        share_percentage = 100 / num_friends
        amount_per_friend = total_price / num_friends

        for friend in friends:
            exists = supabase.table("friend_items").select("*")\
                .eq("item_id", item_id)\
                .eq("friend_id", friend["id"])\
                .execute().data
            if not exists:
                supabase.table("friend_items").insert({
                    "receipt_id": receipt_id,
                    "friend_id": friend["id"],
                    "item_id": item_id,
                    "share_percentage": share_percentage,
                    "amount": amount_per_friend
                }).execute()

def generate_friend_summary(receipt_id, receipt):
    friend_items = supabase.table("friend_items").select("*").eq("receipt_id", receipt_id).execute().data
    summary = {}
    
    friend_ids = set(fi["friend_id"] for fi in friend_items)
    num_friends = len(friend_ids)
    service_charge = receipt.get("service_charge", 0) / num_friends

    for fi in friend_items:
        fid = fi["friend_id"]
        if fid not in summary:
            summary[fid] = {"total_amount": 0, "service_charge": 0, "items": []}
        
        item = supabase.table("items").select("*").eq("id", fi["item_id"]).execute().data[0]
        base = float(item["unit_price"]) * int(item["quantity"])
        share = fi["share_percentage"] / 100

        tax = base * share * (receipt["tax"] / 100)

        summary[fid]["total_amount"] += fi["amount"] + tax + service_charge
        summary[fid]["items"].append({
            "item_name": item["item_name"],
            "quantity": item["quantity"],
            "share_percentage": fi["share_percentage"],
            "amount": fi["amount"],
            "tax": tax,
        })
    
    for fid in summary:
        friend = supabase.table("friends").select("name, photo").eq("id", fid).execute().data[0]
        summary[fid]["name"] = friend["name"]
        summary[fid]["photo"] = friend["photo"]
        summary[fid]["service_charge"] = service_charge
    
    print(json.dumps(summary))
    return summary
