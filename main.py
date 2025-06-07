# main.py
import asyncio
import logging
import json
import random
import csv
from datetime import datetime
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import requests
import platform
from utils.binance_token import get_token_price
from core.builder import TransactionBuilder
from core.baseAccountClient import AccountClient
from core.base_client import Client
from core.Settings import Settings
from core.jumper_exchange import BaseJumperCompatibleCommand
from core.deposit_from_exchange import deposit_from_exchange

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger("Main")

stats = {}
successful_transactions = []
failed_transactions = []

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class Token:
    def __init__(self, symbol: str, address: str, decimals: int, is_native: bool):
        self.symbol = symbol
        self.address = address
        self.decimals = decimals
        self.is_native = is_native

class TokenAmount:
    def __init__(self, token: Token, amount: float):
        self.token = token
        self.Ether = amount
        self.Wei = int(amount * (10 ** token.decimals))

def load_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Файл {file_path} не найден.")
    except json.JSONDecodeError:
        raise ValueError(f"Ошибка при разборе JSON-файла {file_path}.")

def validate_networks(config):
    source_networks = config.get("sourceNetworks", [])
    destination_networks = config.get("destinationNetworks", [])
    if len(set(source_networks)) == 1 and len(set(destination_networks)) == 1 and source_networks[0] == destination_networks[0]:
        raise ValueError(f"Ошибка: Исходная и целевая сети совпадают ({source_networks[0]}), транзакция невозможна.")

async def check_rpc_health(networks_data):
    print("Проверка доступности RPC...")
    faulty_rpcs = []
    for net_slug, net_info in networks_data.items():
        rpc_url = net_info.get("rpc_url")
        if not rpc_url:
            print(f"Сеть {net_slug}: RPC не указан в конфигурации")
            faulty_rpcs.append((net_slug, rpc_url, "RPC не указан"))
            continue

        web3 = Web3(Web3.HTTPProvider(rpc_url))
        try:
            is_connected = await asyncio.to_thread(web3.is_connected)
            if not is_connected:
                faulty_rpcs.append((net_slug, rpc_url, "Нет соединения"))
                continue
            block_number = await asyncio.to_thread(lambda: web3.eth.block_number)
            if block_number is None:
                faulty_rpcs.append((net_slug, rpc_url, "Не удалось получить block_number"))
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                faulty_rpcs.append((net_slug, rpc_url, "Ошибка 429: Too Many Requests"))
            else:
                faulty_rpcs.append((net_slug, rpc_url, f"Ошибка HTTP: {str(e)}"))
        except Exception as e:
            faulty_rpcs.append((net_slug, rpc_url, f"Ошибка: {str(e)}"))

    if faulty_rpcs:
        print("\nОбнаружены проблемы с RPC:")
        for slug, url, error in faulty_rpcs:
            net_name = network_names.get(slug, slug)
            print(f"- {net_name}: {url} ({error})")
        print("Рекомендуется заменить проблемные RPC в config_bridge.json перед продолжением.")
    else:
        print("Все RPC работают корректно.")
    print("")

def load_accounts(file_path):
    accounts = []
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                address, private_key = line.strip().split(',')
                checksum_address = Web3.to_checksum_address(address.strip())
                accounts.append((checksum_address, private_key.strip()))
    except FileNotFoundError:
        raise FileNotFoundError(f"Файл {file_path} не найден.")
    except ValueError:
        raise ValueError("Формат accounts.txt должен быть 'address,private_key'.")
    return accounts

def load_exchange_wallets(file_path):
    exchange_wallets = []
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                address = line.strip()
                if address:
                    checksum_address = Web3.to_checksum_address(address)
                    exchange_wallets.append(checksum_address)
        return exchange_wallets
    except FileNotFoundError:
        logger.info(f"Файл {file_path} не найден, будет использован пустой список кошельков.")
        return exchange_wallets
    except ValueError as e:
        raise ValueError(f"Ошибка в формате exchange_wallets.txt: {e}")

config_json = load_json("data/config_bridge.json")

def load_networks():
    networks_json = load_json("extra/cfg/networks.json")
    networks_list = networks_json["network"]
    network_overrides = config_json.get("networkConfigs", {})
    for net in networks_list:
        slug = net.get("slug")
        if slug in network_overrides and "rpc_url" in network_overrides[slug]:
            net["rpc_url"] = network_overrides[slug]["rpc_url"]
    return {net["slug"]: net for net in networks_list}

def get_network_by_slug(slug, networks_data):
    return networks_data.get(slug)

def get_token_for_network(network_slug, token_symbol=None, all_tokens=None):
    for t in all_tokens:
        if t["network"] == network_slug:
            if token_symbol and t["symbol"] == token_symbol:
                return Token(
                    symbol=t["symbol"],
                    address=t["address"],
                    decimals=t["decimals"],
                    is_native=t["params"].get("is_native", False)
                )
            elif not token_symbol and t["params"].get("is_native", False):
                return Token(
                    symbol=t["symbol"],
                    address=t["address"],
                    decimals=t["decimals"],
                    is_native=True
                )
    return None

async def get_token_balance(client: Client, account_address: str, token_obj: Token):
    web3 = client.web3
    if token_obj.is_native:
        balance_wei = web3.eth.get_balance(account_address)
        return balance_wei / (10 ** token_obj.decimals)
    abi_balance_of = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        }
    ]
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(token_obj.address),
        abi=abi_balance_of
    )
    try:
        balance_wei = contract.functions.balanceOf(Web3.to_checksum_address(account_address)).call()
        return balance_wei / (10 ** token_obj.decimals)
    except Exception as e:
        logger.error(f"Ошибка при получении баланса ERC20: {e}")
        return 0

def get_random_delay(delay_config):
    if isinstance(delay_config, list) and len(delay_config) == 2:
        return random.uniform(delay_config[0], delay_config[1])
    return delay_config

network_names = {
    "base": "Base",
    "arbitrum_one": "Arbitrum One",
    "optimism": "Optimism",
    "linea": "Linea",
    "ethereum": "Ethereum"
}

async def process_one_transaction(
    address, _priv, tx_index, total_tx_count,
    networks_data, tokens_data,
    source_net_slug, from_symbol,
    dest_net_slug, to_symbol,
    min_pct, max_pct,
    transaction_delay_config
):
    logger.info(f"[{address}] Начинаю транзакцию {tx_index}/{total_tx_count}")
    from_token_obj = get_token_for_network(source_net_slug, from_symbol, tokens_data)
    if not from_token_obj:
        logger.error(f"[{address}] Токен {from_symbol} не найден в сети {source_net_slug}.")
        return
    to_token_obj = get_token_for_network(dest_net_slug, to_symbol, tokens_data)
    if not to_token_obj:
        logger.error(f"[{address}] Токен {to_symbol} не найден в сети {dest_net_slug}.")
        return

    net_info = get_network_by_slug(source_net_slug, networks_data)
    if not net_info:
        logger.error(f"[{address}] Сеть {source_net_slug} не найдена в конфигурации.")
        return

    use_proxy = config_json.get("useProxy", False)
    client = Client(
        network_slug=source_net_slug,
        rpc_url=net_info["rpc_url"],
        chain_id=net_info["chain_id"],
        txn_explorer_url=net_info.get("txn_explorer_url", ""),
        use_proxy=use_proxy
    )
    if use_proxy:
        logger.info(f"[{address}] Использую прокси для сети {source_net_slug}")

    # Устанавливаем default_block='latest' для сети abstract
    if source_net_slug == "abstract":
        client.web3.eth.default_block = "latest"
        logger.info(f"[{address}] Установлен default_block='latest' для сети {source_net_slug}")

    client.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    logger.info(f"[{address}] Проверка баланса {from_symbol} в сети {source_net_slug}")
    balance_float = await get_token_balance(client, address, from_token_obj)
    logger.info(f"[{address}] Баланс {from_symbol} в сети {source_net_slug}: {balance_float:.6f}")
    if balance_float <= 0:
        logger.error(f"[{address}] Баланс 0 для {from_token_obj.symbol} в сети {source_net_slug}.")
        return

    # Устанавливаем параметры газа
    gas_limit = 100000  # Уменьшаем gas_limit до 100,000
    if source_net_slug == "abstract":
        gas_price = 1000000000  # 1 Gwei для abstract
        logger.info(f"[{address}] Используем фиксированную цену газа 1 Gwei для сети {source_net_slug}")
    else:
        logger.info(f"[{address}] Получение gas_price для сети {source_net_slug}")
        gas_price = client.web3.eth.gas_price

    gas_cost = gas_price * gas_limit / 10**18
    gas_buffer = gas_cost * 1.2  # Уменьшаем множитель до 1.2
    logger.info(f"[{address}] Расчётная стоимость газа: {gas_cost:.6f} ETH, резерв газа: {gas_buffer:.6f} ETH")

    native_token = get_token_for_network(source_net_slug, None, tokens_data)
    if not native_token:
        logger.error(f"[{address}] Нативный токен не найден в сети {source_net_slug}.")
        return
    logger.info(f"[{address}] Проверка баланса нативного токена ({native_token.symbol}) в сети {source_net_slug}")
    native_balance = await get_token_balance(client, address, native_token)
    logger.info(f"[{address}] Баланс нативного токена ({native_token.symbol}) в сети {source_net_slug}: {native_balance:.6f}")

    # Рассчитываем сумму для свапа с учётом газа
    rand_pct = random.uniform(min_pct, max_pct)
    logger.info(f"[{address}] Выбранный процент для свапа: {rand_pct:.2f}%")
    amount_to_bridge = balance_float * (rand_pct / 100.0)

    if not from_token_obj.is_native:
        # Для ERC-20 токенов проверяем только баланс токена и газа
        if amount_to_bridge > balance_float:
            amount_to_bridge = balance_float * 0.95  # Оставляем 5% резерва
            logger.info(f"[{address}] Сумма скорректирована до 95% баланса: {amount_to_bridge:.6f} {from_symbol}")
        if native_balance < gas_buffer:
            logger.error(f"[{address}] Недостаточно газа: требуется {gas_buffer:.6f} {native_token.symbol}, доступно {native_balance:.6f}")
            failed_transactions.append({
                "WalletAddress": address,
                "TransactionIndex": tx_index,
                "SourceNetwork": source_net_slug,
                "FromToken": from_symbol,
                "DestinationNetwork": dest_net_slug,
                "ToToken": to_symbol,
                "Amount": amount_to_bridge,
                "USDVolume": 0,
                "Status": "FAILED",
                "Error": f"Insufficient gas: need {gas_buffer:.6f} {native_token.symbol}, have {native_balance:.6f}"
            })
            return
    else:
        # Для нативного токена (ETH) учитываем сумму транзакции и газ
        total_required = amount_to_bridge + gas_buffer
        if total_required > native_balance:
            # Корректируем amount_to_bridge, чтобы уместиться в баланс
            amount_to_bridge = max(0, native_balance - gas_buffer)
            logger.info(f"[{address}] Сумма скорректирована из-за недостаточного баланса: {amount_to_bridge:.6f} {from_symbol}")
        if amount_to_bridge <= 0:
            logger.error(f"[{address}] Сумма для перевода после корректировки <= 0: {amount_to_bridge:.6f} {from_symbol}")
            failed_transactions.append({
                "WalletAddress": address,
                "TransactionIndex": tx_index,
                "SourceNetwork": source_net_slug,
                "FromToken": from_symbol,
                "DestinationNetwork": dest_net_slug,
                "ToToken": to_symbol,
                "Amount": amount_to_bridge,
                "USDVolume": 0,
                "Status": "FAILED",
                "Error": f"Insufficient funds: need {total_required:.6f} {native_token.symbol}, have {native_balance:.6f}"
            })
            return

    logger.info(f"[{address}] Сумма для перевода: {amount_to_bridge:.6f} {from_symbol}")
    logger.info(f"[{address}] Общая требуемая сумма (сумма + газ): {amount_to_bridge + gas_buffer:.6f} {native_token.symbol}")

    from_token_amount = TokenAmount(from_token_obj, amount_to_bridge)
    gas_price_limits = config_json.get("gasPriceLimits")
    settings = Settings(
        to_network=dest_net_slug,
        allowance=1.1,
        delay_after_approve=(1, 3),
        gas_amount=False,
        gas_price_limits=gas_price_limits
    )
    swap_command = BaseJumperCompatibleCommand(
        transaction_builder_cls=TransactionBuilder,
        client=client,
        account_client=AccountClient(address, _priv, client),
        settings=settings,
        from_token_amount=from_token_amount,
        from_token=from_token_obj,
        to_token=to_token_obj,
        is_from_token_native=from_token_obj.is_native
    )
    try:
        logger.info(f"[{address}] Выполнение свопа для сети {source_net_slug}")
        txn_hash, to_amount = await asyncio.wait_for(swap_command._swap(), timeout=300)
        bridge_mode = getattr(swap_command, '_bridge_mode', 'unknown')
        source_net_name = network_names.get(source_net_slug, source_net_slug)
        dest_net_name = network_names.get(dest_net_slug, dest_net_slug)
        summary = (f"[{address}] Tx {tx_index}/{total_tx_count} - {bridge_mode} - "
                   f"{amount_to_bridge:.6f} {from_token_obj.symbol}({source_net_name}) "
                   f"=> {to_amount:.6f} {to_token_obj.symbol}({dest_net_name})")
        logger.info(summary)
        hash_line = f"[{address}] Hash - '{client.network.txn_explorer_url}{txn_hash}'"
        logger.info(hash_line)

        try:
            token_price = await get_token_price(from_symbol)
            logger.info(f"[{address}] Цена токена {from_symbol}: {token_price:.2f} USD")
        except Exception as e:
            logger.warning(f"[{address}] Не удалось получить цену токена {from_symbol}: {e}")
            token_price = 0.0
        usd_volume = amount_to_bridge * token_price
        if address not in stats:
            stats[address] = {"transactions_count": 0, "net_token_dollars": {}}
        stats[address]["transactions_count"] += 1
        pair = (source_net_slug, from_symbol)
        current_dollars = stats[address]["net_token_dollars"].get(pair, 0.0)
        stats[address]["net_token_dollars"][pair] = current_dollars + usd_volume
        successful_transactions.append({
            "WalletAddress": address,
            "TransactionIndex": tx_index,
            "SourceNetwork": source_net_slug,
            "FromToken": from_symbol,
            "DestinationNetwork": dest_net_slug,
            "ToToken": to_symbol,
            "Amount": amount_to_bridge,
            "USDVolume": usd_volume,
            "Status": "SUCCESS",
            "Error": ""
        })
    except asyncio.TimeoutError:
        logger.error(f"[{address}] Tx {tx_index}/{total_tx_count} - Таймаут при выполнении свапа (5 минут)")
        failed_transactions.append({
            "WalletAddress": address,
            "TransactionIndex": tx_index,
            "SourceNetwork": source_net_slug,
            "FromToken": from_symbol,
            "DestinationNetwork": dest_net_slug,
            "ToToken": to_symbol,
            "Amount": amount_to_bridge,
            "USDVolume": 0,
            "Status": "FAILED",
            "Error": "Timeout after 5 minutes"
        })
    except Exception as e:
        error_text = str(e)
        source_net_name = network_names.get(source_net_slug, source_net_slug)
        dest_net_name = network_names.get(dest_net_slug, dest_net_slug)
        bridge_mode = getattr(swap_command, '_bridge_mode', 'unknown')
        error_summary = (f"[{address}] Tx {tx_index}/{total_tx_count} - {bridge_mode} - Ошибка при свапе: "
                         f"{amount_to_bridge:.6f} {from_token_obj.symbol}({source_net_name}) "
                         f"=> {to_token_obj.symbol}({dest_net_name}). Ошибка: {error_text}")
        logger.error(error_summary)
        failed_transactions.append({
            "WalletAddress": address,
            "TransactionIndex": tx_index,
            "SourceNetwork": source_net_slug,
            "FromToken": from_symbol,
            "DestinationNetwork": dest_net_slug,
            "ToToken": to_symbol,
            "Amount": amount_to_bridge,
            "USDVolume": 0,
            "Status": "FAILED",
            "Error": error_text
        })

    delay_tx = get_random_delay(transaction_delay_config)
    logger.info(f"[{address}] Завершил Tx {tx_index}/{total_tx_count}. Задержка {delay_tx:.2f} сек между транзакциями.")
    await asyncio.sleep(delay_tx)

async def send_transaction(
    address, _priv, tx_index, total_tx_count,
    networks_data, token_symbol, network_slug, to_address, amount,
    transaction_delay_config=None
):
    logger.info(f"[{address}] Начинаю транзакцию {tx_index}/{total_tx_count}")
    net_info = get_network_by_slug(network_slug, networks_data)
    if not net_info:
        logger.error(f"[{address}] Сеть {network_slug} не найдена в конфигурации.")
        return

    use_proxy = config_json.get("useProxy", False)
    client = Client(
        network_slug=network_slug,
        rpc_url=net_info["rpc_url"],
        chain_id=net_info["chain_id"],
        txn_explorer_url=net_info.get("txn_explorer_url", ""),
        use_proxy=use_proxy
    )
    if use_proxy:
        logger.info(f"[{address}] Использую прокси для подключения к RPC сети {network_slug}")

    token_obj = get_token_for_network(network_slug, token_symbol, tokens_data)
    if not token_obj:
        logger.error(f"[{address}] Токен {token_symbol} не найден в сети {network_slug}.")
        return

    balance = await get_token_balance(client, address, token_obj)
    if balance <= 0:
        logger.error(f"[{address}] Баланс 0 для {token_symbol} в сети {network_slug}.")
        return

    amount_to_send = min(amount, balance)
    web3 = client.web3
    nonce = web3.eth.get_transaction_count(address)
    gas_price = web3.eth.gas_price

    if token_obj.is_native:
        tx = {
            'nonce': nonce,
            'to': to_address,
            'value': web3.to_wei(amount_to_send, 'ether'),
            'gasPrice': gas_price,
            'chainId': net_info["chain_id"]
        }
        try:
            gas_limit = web3.eth.estimate_gas(tx)
            tx['gas'] = int(gas_limit * 1.2)
        except Exception as e:
            logger.warning(f"[{address}] Не удалось оценить газ: {e}. Использую запасной лимит 30000.")
            tx['gas'] = 30000
    else:
        erc20_abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            }
        ]
        contract = web3.eth.contract(address=token_obj.address, abi=erc20_abi)
        tx = contract.functions.transfer(
            to_address,
            int(amount_to_send * 10 ** token_obj.decimals)
        ).build_transaction({
            'nonce': nonce,
            'gasPrice': gas_price,
            'chainId': net_info["chain_id"]
        })
        try:
            gas_limit = web3.eth.estimate_gas(tx)
            tx['gas'] = int(gas_limit * 1.2)
        except Exception as e:
            logger.warning(f"[{address}] Не удалось оценить газ: {e}. Использую запасной лимит 100000.")
            tx['gas'] = 100000

    try:
        signed_tx = web3.eth.account.sign_transaction(tx, private_key=_priv)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt.status == 1:
            net_name = network_names.get(network_slug, network_slug)
            logger.info(f"[{address}] Tx {tx_index}/{total_tx_count} - Перевод - {amount_to_send:.6f} {token_symbol}({net_name}) => {to_address}")
            logger.info(f"[{address}] Hash - '{client.network.txn_explorer_url}{tx_hash.hex()}'")

            try:
                token_price = await get_token_price(token_symbol)
            except Exception:
                token_price = 0.0
            usd_volume = amount_to_send * token_price
            if address not in stats:
                stats[address] = {"transactions_count": 0, "net_token_dollars": {}}
            stats[address]["transactions_count"] += 1
            pair = (network_slug, token_symbol)
            current_dollars = stats[address]["net_token_dollars"].get(pair, 0.0)
            stats[address]["net_token_dollars"][pair] = current_dollars + usd_volume
            successful_transactions.append({
                "WalletAddress": address,
                "TransactionIndex": tx_index,
                "SourceNetwork": network_slug,
                "FromToken": token_symbol,
                "DestinationNetwork": network_slug,
                "ToToken": token_symbol,
                "Amount": amount_to_send,
                "USDVolume": usd_volume,
                "Status": "SUCCESS",
                "Error": ""
            })
        else:
            logger.error(f"[{address}] Транзакция не удалась: {tx_hash.hex()}")
            failed_transactions.append({
                "WalletAddress": address,
                "TransactionIndex": tx_index,
                "SourceNetwork": network_slug,
                "FromToken": token_symbol,
                "DestinationNetwork": network_slug,
                "ToToken": token_symbol,
                "Amount": amount_to_send,
                "USDVolume": 0,
                "Status": "FAILED",
                "Error": "Transaction failed on-chain"
            })
    except Exception as e:
        logger.error(f"[{address}] Ошибка при переводе: {amount_to_send:.6f} {token_symbol}({network_slug}) => {to_address}. Ошибка: {str(e)}")
        failed_transactions.append({
            "WalletAddress": address,
            "TransactionIndex": tx_index,
            "SourceNetwork": network_slug,
            "FromToken": token_symbol,
            "DestinationNetwork": network_slug,
            "ToToken": token_symbol,
            "Amount": amount_to_send,
            "USDVolume": 0,
            "Status": "FAILED",
            "Error": str(e)
        })

    delay_tx = get_random_delay(transaction_delay_config) if transaction_delay_config else 0
    logger.info(f"[{address}] Завершил Tx {tx_index}/{total_tx_count}. Задержка {delay_tx:.2f} сек между транзакциями.")
    await asyncio.sleep(delay_tx)

async def process_one_account(
    account,
    networks_data,
    tokens_data,
    source_networks,
    destination_networks,
    from_tokens,
    to_tokens,
    min_pct,
    max_pct,
    transaction_delay_config,
    account_delay_config
):
    address, _priv = account
    delay_wallet = get_random_delay(account_delay_config)
    logger.info(f"[{address}] Начинаю обработку аккаунта. Задержка между кошельками: {delay_wallet:.2f} сек.")
    await asyncio.sleep(delay_wallet)

    valid_source_pairs = []
    for net_slug in source_networks:
        for from_symbol in from_tokens:
            token_obj = get_token_for_network(net_slug, from_symbol, tokens_data)
            if token_obj is not None:
                valid_source_pairs.append((net_slug, from_symbol))
    if not valid_source_pairs:
        logger.error(f"[{address}] Нет допустимых пар (сеть, токен) для исходящей сети.")
        return

    tc = config_json.get("transactionCount", 1)
    if isinstance(tc, list) and len(tc) == 2:
        transaction_count = random.randint(tc[0], tc[1])
    else:
        transaction_count = tc

    tx_index = 1
    while tx_index <= transaction_count:
        source_net_slug, from_symbol = random.choice(valid_source_pairs)
        dest_net_slug = random.choice(destination_networks)
        to_symbol = random.choice(to_tokens)
        if source_net_slug == dest_net_slug:
            continue
        if get_token_for_network(source_net_slug, from_symbol, tokens_data) is None:
            logger.info(f"[{address}] Токен {from_symbol} не найден в сети {source_net_slug}. Выбираю другую пару.")
            continue
        if get_token_for_network(dest_net_slug, to_symbol, tokens_data) is None:
            logger.info(f"[{address}] Токен {to_symbol} не найден в сети {dest_net_slug}. Выбираю другую пару.")
            continue
        await process_one_transaction(
            address, _priv, tx_index, transaction_count,
            networks_data, tokens_data,
            source_net_slug, from_symbol,
            dest_net_slug, to_symbol,
            min_pct, max_pct,
            config_json.get("transactionDelay", [5, 5])
        )
        tx_index += 1
    logger.info(f"[{address}] Завершил обработку аккаунта")

async def check_balances(accounts, networks_data, tokens_data, source_networks, from_tokens):
    logger.info("Начинаю проверку балансов...")
    use_proxy = config_json.get("useProxy", False)
    balances_data = {}

    for address, _priv in accounts:
        balances_data[address] = {}
        balance_summary = []
        print(f"[{address}] Проверка баланса для аккаунта")
        for net_slug in source_networks:
            net_info = get_network_by_slug(net_slug, networks_data)
            if not net_info:
                logger.error(f"Сеть {net_slug} не найдена в конфигурации")
                continue

            client = Client(
                network_slug=net_slug,
                rpc_url=net_info["rpc_url"],
                chain_id=net_info["chain_id"],
                txn_explorer_url=net_info.get("txn_explorer_url", ""),
                use_proxy=use_proxy
            )
            if use_proxy:
                pass

            for token_symbol in from_tokens:
                token_obj = get_token_for_network(net_slug, token_symbol, tokens_data)
                if not token_obj:
                    print(f"[{address}] Токен {token_symbol} не найден в сети {net_slug}")
                    continue

                balance = await get_token_balance(client, address, token_obj)
                net_name = network_names.get(net_slug, net_slug)
                balances_data[address][f"{net_name}_{token_symbol}"] = balance
                balance_summary.append(f"{net_name}: {balance:.6f} {token_symbol}")

        summary = f"[{address}] - {'; '.join(balance_summary)}"
        print(summary)
        await asyncio.sleep(1)

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_columns = set()
    for balances in balances_data.values():
        all_columns.update(balances.keys())
    all_columns = sorted(list(all_columns))

    fieldnames = ["Date", "WalletAddress"] + all_columns
    with open("balances.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for address, balances in balances_data.items():
            row = {"WalletAddress": address, "Date": current_date}
            for col in all_columns:
                balance = balances.get(col, 0.0)
                row[col] = f"{balance:.6f}"
            writer.writerow(row)

    print("Проверка балансов завершена! Результаты сохранены в balances.csv")

async def swap_process(accounts, networks_data, tokens_data):
    try:
        validate_networks(config_json)
    except ValueError as e:
        logger.error(e)
        return

    source_networks = config_json["sourceNetworks"]
    destination_networks = config_json["destinationNetworks"]
    from_tokens = config_json["fromTokens"]
    to_tokens = config_json["toTokens"]
    min_pct, max_pct = config_json["percentageRange"]

    transaction_delay_config = config_json.get("transactionDelay", [5, 5])
    account_delay_config = config_json.get("delayBetweenAccounts", [10, 10])
    concurrency = config_json.get("threads", 1)

    semaphore = asyncio.Semaphore(concurrency)

    async def handle_account_with_sema(acc):
        async with semaphore:
            await process_one_account(
                acc,
                networks_data,
                tokens_data,
                source_networks,
                destination_networks,
                from_tokens,
                to_tokens,
                min_pct,
                max_pct,
                transaction_delay_config,
                account_delay_config
            )

    tasks = [asyncio.create_task(handle_account_with_sema(acc)) for acc in accounts]
    await asyncio.gather(*tasks, return_exceptions=True)

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_pairs = set()
    for wal, info in stats.items():
        for pair_nt in info["net_token_dollars"]:
            all_pairs.add(pair_nt)
    col_names = [f"{net_slug}-{token_sym}" for (net_slug, token_sym) in all_pairs]
    col_names.sort()

    fieldnames_summary = ["Date", "WalletAddress", "TotalTransactions"] + col_names
    with open("summary.csv", "w", newline="", encoding="utf-8-sig") as f:
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
        with open("successful_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_success, delimiter=';')
            writer.writeheader()
            for row in successful_transactions:
                writer.writerow(row)

    if failed_transactions:
        fieldnames_failed = ["WalletAddress", "TransactionIndex", "SourceNetwork", "FromToken",
                             "DestinationNetwork", "ToToken", "Amount", "USDVolume", "Status", "Error"]
        with open("failed_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_failed, delimiter=';')
            writer.writeheader()
            for row in failed_transactions:
                writer.writerow(row)

    logger.info("Готово! Итоги сохранены в summary.csv, successful_transactions.csv и failed_transactions.csv.")

async def circular_swap_process(accounts, networks_data, tokens_data):
    logger.info("Запуск кругового прогона свапов...")
    source_networks = config_json["sourceNetworks"]
    from_tokens = config_json["fromTokens"]
    to_tokens = config_json["toTokens"]
    min_pct, max_pct = config_json["percentageRange"]
    transaction_delay_config = config_json.get("transactionDelay", [5, 5])
    account_delay_config = config_json.get("delayBetweenAccounts", [10, 10])
    concurrency = config_json.get("threads", 1)
    circular_rounds = config_json.get("circularRounds", 1)

    print("\nНастройки кругового прогона:")
    print(f"Доступные сети: {source_networks}")
    end_network = input("Введите конечную сеть для всех токенов: ").strip()
    if end_network not in source_networks:
        logger.error("Указанная конечная сеть отсутствует в sourceNetworks")
        return

    print(f"Доступные токены для прогона: {to_tokens}")
    final_token = input("Введите токен, который будет использоваться в прогоне: ").strip()
    if final_token not in to_tokens:
        logger.error(f"Токен {final_token} не найден в toTokens")
        return

    logger.info(f"Конечная сеть: {end_network}, токен для прогона: {final_token}")
    logger.info(f"Количество кругов из конфига: {circular_rounds}")

    semaphore = asyncio.Semaphore(concurrency)

    async def process_account_with_sema(address, _priv):
        async with semaphore:
            await process_account_circular(address, _priv, networks_data, tokens_data, source_networks, end_network, final_token, circular_rounds, min_pct, max_pct, transaction_delay_config, account_delay_config)

    async def process_account_circular(address, _priv, networks_data, tokens_data, source_networks, end_network, final_token, circular_rounds, min_pct, max_pct, transaction_delay_config, account_delay_config):
        balances = {}
        use_proxy = config_json.get("useProxy", False)
        for net_slug in source_networks:
            net_info = get_network_by_slug(net_slug, networks_data)
            if not net_info:
                logger.error(f"[{address}] Сеть {net_slug} не найдена в конфигурации")
                continue
            client = Client(
                network_slug=net_slug,
                rpc_url=net_info["rpc_url"],
                chain_id=net_info["chain_id"],
                txn_explorer_url=net_info.get("txn_explorer_url", ""),
                use_proxy=use_proxy
            )
            token_obj = get_token_for_network(net_slug, final_token, tokens_data)
            if not token_obj:
                logger.info(f"[{address}] Токен {final_token} не найден в сети {net_slug}, баланс считается 0")
                balances[net_slug] = 0
                continue
            balance = await get_token_balance(client, address, token_obj)
            balances[net_slug] = balance
            logger.info(f"[{address}] Баланс {final_token} в сети {net_slug}: {balance:.6f}")

        start_network = max(balances, key=balances.get, default=end_network)
        logger.info(f"[{address}] Сеть с максимальным балансом {final_token}: {start_network} ({balances[start_network]:.6f})")

        network_order = [start_network]
        remaining_networks = [net for net in source_networks if net != start_network and net != end_network]
        random.shuffle(remaining_networks)
        network_order.extend(remaining_networks)
        network_order.append(end_network)
        logger.info(f"[{address}] Случайный порядок сетей для кругового прогона: {network_order}")

        tx_index = 1
        total_tx_count = circular_rounds * (len(network_order) - 1)
        logger.info(f"[{address}] Всего транзакций в круговом прогоне: {total_tx_count}")

        for round in range(circular_rounds):
            logger.info(f"[{address}] Начинаю круг {round + 1} из {circular_rounds}")
            for i in range(len(network_order) - 1):
                source_net_slug = network_order[i]
                dest_net_slug = network_order[i + 1]
                client = Client(
                    network_slug=source_net_slug,
                    rpc_url=get_network_by_slug(source_net_slug, networks_data)["rpc_url"],
                    chain_id=get_network_by_slug(source_net_slug, networks_data)["chain_id"],
                    txn_explorer_url=get_network_by_slug(source_net_slug, networks_data).get("txn_explorer_url", ""),
                    use_proxy=config_json.get("useProxy", False)
                )
                token_obj = get_token_for_network(source_net_slug, final_token, tokens_data)
                if not token_obj:
                    logger.error(f"[{address}] Токен {final_token} не найден в сети {source_net_slug}")
                    continue
                balance = await get_token_balance(client, address, token_obj)
                if balance <= 0:
                    logger.info(f"[{address}] Баланс {final_token} в сети {source_net_slug} равен 0, пропускаю транзакцию")
                    continue

                logger.info(f"[{address}] Выполняю транзакцию {tx_index}/{total_tx_count} в круге {round + 1} ({source_net_slug} -> {dest_net_slug})")
                await process_one_transaction(
                    address, _priv, tx_index, total_tx_count,
                    networks_data, tokens_data,
                    source_net_slug, final_token,
                    dest_net_slug, final_token,
                    min_pct, max_pct,
                    transaction_delay_config
                )
                tx_index += 1

            logger.info(f"[{address}] Завершил круг {round + 1} из {circular_rounds}")

        delay_wallet = get_random_delay(account_delay_config)
        logger.info(f"[{address}] Завершил круговой прогон. Задержка между аккаунтами: {delay_wallet:.2f} сек.")
        await asyncio.sleep(delay_wallet)

    tasks = [asyncio.create_task(process_account_with_sema(address, _priv)) for address, _priv in accounts]
    await asyncio.gather(*tasks, return_exceptions=True)

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_pairs = set()
    for wal, info in stats.items():
        for pair_nt in info["net_token_dollars"]:
            all_pairs.add(pair_nt)
    col_names = [f"{net_slug}-{token_sym}" for (net_slug, token_sym) in all_pairs]
    col_names.sort()

    fieldnames_summary = ["Date", "WalletAddress", "TotalTransactions"] + col_names
    with open("circular_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
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
        with open("circular_successful_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_success, delimiter=';')
            writer.writeheader()
            for row in successful_transactions:
                writer.writerow(row)

    if failed_transactions:
        fieldnames_failed = ["WalletAddress", "TransactionIndex", "SourceNetwork", "FromToken",
                             "DestinationNetwork", "ToToken", "Amount", "USDVolume", "Status", "Error"]
        with open("circular_failed_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_failed, delimiter=';')
            writer.writeheader()
            for row in failed_transactions:
                writer.writerow(row)

    logger.info("Круговой прогон завершен! Итоги сохранены в circular_summary.csv, circular_successful_transactions.csv и circular_failed_transactions.csv.")

async def withdraw_to_exchange(accounts, networks_data, tokens_data, exchange_wallets):
    logger.info("Запуск вывода на биржу...")
    source_network = config_json.get("withdrawNetwork")
    withdraw_token = config_json.get("withdrawToken")
    withdraw_mode = config_json.get("withdrawMode", "percentage")
    withdraw_percentage = config_json.get("withdrawPercentage", [90, 100])
    withdraw_amount = config_json.get("withdrawAmount", 0)
    transaction_delay_config = config_json.get("transactionDelay", [5, 5])
    account_delay_config = config_json.get("delayBetweenAccounts", [10, 20])

    if not exchange_wallets:
        raise ValueError("Ошибка: Файл exchange_wallets.txt пуст или не содержит валидных адресов. Укажите кошельки для вывода.")

    if source_network not in config_json["sourceNetworks"]:
        logger.error(f"Сеть вывода {source_network} не найдена в sourceNetworks")
        return
    if withdraw_token not in config_json["toTokens"]:
        logger.error(f"Токен вывода {withdraw_token} не найден в toTokens")
        return

    total_accounts = len(accounts)
    total_exchanges = len(exchange_wallets)
    logger.info(f"Количество аккаунтов: {total_accounts}, количество биржевых кошельков: {total_exchanges}")

    for idx, (address, _priv) in enumerate(accounts):
        exchange_wallet = exchange_wallets[idx % total_exchanges]
        logger.info(f"[{address}] Начинаю вывод на биржу {exchange_wallet}")

        client = Client(
            network_slug=source_network,
            rpc_url=get_network_by_slug(source_network, networks_data)["rpc_url"],
            chain_id=get_network_by_slug(source_network, networks_data)["chain_id"],
            txn_explorer_url=get_network_by_slug(source_network, networks_data).get("txn_explorer_url", ""),
            use_proxy=config_json.get("useProxy", False)
        )
        token_obj = get_token_for_network(source_network, withdraw_token, tokens_data)
        if not token_obj:
            logger.error(f"[{address}] Токен {withdraw_token} не найден в сети {source_network}")
            continue

        balance = await get_token_balance(client, address, token_obj)
        if balance <= 0:
            logger.info(f"[{address}] Баланс {withdraw_token} в сети {source_network} равен 0, пропускаю")
            continue

        if withdraw_mode == "percentage":
            min_pct, max_pct = withdraw_percentage
            rand_pct = random.uniform(min_pct, max_pct)
            amount_to_withdraw = balance * (rand_pct / 100.0)
        else:
            amount_to_withdraw = min(withdraw_amount, balance)

        await send_transaction(
            address, _priv, 1, 1,
            networks_data, withdraw_token, source_network, exchange_wallet,
            amount_to_withdraw, transaction_delay_config
        )

        delay_wallet = get_random_delay(account_delay_config)
        logger.info(f"[{address}] Завершил вывод на биржу. Задержка между аккаунтами: {delay_wallet:.2f} сек.")
        await asyncio.sleep(delay_wallet)

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_pairs = set()
    for wal, info in stats.items():
        for pair_nt in info["net_token_dollars"]:
            all_pairs.add(pair_nt)
    col_names = [f"{net_slug}-{token_sym}" for (net_slug, token_sym) in all_pairs]
    col_names.sort()

    fieldnames_summary = ["Date", "WalletAddress", "TotalTransactions"] + col_names
    with open("withdraw_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
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
        with open("withdraw_successful_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_success, delimiter=';')
            writer.writeheader()
            for row in successful_transactions:
                writer.writerow(row)

    if failed_transactions:
        fieldnames_failed = ["WalletAddress", "TransactionIndex", "SourceNetwork", "FromToken",
                             "DestinationNetwork", "ToToken", "Amount", "USDVolume", "Status", "Error"]
        with open("withdraw_failed_transactions.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_failed, delimiter=';')
            writer.writeheader()
            for row in failed_transactions:
                writer.writerow(row)

    logger.info("Вывод на биржу завершен! Итоги сохранены в withdraw_summary.csv, withdraw_successful_transactions.csv и withdraw_failed_transactions.csv.")

async def main():
    global tokens_data, stats, successful_transactions, failed_transactions, config_json
    networks_data = load_networks()
    tokens_json = load_json("extra/cfg/tokens.json")
    tokens_data = tokens_json["network_token"]
    accounts = load_accounts("data/accounts.txt")
    exchange_wallets = load_exchange_wallets("data/exchange_wallets.txt")
    random.shuffle(accounts)
    source_networks = config_json["sourceNetworks"]
    from_tokens = config_json["fromTokens"]

    await check_rpc_health(networks_data)

    while True:
        print("\nМеню:")
        print("1. Проверить баланс во всех сетях и токенах")
        print("2. Запустить процесс свапа")
        print("3. Круговой прогон свапов")
        print("4. Вывод на биржу")
        print("5. Ввод с биржи")
        print("6. Выйти")
        choice = input("Выберите опцию (1-6): ")

        if choice == "1":
            await check_balances(accounts, networks_data, tokens_data, source_networks, from_tokens)
        elif choice == "2":
            await swap_process(accounts, networks_data, tokens_data)
        elif choice == "3":
            await circular_swap_process(accounts, networks_data, tokens_data)
        elif choice == "4":
            await withdraw_to_exchange(accounts, networks_data, tokens_data, exchange_wallets)
        elif choice == "5":
            await deposit_from_exchange(accounts, config_json, stats, successful_transactions, failed_transactions)
        elif choice == "6":
            break
        else:
            print("Неверный выбор, попробуйте снова.")

if __name__ == "__main__":
    asyncio.run(main())