import logging
import copy
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.types import TxParams

logger = logging.getLogger(__name__)

class TransactionBuilder:

    def __init__(self, client):
        self.client = client
        self.chain_id = getattr(client.network, "chain_id", None)
        if self.chain_id is None:
            raise ValueError("chain_id отсутствует в объекте network.")

        self._draft_txn_dict = {
            "chainId": self.chain_id,
            "value": 0,
        }

    def add_from_address(self, address: ChecksumAddress):
        self._draft_txn_dict["from"] = address
        return self

    def add_to_address(self, address: ChecksumAddress):
        self._draft_txn_dict["to"] = address
        return self

    def add_value(self, value: int):
        self._draft_txn_dict["value"] = value
        return self

    def add_data(self, data: str):
        self._draft_txn_dict["data"] = data
        return self

    async def prepare_transaction(self) -> TxParams:
        txn_dict = copy.deepcopy(self._draft_txn_dict)

        from_address = txn_dict.get("from")
        if not from_address:
            raise ValueError("`from` address is required in the transaction.")

        txn_dict["nonce"] = self.client.web3.eth.get_transaction_count(from_address)

        gas_estimate = self.client.web3.eth.estimate_gas(txn_dict)
        txn_dict["gas"] = gas_estimate

        slug = getattr(self.client.network, 'slug', '')
        block_id = 'pending' if slug != 'abstract' else 'latest'
        base_fee = self.client.web3.eth.get_block(block_id)['baseFeePerGas']
        max_priority_fee = self.client.web3.eth.max_priority_fee
        max_fee_per_gas = base_fee + max_priority_fee

        txn_dict["maxFeePerGas"] = max_fee_per_gas
        txn_dict["maxPriorityFeePerGas"] = max_priority_fee

        return txn_dict

    async def build_transaction_with_raw_data(
        self,
        from_address: ChecksumAddress,
        to_address: ChecksumAddress,
        value: int,
        data: str,
        gas: int = None
    ) -> TxParams:
        self.add_from_address(from_address)
        self.add_to_address(to_address)
        self.add_value(value)
        self.add_data(data)

        if gas is not None:
            self._draft_txn_dict["gas"] = gas

        return await self.prepare_transaction()

    async def send_transaction(self, txn_dict: TxParams, private_key: str):

        web3 = self.client.web3

        signed_txn = web3.eth.account.sign_transaction(txn_dict, private_key)
        logger.info(f"Подписанная транзакция: {signed_txn}")

        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        logger.info(f"Транзакция отправлена. Хэш: {tx_hash.hex()}")

        return tx_hash

    async def wait_for_receipt(self, tx_hash):
        receipt = self.client.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt
