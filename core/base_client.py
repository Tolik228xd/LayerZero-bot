from web3 import Web3
from utils.proxy_utils import get_proxy

class Network:
    def __init__(self, slug: str, chain_id: int, txn_explorer_url: str):
        self.slug = slug
        self.chain_id = chain_id
        self.txn_explorer_url = txn_explorer_url

class Client:
    def __init__(self, network_slug: str, rpc_url: str, chain_id: int, txn_explorer_url: str = "", use_proxy: bool = False):
        self._network = Network(slug=network_slug, chain_id=chain_id, txn_explorer_url=txn_explorer_url)
        if use_proxy:
            proxy = get_proxy()
            if proxy:
                self.web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"proxies": {"http": proxy, "https": proxy}}))
            else:
                self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        else:
            self.web3 = Web3(Web3.HTTPProvider(rpc_url))

    @property
    def network(self):
        return self._network

    def wait_for_transaction_receipt(self, tx_hash, timeout=3600, poll_latency=2):
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout, poll_latency=poll_latency)
        return receipt