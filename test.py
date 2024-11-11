from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

# Load store configurations
store_configs = {
    "UK": {
        "SHOP_NAME": os.getenv("UK_SHOP_NAME"),
        "API_KEY": os.getenv("UK_API_KEY"),
        "PASSWORD": os.getenv("UK_PASSWORD"),
        "API_VERSION": os.getenv("UK_API_VERSION")
    },
    "US": {
        "SHOP_NAME": os.getenv("US_SHOP_NAME"),
        "API_KEY": os.getenv("US_API_KEY"),
        "PASSWORD": os.getenv("US_PASSWORD"),
        "API_VERSION": os.getenv("US_API_VERSION")
    },
    "EU": {
        "SHOP_NAME": os.getenv("EU_SHOP_NAME"),
        "API_KEY": os.getenv("EU_API_KEY"),
        "PASSWORD": os.getenv("EU_PASSWORD"),
        "API_VERSION": os.getenv("EU_API_VERSION")
    },
    "DUCO": {
        "SHOP_NAME": os.getenv("DUCO_SHOP_NAME"),
        "API_KEY": os.getenv("DUCO_API_KEY"),
        "PASSWORD": os.getenv("DUCO_PASSWORD"),
        "API_VERSION": os.getenv("DUCO_API_VERSION")
    }
}

SOURCE_STORE = store_configs["UK"]["SHOP_NAME"]
SOURCE_API_KEY = store_configs["UK"]["API_KEY"]
SOURCE_PASSWORD = store_configs["UK"]["PASSWORD"]
SOURCE_API_VERSION = store_configs["UK"]["API_VERSION"]

@app.route('/webhook/product-update', methods=['POST'])
def product_update_webhook():
    data = request.json
    product_id = data['id']  # Shopify ID of the updated product\

    if product_id == '8098008498397':

        # Step 1: Get destination product IDs from metafields
        metafields = get_product_metafields(SOURCE_STORE, SOURCE_API_KEY, SOURCE_PASSWORD, SOURCE_API_VERSION, product_id)
        if not metafields:
            return jsonify({"message": "No destination IDs found"}), 404


        def get_variants_from_destination(store, api_key, password, api_version, product_id):
            shop_url = f"https://{api_key}:{password}@{store}.myshopify.com/admin/api/{api_version}"
            url = f"{shop_url}/products/{product_id}.json"
            response = requests.get(url)

            if response.status_code == 200:
                product_data = response.json().get('product', {})
                return product_data.get('variants', [])
            else:
                print(f"Failed to fetch product variants from destination store: {response.text}")
                return []

        # Step 2: Prepare the data for updating destination store products
        def get_data_to_update(store, destination_variants):
            general_data = ['id', 'title', 'vendor', 'product_type']
            general_variant_data = ['weight', 'weight_unit']

            match store:
                case "US":
                    product_data = general_data
                    variant_data = general_variant_data
                case "EU":
                    product_data = general_data + ['status']
                    variant_data = general_variant_data
                case "DUCO":
                    product_data = general_data + ['status']
                    variant_data = general_variant_data + ['inventory_policy']

            updated_data = {
                    "product": {key: data[key] for key in product_data}
                }

            # Update specific fields for variants based on SKU
            if "variants" in data:
                variants_to_update = []
                for src_variant in data["variants"]:
                    print(src_variant)
                    for dest_variant in destination_variants:
                        print(dest_variant)
                        if src_variant["sku"] == dest_variant["sku"]:
                            updated_variant = {
                                "id": dest_variant["id"],  # Use destination variant ID for the update
                                **{key: src_variant[key] for key in variant_data}
                            }
                            variants_to_update.append(updated_variant)

                if variants_to_update:
                    updated_data["product"]["variants"] = variants_to_update
            
            return updated_data
                
        # Step 3: Update products in the destination stores
        for region, config in store_configs.items():
            if region != 'UK':  # Skip the source store
                destination_store = config['SHOP_NAME']
                destination_api_key = config['API_KEY']
                destination_password = config['PASSWORD']
                destination_api_version = config['API_VERSION']
                dest_product_id = metafields.get(region)  # Retrieve the destination product ID

                if dest_product_id:
                    destination_variants = get_variants_from_destination(destination_store, destination_api_key, destination_password, destination_api_version, dest_product_id)
                    updated_data = get_data_to_update(region, destination_variants)
                    update_product_in_destination(destination_store, destination_api_key, destination_password, destination_api_version, dest_product_id, updated_data)

        return jsonify({"message": f"Product with id {product_id} updates processed successfully"}), 200
    else:
        return jsonify({"message": f"No need to update"}), 200

    

def get_product_metafields(store, api_key, password, api_version, product_id):
    shop_url = "https://%s:%s@%s.myshopify.com/admin/api/%s" % (api_key, password, store, api_version)
    url = f"{shop_url}/products/{product_id}/metafields.json"
    response = requests.get(url)

    if response.status_code == 200:
        metafields = response.json().get('metafields', [])
        
        # Extract destination IDs using split to get the region key
        dest_ids = {
            mf['key'].split('_')[0].upper(): mf['value']
            for mf in metafields
            if mf['namespace'] == 'custom' and mf['key'].endswith('_product_id')
        }
        return dest_ids
    else:
        print(f"Failed to fetch metafields: {response.json()}")
        return None


def update_product_in_destination(store, api_key, password, api_version, product_id, updated_data):
    shop_url = "https://%s:%s@%s.myshopify.com/admin/api/%s" % (api_key, password, store, api_version)
    url = f"{shop_url}/products/{product_id}.json"
    response = requests.put(url, json=updated_data)

    if response.status_code == 200:
        print(f"Product updated successfully in destination store {store}: {product_id}")
    else:
        print(f"Failed to update product: {response.json()}")


if __name__ == '__main__':
    app.run(port=5000)
