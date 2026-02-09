import requests

token = "8465760307:AAGkPIDf0bFmzpL3GSt9DBcwZOhYzmrR8jA"
chat_id = "5154061728"
message = "Test from script"

url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {
    'chat_id': chat_id,
    'text': message
}

try:
    print(f"Sending request to {url}...")
    response = requests.post(url, json=payload, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
