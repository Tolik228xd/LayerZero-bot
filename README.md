### Follow: https://t.me/cryptofizic

# Quick Start

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Fill in `accounts.txt` with MetaMask private keys. Format: `address,privatekey`

3. To install dependencies:
```bash
pip install -r requirements.txt
```

4. To run the script:
```bash
python main.py
```

# Supported Networks:
bsc, polygon, optimism, arbitrum_one, eth, abstract, linea

# Modes:
1 – Balance check mode: checks all balances and tokens specified in `config_bridge.json`  
2 – Standard swaps: settings configured in `config_bridge.json`  
3 – Circular swaps: cycles tokens across all selected networks and gathers funds into one specified token and network

# Circular Mode
To perform circular swaps, list all networks and tokens you want to cycle in the config.  
At runtime, select the final network and token to collect the result.

# `config_bridge.json` Settings:
- `sourceNetworks`: networks to bridge from (randomized per account)
- `destinationNetworks`: networks to bridge to
- `fromTokens`: tokens to bridge (e.g., usdt, eth, usdc.e)
- `toTokens`: tokens to receive (e.g., usdt, eth, usdc.e)
- `percentageRange`: random percent of token to swap
- `transactionCount`: total transactions across all accounts
- `delayBetweenAccounts`: delay between accounts (seconds)
- `transactionDelay`: delay between transactions (seconds)
- `threads`: number of threads
- `bridgeMode`: fast/slow – use fast mode for visibility on L0 scan (percent-controlled)
- `gasPriceLimits`: gas limits per chain
- `randomBridge`: % of txs to route via alternative bridge (not Stargate)

# Withdraw to Exchange

Fill in `exchange_wallet.txt` with exchange wallet addresses (one per line)

Example config:
```json
"withdrawNetwork": "arbitrum_one",
"withdrawToken": "ETH",
"withdrawMode": "percentage",      // or "fixed"
"withdrawPercentage": [90, 100],
"withdrawAmount": 0.01
```

# Deposit from Exchange

Deposits supported from: Binance, OKX, Bybit, Gate, KuCoin, MEXC, Huobi

In `api_keys.py`, set your API keys:
```python
class API:
    binance_apikey = "your_api_key"
    binance_apisecret = "your_api_secret"
    okx_apikey = ""
    okx_apisecret = ""
    okx_passphrase = ""
```

# Deposit Config Example (`data/config_bridge.json`):
```json
{
  "depositCex": "binance",
  "depositToken": "USDT",
  "depositNetwork": "Arbitrum One",
  "depositAmountRange": [1.5, 2.5],
  "depositDecimalPlaces": 2,
  "depositDelayRange": [35, 85],
  "shuffleWallets": "no",
  "useProxy": true
}
```

# Transaction Filter (`config_filter.json`):
- `Data_from`: start date
- `Data_to`: end date

# Proxy Setup (`proxies.txt`)
Format:
```
http://login:pass@ip:port
```
Enable or disable proxy via `config_bridge.json`:  
`"useProxy": true` or `false`

---

## Virtual Environment Guide

Make sure Python is installed. Check with:
```bash
python --version
```

To create a virtual environment:
- On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

- On macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

To deactivate:
```bash
deactivate
```

---

### Donate :)
ERC-20: `0xF807A0957fe63753b0CbD4848cA3341E52094051`
