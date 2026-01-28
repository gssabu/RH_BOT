sudo apt update && sudo apt upgrade -y

sudo apt install python3 python3-pip git -y

git clone https://github.com/gssabu/RH-BOT.git

cd RH-BOT

python3 -m venv env

source env/bin/activate

pip install -r requirements.txt

python keygen.py
use the generated keys in .env file

python3 main.py sma-bot --symbol DOGE-USD --strategy swingT --threshold 0.0000002 --trend 10 --period 5 --notional 10 --trail 5 --no-atr --no-rsi --sell_pct 1.85 --buy_pct 0.02


TO RUN THE BOT ON a new TMUX:
tmux new -s mysession

TO attach to an existing TMUX session:
tmux a -t mysession

TO RUN BUT LIVE:
add "--live" argument when starting the bot
