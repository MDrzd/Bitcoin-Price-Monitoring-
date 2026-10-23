
import argparse
import csv
import os
import time
from datetime import datetime

import requests

BASE_URL = "https://data-api.binance.vision"
SYMBOL = "BTCUSDT"
CSV_FILE = "btc_history.csv"


class BTCMonitor:
    def __init__(self, interval=5, timeframe="1m",
                 target_up=None, target_down=None):
        self.interval = max(2, interval)
        self.timeframe = timeframe
        self.target_up = target_up
        self.target_down = target_down

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BTC-Monitor"
        })

        self.last_alert = {"up": False, "down": False}
        self.samples = 0
        self.session_high = 0.0
        self.session_low = float("inf")
        self.start_price = None

    def get_json(self, endpoint, params=None):
        response = self.session.get(
            f"{BASE_URL}{endpoint}",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    def get_price(self):
        data = self.get_json(
            "/api/v3/ticker/price",
            {"symbol": SYMBOL}
        )
        return float(data["price"])

    def get_candles(self):
        data = self.get_json(
            "/api/v3/klines",
            {
                "symbol": SYMBOL,
                "interval": self.timeframe,
                "limit": 100
            }
        )

        now_ms = int(time.time() * 1000)

        return [
            {
                "time": int(candle[0]),
                "close_time": int(candle[6]),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5])
            }
            for candle in data
            if int(candle[6]) < now_ms
        ]

    @staticmethod
    def calculate_ema(values, period):
        if len(values) < period:
            return None

        ema = sum(values[:period]) / period
        multiplier = 2 / (period + 1)

        for value in values[period:]:
            ema = (value - ema) * multiplier + ema

        return ema

    @staticmethod
    def calculate_rsi(values, period=14):
        if len(values) < period + 1:
            return None

        changes = [
            values[i] - values[i - 1]
            for i in range(len(values) - period, len(values))
        ]

        gains = [max(change, 0) for change in changes]
        losses = [max(-change, 0) for change in changes]

        average_gain = sum(gains) / period
        average_loss = sum(losses) / period

        if average_loss == 0:
            return 100.0 if average_gain > 0 else 50.0

        rs = average_gain / average_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def make_chart(values, width=40, height=8):
        values = values[-width:]

        if not values:
            return ["No chart data available"]

        low = min(values)
        high = max(values)
        spread = high - low or 1e-12

        rows = []

        for row in range(height - 1, -1, -1):
            threshold = low + spread * row / (height - 1)
            line = ""

            for value in values:
                level = round(
                    (value - low) / spread * (height - 1)
                )

                line += "*" if level == row else " "

            rows.append(f"{threshold:>12,.2f} |{line}")

        rows.append(" " * 14 + "-" * len(values))
        return rows

    @staticmethod
    def get_signal(ema9, ema21, rsi):
        if ema9 is None or ema21 is None or rsi is None:
            return "WAIT", "Insufficient candle data"

        if ema9 > ema21 and 50 <= rsi < 70:
            return "BUY", "Bullish EMA alignment and momentum"

        if ema9 < ema21 and 30 < rsi <= 50:
            return "SELL", "Bearish EMA alignment and momentum"

        return "HOLD", "No matching signal conditions"

    def save_csv(self, price, candles, ema9, ema21, rsi, signal):
        new_file = not os.path.exists(CSV_FILE)

        with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            if new_file:
                writer.writerow([
                    "timestamp", "symbol", "price",
                    "timeframe", "ema9", "ema21",
                    "rsi14", "signal", "candle_volume"
                ])

            writer.writerow([
                datetime.now().isoformat(timespec="seconds"),
                SYMBOL,
                price,
                self.timeframe,
                ema9,
                ema21,
                rsi,
                signal,
                candles[-1]["volume"] if candles else None
            ])

    def check_alerts(self, price):
        targets = [
            ("up", self.target_up, "UPPER"),
            ("down", self.target_down, "LOWER")
        ]

        for key, target, label in targets:
            if target is None:
                continue

            reached = (
                price >= target if key == "up"
                else price <= target
            )

            if reached and not self.last_alert[key]:
                print(
                    f"\n[PRICE ALERT] {label} target reached: "
                    f"${price:,.2f} (target: ${target:,.2f})"
                )

            self.last_alert[key] = reached

    def display(self, price, candles):
        closes = [candle["close"] for candle in candles]

        ema9 = self.calculate_ema(closes, 9)
        ema21 = self.calculate_ema(closes, 21)
        rsi = self.calculate_rsi(closes, 14)

        signal, reason = self.get_signal(ema9, ema21, rsi)

        if self.start_price is None:
            self.start_price = price

        self.session_high = max(self.session_high, price)
        self.session_low = min(self.session_low, price)
        self.samples += 1

        change = price - self.start_price
        change_pct = change / self.start_price * 100

        os.system("clear")

        print("=" * 54)
        print("               BTC MONITOR")
        print("=" * 54)
        print(f"Timestamp       : {datetime.now():%Y-%m-%d %H:%M:%S}")
        print(f"Trading Pair    : {SYMBOL}")
        print(f"Timeframe       : {self.timeframe}")
        print(f"Current Price   : ${price:,.2f}")
        print(f"Session Change  : {change:+,.2f} USD ({change_pct:+.3f}%)")
        print(f"Session High    : ${self.session_high:,.2f}")
        print(f"Session Low     : ${self.session_low:,.2f}")
        print(f"Closed Candles  : {len(candles)}")
        print("-" * 54)
        print(f"EMA 9           : ${ema9:,.2f}" if ema9 is not None else "EMA 9           : N/A")
        print(f"EMA 21          : ${ema21:,.2f}" if ema21 is not None else "EMA 21          : N/A")
        print(f"RSI 14          : {rsi:.2f}" if rsi is not None else "RSI 14          : N/A")
        print(f"Signal          : {signal}")
        print(f"Signal Reason   : {reason}")
        print("-" * 54)
        print("PRICE CHART (RECENT CLOSED CANDLES)")

        for line in self.make_chart(closes):
            print(line)

        print("=" * 54)
        print(f"Samples         : {self.samples}")
        print(f"CSV Log         : {os.path.abspath(CSV_FILE)}")
        print("Press Ctrl+C to stop.")

        self.save_csv(
            price, candles, ema9, ema21, rsi, signal
        )
        self.check_alerts(price)

    def run(self):
        print("Starting BTC Monitor...")

        try:
            while True:
                try:
                    price = self.get_price()
                    candles = self.get_candles()

                    if len(candles) < 22:
                        print("Waiting for sufficient candle data...")
                    else:
                        self.display(price, candles)

                    time.sleep(self.interval)

                except requests.HTTPError as error:
                    status = error.response.status_code

                    if status in (418, 429):
                        retry = error.response.headers.get(
                            "Retry-After", "60"
                        )
                        try:
                            wait = max(1, int(retry))
                        except ValueError:
                            wait = 60

                        print(
                            f"[API LIMIT] HTTP {status}. "
                            f"Waiting {wait} seconds."
                        )
                        time.sleep(wait)

                    else:
                        print(f"[HTTP ERROR] {error}")
                        time.sleep(5)

                except (
                    requests.RequestException,
                    ValueError,
                    KeyError,
                    IndexError
                ) as error:
                    print(f"[ERROR] {error}")
                    print("Retrying in 5 seconds...")
                    time.sleep(5)

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            print(f"Total samples: {self.samples}")
            print(f"CSV file: {os.path.abspath(CSV_FILE)}")

        finally:
            self.session.close()


def main():
    parser = argparse.ArgumentParser(
        description="BTC Monitor - Technical Analysis Dashboard"
    )

    parser.add_argument(
        "--interval", type=int, default=5,
        help="Dashboard refresh interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--timeframe", choices=["1m", "5m", "15m", "1h"],
        default="1m",
        help="Candlestick timeframe (default: 1m)"
    )
    parser.add_argument(
        "--up", type=float, default=None,
        help="Upper price alert in USD"
    )
    parser.add_argument(
        "--down", type=float, default=None,
        help="Lower price alert in USD"
    )

    args = parser.parse_args()

    if args.interval < 2:
        parser.error("--interval must be at least 2 seconds")

    if args.up is not None and args.up <= 0:
        parser.error("--up must be greater than zero")

    if args.down is not None and args.down <= 0:
        parser.error("--down must be greater than zero")

    if (
        args.up is not None
        and args.down is not None
        and args.down >= args.up
    ):
        parser.error("--down must be lower than --up")

    monitor = BTCMonitor(
        interval=args.interval,
        timeframe=args.timeframe,
        target_up=args.up,
        target_down=args.down
    )

    monitor.run()


if __name__ == "__main__":
    main()
        
