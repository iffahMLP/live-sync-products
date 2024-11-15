from flask import Flask, request, jsonify
import requests
import os
from pprint import pprint

app = Flask(__name__)

# Load store configurations from environment variables
store_configs = {
    region: {
        "SHOP_NAME": os.getenv(f"{region}_SHOP_NAME"),
        "API_KEY": os.getenv(f"{region}_API_KEY"),
        "PASSWORD": os.getenv(f"{region}_PASSWORD"),
        "API_VERSION": os.getenv(f"{region}_API_VERSION"),
    } for region in ["UK", "US", "EU", "DUCO"]
}

# Source store configuration (UK in this case)
SOURCE_STORE = store_configs["UK"]["SHOP_NAME"]
SOURCE_API_KEY = store_configs["UK"]["API_KEY"]
SOURCE_PASSWORD = store_configs["UK"]["PASSWORD"]
SOURCE_API_VERSION = store_configs["UK"]["API_VERSION"]

@app.route('/webhook/product-update', methods=['POST'])
def product_update_webhook():
    data = request.json
    product_id = data.get('id')
    print(f"Updating for product ID: {product_id}")

    if not product_id or product_id != 8098008498397:
        return jsonify({"message": "No need to update"}), 200

    metafields_data = get_product_metafields(SOURCE_STORE, SOURCE_API_KEY, SOURCE_PASSWORD, SOURCE_API_VERSION, product_id)
    if not metafields_data:
        return jsonify({"message": "No destination IDs found"}), 404

    destination_ids = metafields_data.get("destination_ids")
    shipping_label = metafields_data.get("shipping_label")

    for region, config in store_configs.items():
        if region != "UK":  # Skip source store
            dest_product_id = destination_ids.get(region)
            if dest_product_id:
                print(f"{region} product ID: {dest_product_id}")
                destination_variants = get_variants_details(config, dest_product_id)
                updated_data = prepare_update_data(region, data, destination_variants, product_id)
                update_product_in_destination(config, dest_product_id, updated_data)
                update_product_metafield(config, dest_product_id, shipping_label)

    return jsonify({"message": f"Product with ID {product_id} updates processed successfully"}), 200

def get_variants_details(config, product_id):
    """Fetch variant details for a given product from a store."""
    url = f"https://{config['API_KEY']}:{config['PASSWORD']}@{config['SHOP_NAME']}.myshopify.com/admin/api/{config['API_VERSION']}/products/{product_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get('product', {}).get('variants', [])
    else:
        print(f"Failed to fetch product variants from store: {response.text}")
        return []

def prepare_update_data(region, source_data, destination_variants, product_id):
    """Prepare data for updating destination products."""
    general_data = ['id', 'title', 'vendor', 'product_type']
    variant_fields = {
        "US": ['weight', 'weight_unit'],
        "EU": ['weight', 'weight_unit', 'status'],
        "DUCO": ['weight', 'weight_unit', 'status', 'inventory_policy']
    }
    
    product_data = general_data
    variant_data = variant_fields.get(region, [])

    updated_data = {
        "product": {key: source_data[key] for key in product_data if key in source_data}
    }

    # Update specific fields for variants based on SKU
    source_variants = get_variants_details(store_configs["UK"], product_id)
    variants_to_update = [
        {
            "id": dest_variant["id"],
            **{key: src_variant[key] for key in variant_data if key in src_variant}
        }
        for src_variant in source_variants
        for dest_variant in destination_variants
        if src_variant["sku"] == dest_variant["sku"]
    ]

    if variants_to_update:
        updated_data["product"]["variants"] = variants_to_update

    return updated_data

def get_product_metafields(store, api_key, password, api_version, product_id):
    """Fetch metafields for a given product ID in the source store."""
    url = f"https://{api_key}:{password}@{store}.myshopify.com/admin/api/{api_version}/products/{product_id}/metafields.json"
    response = requests.get(url)

    if response.status_code == 200:
        metafields = response.json().get('metafields', [])
        dest_ids = {mf['key'].split('_')[0].upper(): mf['value'] for mf in metafields if mf['namespace'] == 'custom' and mf['key'].endswith('_product_id')}
        shipping_label = next((mf['value'] for mf in metafields if mf['namespace'] == 'shipping_information' and mf['key'] == 'shipping_label'), "")
        return {"destination_ids": dest_ids, "shipping_label": shipping_label}
    else:
        print(f"Failed to fetch metafields: {response.json()}")
        return None

def update_product_metafield(config, product_id, shipping_label):
    """Update the shipping label metafield in a destination store."""
    url = f"https://{config['API_KEY']}:{config['PASSWORD']}@{config['SHOP_NAME']}.myshopify.com/admin/api/{config['API_VERSION']}/graphql.json"
    mutation = """
    mutation updateProductMetafield($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id metafields(first: 10) { edges { node { id namespace key value } } } }
        userErrors { field message }
      }
    }
    """
    product_gid = f'gid://shopify/Product/{product_id}'
    product_input = {
        "input": {
            "id": product_gid,
            "metafields": [{"namespace": "shipping_information", "key": "shipping_label", "value": shipping_label, "type": "single_line_text_field"}]
        }
    }

    response = requests.post(url, json={'query': mutation, 'variables': product_input})
    data = response.json()
    if 'errors' in data:
        print("API Error:", data['errors'])
    else:
        errors = data.get('data', {}).get('productUpdate', {}).get('userErrors', [])
        if errors:
            for error in errors:
                print("Error:", error['field'], "-", error['message'])
        else:
            metafield_node = data.get('data', {}).get('productUpdate', {}).get('product', {}).get('metafields', {}).get('edges', [])
            if metafield_node:
                updated_metafield = metafield_node[-1]['node']
                print(f"Metafield updated for {product_id}: Namespace={updated_metafield['namespace']}, Key={updated_metafield['key']}, Value={updated_metafield['value']}")

def update_product_in_destination(config, product_id, updated_data):
    """Update a product in a destination store."""
    url = f"https://{config['API_KEY']}:{config['PASSWORD']}@{config['SHOP_NAME']}.myshopify.com/admin/api/{config['API_VERSION']}/products/{product_id}.json"
    print(f"Updating product in {config['SHOP_NAME']}: {url}")
    response = requests.put(url, json=updated_data)

    if response.status_code == 200:
        print(f"Product updated successfully in store {config['SHOP_NAME']}: {product_id}")
    else:
        print(f"Failed to update product: {response.json()}")

if __name__ == '__main__':
    app.run(port=5000)
