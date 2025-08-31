import csv, time

class PaperAccount:
    def __init__(self, usd_start=100.0, fee_rate=0.0085, slippage=0.001):
        self.usd = usd_start
        self.asset = 0.0
        self.entry = None
        self.history = []
        self.fee_rate = fee_rate
        self.slippage = slippage

    def buy(self, qty, price, symbol):
        # apply slippage: assume fill slightly higher
        fill_price = price * (1 + self.slippage)
        cost = qty * fill_price
        fee = cost * self.fee_rate
        total_cost = cost + fee

        if self.usd >= total_cost:
            self.usd -= total_cost
            self.asset += qty
            self.entry = fill_price
            self.history.append((time.time(), "BUY", symbol, qty, fill_price, self.usd, self.asset, -fee))
            return True
        return False

    def sell(self, qty, price, symbol):
        if self.asset >= qty:
            # apply slippage: assume fill slightly lower
            fill_price = price * (1 - self.slippage)
            proceeds = qty * fill_price
            fee = proceeds * self.fee_rate
            net_proceeds = proceeds - fee

            self.asset -= qty
            self.usd += net_proceeds
            self.entry = None if self.asset == 0 else self.entry
            self.history.append((time.time(), "SELL", symbol, qty, fill_price, self.usd, self.asset, -fee))
            return True
        return False


    def export_csv(self, filename="paper_trades.csv"):
        import csv
        wins, losses, total_pnl = 0, 0, 0.0
        with open(filename, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "action", "symbol", "qty", "price", "usd_balance", "asset_balance", "fee"])
            for t, act, sym, qty, price, usd, asset, fee in self.history:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
                w.writerow([ts, act, sym, qty, price, usd, asset, fee])
        # compute PnL summary
        if self.history:
            start_usd = self.history[0][5]  # first USD balance
            end_usd = self.usd
            total_pnl = end_usd - start_usd
            trades = [h for h in self.history if h[1] == "SELL"]
            for h in trades:
                # crude: if usd balance grew since last sell, call it a win
                wins += 1 if h[5] > start_usd else 0
                losses += 1 if h[5] <= start_usd else 0
            win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
            print(f"\nSummary: {len(trades)} completed trades")
            print(f"Net PnL: {total_pnl:.2f} USD")
            print(f"Win rate: {win_rate:.1f}%")
        print(f"Trade history saved to {filename}")
        return filename
        
    def summary(self, price):
        return {
            "usd": round(self.usd, 2),
            "asset": round(self.asset, 6),
            "equity": round(self.usd + self.asset * price, 2),
            "entry": round(self.entry, 6) if self.entry is not None else None,
        }


