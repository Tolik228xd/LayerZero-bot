# deposit_from_exchange.py
import asyncio
import logging
import csv
import random
from datetime import datetime
import ccxt.async_support as ccxt
from data.api_keys import API
from utils.proxy_utils import get_proxy_dict

logger = logging.getLogger(__name__)

async def deposit_from_exchange(accounts, config_json, stats, successful_transactions, failed_transactions):
    logger.info("Запуск вывода с биржи на кошельки...")

    cex_name = config_json.get("depositCex", "binance").lower()
    symbol_withdraw = config_json.get("depositToken", "USDT")
    network = config_json.get("depositNetwork", "Arbitrum One")
    amount_range = config_json.get("depositAmountRange", [1.5, 2.5])
    decimal_places = config_json.get("depositDecimalPlaces", 2)
    delay_range = config_json.get("depositDelayRange", [35, 85])
    shuffle_wallets = config_json.get("shuffleWallets", "no").lower()
    use_proxy = config_json.get("useProxy", False)

    supported_cex = ["binance", "okx", "bybit", "gate", "kucoin", "mexc", "huobi"]
    if cex_name not in supported_cex:
        logger.error(f"Неподдерживаемая биржа: {cex_name}. Поддерживаемые: {', '.join(supported_cex)}")
        return

    proxies = get_proxy_dict() if use_proxy else None

    async def initialize_exchange():
        if cex_name == "binance":
            return ccxt.binance({
                'apiKey': API.binance_apikey,
                'secret': API.binance_apisecret,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'},
                'proxies': proxies
            })
        elif cex_name == "okx":
            return ccxt.okx({
                'apiKey': API.okx_apikey,
                'secret': API.okx_apisecret,
                'password': API.okx_passphrase,
                'enableRateLimit': True,
                'proxies': proxies
            })
        elif cex_name == "bybit":
            return ccxt.bybit({
                'apiKey': API.bybit_apikey,
                'secret': API.bybit_apisecret,
                'enableRateLimit': True,
                'proxies': proxies
            })
        elif cex_name == "gate":
            return ccxt.gate({
                'apiKey': API.gate_apikey,
                'secret': API.gate_apisecret,
                'enableRateLimit': True,
                'proxies': proxies
            })
        elif cex_name == "kucoin":
            return ccxt.kucoin({
                'apiKey': API.kucoin_apikey,
                'secret': API.kucoin_apisecret,
                'password': API.kucoin_passphrase,
                'enableRateLimit': True,
                'proxies': proxies
            })
        elif cex_name == "mexc":
            return ccxt.mexc({
                'apiKey': API.mexc_apikey,
                'secret': API.mexc_apisecret,
                'enableRateLimit': True,
                'proxies': proxies
            })
        elif cex_name == "huobi":
            return ccxt.huobi({
                'apiKey': API.huobi_apikey,
                'secret': API.huobi_apisecret,
                'enableRateLimit': True,
                'proxies': proxies
            })

    async def get_okx_withdrawal_fee(exchange, symbol, chain_name):
        try:
            currencies = await exchange.fetch_currencies()
            for currency in currencies:
                if currency == symbol:
                    currency_info = currencies[currency]
                    network_info = currency_info.get('networks', {})
                    for net in network_info:
                        network_data = network_info[net]
                        network_id = network_data['id']
                        if network_id == chain_name:
                            return network_data.get('fee', 0)
            raise ValueError(f"Не удалось найти комиссию для {symbol} в сети {chain_name}")
        except Exception as e:
            logger.error(f"Ошибка получения комиссии OKX: {e}")
            raise

    async def withdraw(exchange, address, amount, wallet_number):
        try:
            if cex_name == "okx":
                chain_name = f"{symbol_withdraw}-{network}"
                fee = await get_okx_withdrawal_fee(exchange, symbol_withdraw, chain_name)
                await exchange.withdraw(
                    code=symbol_withdraw,
                    amount=amount,
                    address=address,
                    params={
                        "toAddress": address,
                        "chainName": chain_name,
                        "dest": 4,
                        "fee": fee,
                        "pwd": '-',
                        "amt": amount,
                        "network": network
                    }
                )
            else:
                await exchange.withdraw(
                    code=symbol_withdraw,
                    amount=amount,
                    address=address,
                    tag=None,
                    params={
                        "network": network,
                        "forceChain": 1 if cex_name == "bybit" else None
                    }
                )
            logger.info(f"[{address}] Вывел {amount:.{decimal_places}f} {symbol_withdraw} с {cex_name} (Кошелек #{wallet_number})")
            successful_transactions.append({
                "WalletAddress": address,
                "TransactionIndex": wallet_number,
                "SourceNetwork": cex_name,
                "FromToken": symbol_withdraw,
                "DestinationNetwork": network,
                "ToToken": symbol_withdraw,
                "Amount": amount,
                "USDVolume": amount,  # Предполагаем USDT = 1 USD
                "Status": "SUCCESS",
                "Error": ""
            })
        except Exception as e:
            logger.error(f"[{address}] Не удалось вывести {amount:.{decimal_places}f} {symbol_withdraw} с {cex_name}: {e}")
            failed_transactions.append({
                "WalletAddress": address,
                "TransactionIndex": wallet_number,
                "SourceNetwork": cex_name,
                "FromToken": symbol_withdraw,
                "DestinationNetwork": network,
                "ToToken": symbol_withdraw,
                "Amount": amount,
                "USDVolume": 0,
                "Status": "FAILED",
                "Error": str(e)
            })

    def get_random_delay(delay_config):
        if isinstance(delay_config, list) and len(delay_config) == 2:
            return random.uniform(delay_config[0], delay_config[1])
        return delay_config

    # Перемешивание кошельков
    numbered_accounts = list(enumerate(accounts, start=1))
    if shuffle_wallets == "yes":
        random.shuffle(numbered_accounts)
    elif shuffle_wallets != "no":
        logger.error("Неверное значение shuffleWallets: ожидается 'yes' или 'no'")
        return

    logger.info(f"Количество кошельков: {len(accounts)}")
    logger.info(f"Биржа: {cex_name}")
    logger.info(f"Сумма: {amount_range[0]} - {amount_range[1]} {symbol_withdraw}")
    logger.info(f"Сеть: {network}")

    exchange = await initialize_exchange()
    try:
        for wallet_number, (address, _) in numbered_accounts:
            amount = round(random.uniform(amount_range[0], amount_range[1]), decimal_places)
            await withdraw(exchange, address, amount, wallet_number)
            delay = get_random_delay(delay_range)
            logger.info(f"[{address}] Задержка {delay:.2f} сек перед следующим выводом")
            await asyncio.sleep(delay)
    finally:
        await exchange.close()

    # Сохранение результатов
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_pairs = set()
    for wal, info in stats.items():
        for pair_nt in info["net_token_dollars"]:
            all_pairs.add(pair_nt)
    col_names = [f"{net_slug}-{token_sym}" for (net_slug, token_sym) in all_pairs]
    col_names.sort()

    fieldnames_summary = ["Date", "WalletAddress", "TotalTransactions"] + col_names
    with open("deposit_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_summary, delimiter=';')
        writer.writeheader()
        for wal, info in stats.items():
            row = {"WalletAddress": wal, "TotalTransactions": info["transactions_count"], "Date": current_date}
            for (net_slug, token_sym) in all_pairs:
                col_name = f"{net_slug}-{token_sym}"
                usd_amount = info["net_token_dollars"].get((net_slug, token_sym), 0.0)
                row[col_name] = f"{usd_amount:.2f}$"
            writer.writerow(row)

    if successful_transactions:
        fieldnames_success = ["WalletAddress", "TransactionIndex", "SourceNetwork", "FromToken",
                              "DestinationNetwork", "ToToken", "Amount", "USDVolume", "Status", "Error"]
        with open("deposit_successful_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_success, delimiter=';')
            writer.writeheader()
            for row in successful_transactions:
                writer.writerow(row)

    if failed_transactions:
        fieldnames_failed = ["WalletAddress", "TransactionIndex", "SourceNetwork", "FromToken",
                             "DestinationNetwork", "ToToken", "Amount", "USDVolume", "Status", "Error"]
        with open("deposit_failed_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_failed, delimiter=';')
            writer.writeheader()
            for row in failed_transactions:
                writer.writerow(row)

    logger.info("Вывод с биржи завершен! Итоги сохранены в deposit_summary.csv, deposit_successful_transactions.csv и deposit_failed_transactions.csv.")