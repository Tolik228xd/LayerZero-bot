import logging
import requests
from requests.exceptions import Timeout
import asyncio
import random
import json
from web3 import Web3
from core.baseSwap import BaseSwapCommand
from data.config import JUMPER_NETWORKS_NAME, JUMPER_CHAIN_IDS
from utils.allowance_approve import check_allowance_or_approve
from libraries.funcutils import random_sleep
from core.builder import TransactionBuilder
from utils.binance_token import get_token_price
from utils.proxy_utils import get_proxy_dict
from eth_abi import encode, decode

with open("data/config_bridge.json", "r", encoding="utf-8") as f:
    config_json = json.load(f)

class BaseJumperCompatibleCommand(BaseSwapCommand):
    def __init__(self, transaction_builder_cls=TransactionBuilder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._transaction_builder = transaction_builder_cls(self._client)
        self._bridge_mode = None

    async def _get_swap_data(self) -> dict:
        if self._from_token is None:
            raise ValueError("Ошибка: from_token отсутствует. Проверьте конфигурацию JSON.")
        if self._to_token is None:
            raise ValueError("Ошибка: to_token отсутствует. Проверьте конфигурацию JSON.")

        from_token = Web3.to_checksum_address(self._from_token.address)
        to_token = Web3.to_checksum_address(self._to_token.address)
        base_url = "https://li.quest/v1/quote"
        from_chain = JUMPER_CHAIN_IDS[self._client.network.slug]
        to_chain = JUMPER_CHAIN_IDS[self._settings.to_network.lower()]
        from_address = Web3.to_checksum_address(self._account_client.address)
        try:
            token_price = await get_token_price(self._from_token.symbol)
        except ValueError:
            token_price = 1.0

        ether_amount = float(self._from_token_amount.Ether)
        decimals = int(self._from_token.decimals)
        from_amount = int(ether_amount * (10 ** decimals))

        bridge_mode_config = config_json.get("bridgeMode", {"fast": 70, "slow": 30})
        random_bridge_chance = config_json.get("random_bridge", 0)
        rand_val = random.random() * 100

        params = {
            "fromChain": from_chain,
            "toChain": to_chain,
            "fromToken": from_token,
            "toToken": to_token,
            "fromAddress": from_address,
            "fromAmount": from_amount
        }

        if rand_val < random_bridge_chance:
            self._bridge_mode = "random"
        else:
            if rand_val < bridge_mode_config.get("fast", 70):
                params["allowBridges"] = "stargateV2"
                self._bridge_mode = "fast"
            else:
                params["allowBridges"] = "stargateV2Bus"
                self._bridge_mode = "slow"

        req = requests.Request("GET", base_url, params=params).prepare()
        full_url = req.url

        proxies = get_proxy_dict()
        try:
            response = requests.get(
                full_url,
                headers={"accept": "application/json"},
                timeout=30,
                proxies=proxies
            )
            if not response.ok:
                raise ValueError(f"Ошибка API Stargate: {response.status_code}, {response.text}")
        except Timeout:
            raise
        quote = response.json()
        if 'action' not in quote or 'estimate' not in quote:
            raise ValueError(f"Некорректный ответ API: {quote}")

        return quote

    async def _swap(self):
        quote_data = await self._get_swap_data()
        tx_request = quote_data["transactionRequest"]

        api_from_amount = int(quote_data.get('action', {}).get('fromAmount', '0'))
        script_from_amount = int(self._from_token_amount.Wei)
        if api_from_amount != script_from_amount:
            self._from_token_amount.Wei = api_from_amount
            self._from_token_amount.Ether = api_from_amount / (10 ** self._from_token.decimals)

        data = tx_request['data']
        new_data = data

        if self._bridge_mode in ["fast", "slow"]:
            if data.startswith('0x'):
                data = data[2:]
            function_selector = data[:8]
            encoded_params = bytes.fromhex(data[8:])

            param_types = [
                '(bytes32,string,string,address,address,address,uint256,uint256,bool,bool)',
                '(uint16,(uint32,bytes32,uint256,uint256,bytes,bytes,bytes),(uint256,uint256),address)'
            ]

            try:
                decoded_params = decode(param_types, encoded_params)
                tuple1 = list(decoded_params[0])
                if tuple1[2] == 'lifi-api':
                    tuple1[2] = 'jumper.exchange'
                tuple1[6] = api_from_amount
                tuple2 = list(decoded_params[1])
                tuple2_inner = list(tuple2[1])
                tuple2_inner[2] = api_from_amount
                tuple2_inner[6] = bytes([0])
                tuple2[1] = tuple(tuple2_inner)
                new_encoded_params = encode(param_types, [tuple(tuple1), tuple(tuple2)])
                new_data = '0x' + function_selector + new_encoded_params.hex()
            except Exception as e:
                raise ValueError(f"Не удалось перекодировать данные транзакции: {e}")

        value_hex = tx_request.get("value", "0x0")
        value_int = int(value_hex, 16)

        gas_limit_hex = tx_request.get("gasLimit", "0x5208")
        gas_limit_int = int(gas_limit_hex, 16)

        if not self._is_from_token_native:
            await check_allowance_or_approve(
                account_client=self._account_client,
                token_amount=self._from_token_amount,
                allowance_factor=self._settings.allowance,
                spender_address=quote_data['estimate']['approvalAddress']
            )
            await random_sleep(*self._settings.delay_after_approve)

        if self._settings.gas_price_limits and self._client.network.slug in self._settings.gas_price_limits:
            allowed_gas_price_gwei = self._settings.gas_price_limits[self._client.network.slug]
            allowed_gas_price = allowed_gas_price_gwei * (10 ** 9)
            current_gas_price = self._client.web3.eth.gas_price

            while current_gas_price > allowed_gas_price:
                await asyncio.sleep(60)
                current_gas_price = self._client.web3.eth.gas_price

        adjusted_gas = int(gas_limit_int * 1.2)

        txn_dict = await self._transaction_builder.build_transaction_with_raw_data(
            from_address=Web3.to_checksum_address(self._account_client.address),
            to_address=Web3.to_checksum_address(tx_request['to']),
            value=value_int,
            data=new_data,
            gas=adjusted_gas
        )

        max_retries = 1
        retry = 0
        while True:
            try:
                txn_hash = await self._account_client.commit_transaction(txn_dict)
                break
            except Exception as e:
                error_text = str(e).lower()
                if "max fee per gas" in error_text and "less than" in error_text and retry < max_retries:
                    if "maxFeePerGas" in txn_dict:
                        old_fee = txn_dict["maxFeePerGas"]
                        txn_dict["maxFeePerGas"] = int(old_fee * 1.1)
                        retry += 1
                        continue
                raise
        try:
            receipt = self._client.web3.eth.wait_for_transaction_receipt(
                txn_hash,
                timeout=300,
                poll_latency=5
            )
        except Exception as e:
            raise

        to_amount_raw = quote_data.get("estimate", {}).get("toAmount")
        if to_amount_raw is not None:
            if isinstance(to_amount_raw, str):
                if to_amount_raw.startswith("0x"):
                    to_amount = int(to_amount_raw, 16) / (10 ** self._to_token.decimals)
                else:
                    to_amount = int(to_amount_raw) / (10 ** self._to_token.decimals)
            else:
                to_amount = float(to_amount_raw) / (10 ** self._to_token.decimals)
        else:
            to_amount = 0

        return txn_hash, to_amount

    def _init_contracts(self):
        pass