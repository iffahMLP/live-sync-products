import requests

url = "http://127.0.0.1:5000/webhook/product-update"  # Change to your app's URL if hosted
data = {
    "id": '8098008498397',
    "title": "Genuine BMW Mini 12527507258 E81 E92 E60 Socket Housing 3 POL. (Inc. X6 35dX)", 
    "vendor": "BMW",
    "product_type": "Engine",
    "status": "active",
    "variants": [{
        "sku": "BMW-12527507258",
        "weight": 2,
        "weight_unit": "kg",
        "inventory_policy": "continue"
    }]
    }


response = requests.post(url, json=data)

# Print status code
print("Status Code:", response.status_code)

# Try to parse the JSON response, or print text if not JSON
try:
    print("Response JSON:", response.json())
except requests.exceptions.JSONDecodeError:
    print("Response Text:", response.text)