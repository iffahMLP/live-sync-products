from flask import Flask, request, jsonify
import requests
import json
import os
from pprint import pprint

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
    print(f'Updating for {product_id}')
    if product_id == "--":

        # Step 1: Get destination product IDs from metafields
        metafields_data = get_product_metafields(SOURCE_STORE, SOURCE_API_KEY, SOURCE_PASSWORD, SOURCE_API_VERSION, product_id)

        if metafields_data:
            destination_ids = metafields_data.get("destination_ids")
            shipping_label = metafields_data.get("shipping_label")
        else:
            return jsonify({"message": "No destination IDs found"}), 404


        def get_variants_details(store, api_key, password, api_version, product_id):
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
                source_variants = get_variants_details(SOURCE_STORE, SOURCE_API_KEY, SOURCE_PASSWORD, SOURCE_API_VERSION, product_id)
                for src_variant in source_variants:
                    for dest_variant in destination_variants:
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
                dest_product_id = destination_ids.get(region)  # Retrieve the destination product ID
                print(f'{region} product id: {dest_product_id}')
                if dest_product_id:
                    destination_variants = get_variants_details(destination_store, destination_api_key, destination_password, destination_api_version, dest_product_id)
                    updated_data = get_data_to_update(region, destination_variants)
                    update_product_in_destination(destination_store, destination_api_key, destination_password, destination_api_version, dest_product_id, updated_data)
                    update_product_metafield(destination_store, destination_api_key, destination_password, destination_api_version, dest_product_id, shipping_label)


        return jsonify({"message": f"Product with id {product_id} updates processed successfully"}), 200
    else:
        return jsonify({"message": f"No need to update"}), 200
    

def get_product_metafields(store, api_key, password, api_version, product_id):
    shop_url = f"https://{api_key}:{password}@{store}.myshopify.com/admin/api/{api_version}"
    url = f"{shop_url}/products/{product_id}/metafields.json"
    response = requests.get(url)

    if response.status_code == 200:
        metafields = response.json().get('metafields', [])
        
        # Extract specific metafields
        dest_ids = {
            mf['key'].split('_')[0].upper(): mf['value']
            for mf in metafields
            if mf['namespace'] == 'custom' and mf['key'].endswith('_product_id')
        }

        # Look for the shipping_label metafield
        shipping_label = None
        for mf in metafields:
            if mf['namespace'] == 'shipping_information' and mf['key'] == 'shipping_label':
                shipping_label = mf['value']
                break  # Stop once the desired metafield is found
        
        if shipping_label == None:
            shipping_label = ""
        # shipping_metafield = json.dumps({
        #     "metafield": {
        #         "namespace": "shipping_information",
        #         "key": "shipping_label",
        #         "value": shipping_label,  # Replace with actual value
        #         "type": "single_line_text_field"
        #     }
        # })
        # print(shipping_metafield)
        # Return both destination IDs and shipping_label
        return {
            "destination_ids": dest_ids,
            "shipping_label": shipping_label
        }
    else:
        print(f"Failed to fetch metafields: {response.json()}")
        return None


# def update_product_metafield(store, api_key, password, api_version, product_id, metafield_data):
#     shop_url = f"https://{api_key}:{password}@{store}.myshopify.com/admin/api/{api_version}"
#     url = f"{shop_url}/products/{product_id}/metafields.json"

#     response = requests.post(url, json=metafield_data)
#     if response.status_code == 201:  # Status code 201 indicates successful creation
#         print(f"Metafield 'shipping_label' updated successfully for product {product_id}")
#     else:
#         print(f"Failed to update metafield: {response.status_code}, {response.text}")

def update_product_metafield(store, api_key, password, api_version, product_id, shipping_label):
    shop_url = f"https://{api_key}:{password}@{store}.myshopify.com/admin/api/{api_version}"
    url = f"{shop_url}/graphql.json"
    # Construct the GraphQL mutation for updating the product metafield
    mutation = """
    mutation updateProductMetafield($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          metafields(first: 10) {
            edges {
              node {
                id
                namespace
                key
                value
              }
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    product_gid = f'gid://shopify/Product/{product_id}'
    # Define the input variables for the mutation
    product_input = {
        "input": {
            "id": product_gid,
            "metafields": [
                {
                    "namespace": "shipping_information",
                    "key": "shipping_label",
                    "value": shipping_label,
                    "type": "single_line_text_field"  # Adjust type if necessary
                }
            ]
        }
    }
    # print(product_input)
    # Send the request
    response = requests.post(url, json={'query': mutation, 'variables': product_input})

    # Parse and check for errors in the response
    data = response.json()
    if 'errors' in data:
        print("API Error:", data['errors'])
    else:
        result = data.get('data', {}).get('productUpdate', {})
        if result.get('userErrors'):
            for error in result['userErrors']:
                print("Error:", error['field'], "-", error['message'])
        else:
            metafields = result.get('product', {}).get('metafields', {}).get('edges', [])
            if metafields:
                updated_metafield = metafields[-1]['node']
                # print(metafields)
                print(f"Metafield updated for {product_id}: Namespace={updated_metafield['namespace']}, Key={updated_metafield['key']}, Value={updated_metafield['value']}")


def update_product_in_destination(store, api_key, password, api_version, product_id, updated_data):
    shop_url = "https://%s:%s@%s.myshopify.com/admin/api/%s" % (api_key, password, store, api_version)
    url = f"{shop_url}/products/{product_id}.json"
    print(f'Updating in {store}: {url}')
    response = requests.put(url, json=updated_data)

    if response.status_code == 200:
        print(f"Product updated successfully in destination store {store}: {product_id}")
    else:
        print(f"Failed to update product: {response.json()}")


if __name__ == '__main__':
    app.run(port=5000)
