from web3 import Web3
import asyncio

class AccountClient:
    def __init__(self, address: str, private_key: str, client):
        self.address = Web3.to_checksum_address(address)
        self.private_key = private_key
        self.client = client

    async def commit_transaction(self, txn_dict):

        web3 = self.client.web3
        block_id = "pending"
        try:
            network_slug = getattr(self.client.network, 'slug', '')
        except Exception:
            network_slug = ''
        if network_slug == 'abstract':
            block_id = 'latest'
        nonce = await asyncio.to_thread(
            web3.eth.get_transaction_count,
            self.address,
            block_id
        )
        txn_dict['nonce'] = nonce
        signed_txn = web3.eth.account.sign_transaction(txn_dict, self.private_key)
        raw = signed_txn.raw_transaction
        tx_hash = web3.eth.send_raw_transaction(raw)
        return f"0x{tx_hash.hex()}"

    async def get_token_allowance(self, token, spender_address):
        contract = self.client.web3.eth.contract(
            address=Web3.to_checksum_address(token.address),
            abi=[
                {
                    "constant": True,
                    "inputs": [
                        {"name": "_owner", "type": "address"},
                        {"name": "_spender", "type": "address"}
                    ],
                    "name": "allowance",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function"
                }
            ]
        )
        allowance = contract.functions.allowance(
            Web3.to_checksum_address(self.address),
            Web3.to_checksum_address(spender_address)
        ).call()
        return allowance

    async def approve_token_spend(self, token, amount, spender_address):
        contract = self.client.web3.eth.contract(
            address=Web3.to_checksum_address(token.address),
            abi=[
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_spender", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                }
            ]
        )
        # Estimate gas for approve
        gas_estimate = contract.functions.approve(
            Web3.to_checksum_address(spender_address),
            amount
        ).estimate_gas({"from": self.address})

        # Build transaction dict
        txn_dict = contract.functions.approve(
            Web3.to_checksum_address(spender_address),
            amount
        ).build_transaction({
            "from": self.address,
            # The nonce will be injected in commit_transaction
            # using block identifier logic above
            "gas": int(gas_estimate * 1.2),
            "gasPrice": self.client.web3.eth.gas_price
        })
        return await self.commit_transaction(txn_dict)
