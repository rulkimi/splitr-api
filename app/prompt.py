def create_analysis_prompt() -> str:
	base_prompt = """
	Analyze the receipt with particular attention to indented modifications and their charges.
	Extract in this exact JSON format given from response schema:
	"""

	item_detection_rules = """
	
	CRITICAL ITEM DETECTION RULES:
	1. Main Item Format:
	   - Lines starting with "1x *" are main items
	   - Extract their base price from the "U.P" column
		 - Tax and service charges are 2 different prices, do not duplicate them into the same amount.
	
	2. Modification Format:
	   - Lines starting with "-" or indented under main items are modifications
	   - Look for additional prices on the same line as modifications
	   - Modifications may have their own price line below them
	   - Common formats:
	     * "- Cold"          # Look for price on next line
	     * "- Cold (Jumbo)"  # Look for price on same or next line
	     * "- thin"          # May have price of 0.00
	
	3. Price Association:
	   - ANY price appearing below a main item should be considered
	   - Check both "U.P" and "Price" columns for modification costs
	   - Include modifications even if price is 0.00
	
	4. Special Cases:
	   - For beverages, look specifically for:
	     * Temperature modifiers (Hot/Cold)
	     * Size modifiers (Regular/Large/Jumbo)
	   - For food items, look for:
	     * Preparation modifiers (thin, crispy, etc.)
	     * Add-ons or extras
	"""

	return base_prompt + item_detection_rules