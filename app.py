import requests
import time
import sys

def get_btc_price():
    url = 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'
    response = requests.get(url)
    data = response.json()
    return float(data['price'])

try:
    while True:
        price = get_btc_price()
        sys.stdout.write(f"\rHarga BTC/USDT: ${price:.2f}   ")
        sys.stdout.flush()
        time.sleep(1)
except KeyboardInterrupt:
    print("\nMonitoring dihentikan.")
