import requests

token = "8465760307:AAGkPIDf0bFmzpL3GSt9DBcwZOhYzmrR8jA"

# 1. Verify Token
url_me = f"https://api.telegram.org/bot{token}/getMe"
try:
    print(f"Checking Token...")
    response = requests.get(url_me, timeout=10)
    print(f"getMe Status: {response.status_code}")
    print(f"getMe Response: {response.text}")
    
    if response.status_code == 200:
        bot_info = response.json()
        bot_username = bot_info['result']['username']
        print(f"\n✅ Token is VALID. Bot Username: @{bot_username}")
        print(f"Please make sure to send /start to @{bot_username} from your account.")
    else:
        print("\n❌ Token seems INVALID.")
except Exception as e:
    print(f"Error checking token: {e}")
