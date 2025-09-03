# strategy.py
from collections import deque

class SMAStrategy:
    def __init__(self, short=5, long=20):
        if short >= long:
            raise ValueError("short must be < long")
        self.s = deque(maxlen=short)
        self.l = deque(maxlen=long)

    def update(self, price: float):
        self.s.append(price)
        self.l.append(price)
        if len(self.l) < self.l.maxlen:
            return None
        sp = sum(self.s) / len(self.s)
        lp = sum(self.l) / len(self.l)
        if sp > lp:
            return "bull"
        if sp < lp:
            return "bear"
        return None


class PriceMoveStrategy:
    def __init__(self, threshold=0.01):
        self.threshold = threshold
        self.last_price = None

    def update(self, price: float):
        if self.last_price is None:
            self.last_price = price
            return None
        change = price - self.last_price
        if abs(change) >= self.threshold:
            signal = "buy" if change > 0 else "sell"
            self.last_price = price
            return signal
        return None

class SwingStrategy:
    """
    Buys after a drop of >= threshold from the last high.
    Sells after a rise of >= threshold from the last low.
    """

    def __init__(self, threshold=0.001):
        self.threshold = threshold
        self.last_high = None
        self.last_low = None
        self.position = 0  # 0=flat, 1=long

    def update(self, price: float):
        # Initialize anchors
        if self.last_high is None:
            self.last_high = price
        if self.last_low is None:
            self.last_low = price

        signal = None

        if self.position == 0:
            # looking for entry: buy when price falls from high
            if self.last_high - price >= self.threshold:
                signal = "buy"
                self.position = 1
                self.last_low = price   # reset low after buying
        elif self.position == 1:
            # looking for exit: sell when price rises from low
            if price - self.last_low >= self.threshold:
                signal = "sell"
                self.position = 0
                self.last_high = price  # reset high after selling

        # Update anchors
        if price > self.last_high:
            self.last_high = price
        if price < self.last_low:
            self.last_low = price

        return signal
        
class SwingWithTrend:
    def __init__(self, buy_pct=0.5, sell_pct=0.5, trend_window=50,
                 atr_window=14, atr_mult=1.0, rsi_window=14,
                 max_buy_price=None, min_sell_price=None):
        # thresholds now as percent
        self.buy_pct = buy_pct / 100.0
        self.sell_pct = sell_pct / 100.0

        self.last_high = None
        self.last_low = None
        self.position = 0

        self.trend_prices = []
        self.trend_window = trend_window
        self.prev_price = None

        self.atr = ATR(window=atr_window)
        self.atr_mult = atr_mult
        self.rsi = RSI(window=rsi_window)

        # hard price limits (coin-specific, loaded at startup)
        self.max_buy_price = max_buy_price
        self.min_sell_price = min_sell_price

    def update(self, price: float):
        # update trend SMA
        self.trend_prices.append(price)
        if len(self.trend_prices) > self.trend_window:
            self.trend_prices.pop(0)
        sma = sum(self.trend_prices) / len(self.trend_prices)

        # update ATR
        atr_val = self.atr.update(price, self.prev_price)
        self.prev_price = price

        # initialize anchors
        if self.last_high is None: self.last_high = price
        if self.last_low is None: self.last_low = price

        signal = None
        rsi_val = self.rsi.update(price)

        # compute volatility-adjusted thresholds
        base_buy  = self.last_high * self.buy_pct
        base_sell = self.last_low  * self.sell_pct

        if atr_val:
            vol_factor = atr_val / price
            dip_needed  = base_buy  * (1 + self.atr_mult * vol_factor)
            rise_needed = base_sell * (1 + self.atr_mult * vol_factor)
        else:
            dip_needed, rise_needed = base_buy, base_sell

        if self.position == 0:
            # Buy: dipped enough, above SMA, RSI oversold, under hard limit
            if (self.last_high - price >= dip_needed and price > sma and
                (rsi_val is None or rsi_val < 50)):
                if self.max_buy_price is None or price <= self.max_buy_price:
                    signal = "buy"
                    self.position = 1
                    self.last_low = price

        elif self.position == 1:
            # Sell: rose enough, below SMA, RSI overbought, above hard limit
            if (price - self.last_low >= rise_needed and price < sma and
                (rsi_val is None or rsi_val > 50)):
                if self.min_sell_price is None or price >= self.min_sell_price:
                    signal = "sell"
                    self.position = 0
                    self.last_high = price

        # update anchors
        if price > self.last_high: self.last_high = price
        if price < self.last_low: self.last_low = price

        return signal


class ATR:
    def __init__(self, window=0.14):
        self.window = window
        self.tr = []

    def update(self, price, prev_price):
        if prev_price is None:
            return None
        tr = abs(price - prev_price)
        self.tr.append(tr)
        if len(self.tr) > self.window:
            self.tr.pop(0)
        return sum(self.tr) / len(self.tr) if self.tr else None
        
class RSI:
    def __init__(self, window=0.14):
        self.window = window
        self.gains = []
        self.losses = []
        self.prev_price = None

    def update(self, price):
        if self.prev_price is None:
            self.prev_price = price
            return None
        delta = price - self.prev_price
        self.prev_price = price
        self.gains.append(max(delta, 0))
        self.losses.append(abs(min(delta, 0)))
        if len(self.gains) > self.window:
            self.gains.pop(0)
            self.losses.pop(0)
        if len(self.gains) < self.window:
            return None
        avg_gain = sum(self.gains) / self.window
        avg_loss = sum(self.losses) / self.window
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

