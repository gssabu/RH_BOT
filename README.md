sudo apt update && sudo apt upgrade -y

sudo apt install python3 python3-pip git -y

git clone https://github.com/gssabu/RH-BOT.git

cd RH-BOT

python3 -m venv env

source env/bin/activate

pip install -r requirements.txt

python main.py sma-bot --symbol DOGE-USD --strategy swingT --threshold 0.0001 --trend 10 --period 10 --notional 9000 --no-atr --no-rsi


TO RUN THE BOT ON a new TMUX:
tmux new -s mysession

TO attach to an existing TMUX session:
tmux a -t mysession
