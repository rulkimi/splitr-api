from pydantic import BaseModel
from typing import List

class Variation(BaseModel):
  name: str
  price: float

class Item(BaseModel):
  item_name: str
  quantity: int
  unit_price: float
  variation: List[Variation] = None

class Receipt(BaseModel):
  restaurant_name: str
  total_amount: float
  tax: float
  service_charge: float
  currency: str
  items: List[Item]