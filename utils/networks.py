from web3 import Web3, HTTPProvider
from utils.Slugs import NetworkSlug

JUMPER_NETWORKS_NAME = {
    NetworkSlug.ETHEREUM: "ETH",
    NetworkSlug.AVALANCHE: "AVA",
    NetworkSlug.ZKSYNC_ERA: "ERA",
    NetworkSlug.ARBITRUM_ONE: "ARB",
    NetworkSlug.LINEA: "LNA",
    NetworkSlug.OPTIMISM: "OPT",
    NetworkSlug.BASE: "BAS",
    NetworkSlug.BSC: "BSC",
    NetworkSlug.CELO: "CEL",
    NetworkSlug.MOONBEAM: "MOO",
    NetworkSlug.POLYGON: "POL",
    NetworkSlug.SCROLL: "SCL",
    NetworkSlug.GNOSIS: "DAI"
}

NETWORK_RPC_URLS = {
    NetworkSlug.ETHEREUM: "https://mainnet.infura.io/v3/<YOUR_INFURA_KEY>",
    NetworkSlug.AVALANCHE: "https://api.avax.network/ext/bc/C/rpc",
    NetworkSlug.ZKSYNC_ERA: "https://mainnet.era.zksync.io",
    NetworkSlug.ARBITRUM_ONE: "https://arb1.arbitrum.io/rpc",
    NetworkSlug.LINEA: "https://linea-mainnet.infura.io/v3/<YOUR_INFURA_KEY>",
    NetworkSlug.OPTIMISM: "https://optimism-mainnet.infura.io/v3/<YOUR_INFURA_KEY>",
    NetworkSlug.BASE: "https://mainnet.base.org",
    NetworkSlug.BSC: "https://bsc-dataseed.binance.org",
    NetworkSlug.CELO: "https://forno.celo.org",
    NetworkSlug.MOONBEAM: "https://rpc.api.moonbeam.network",
    NetworkSlug.POLYGON: "https://polygon-rpc.com",
    NetworkSlug.SCROLL: "https://scroll.io/api",
    NetworkSlug.GNOSIS: "https://rpc.gnosischain.com"
}


class MultiNetworkWeb3:

    def __init__(self, rpc_urls: dict[NetworkSlug, str]):
        self._rpc_urls = rpc_urls
        self._web3_cache = {}

    def get_web3(self, network_slug: NetworkSlug) -> Web3:
        if network_slug not in self._rpc_urls:
            raise ValueError(f"RPC URL for network {network_slug} not provided!")

        if network_slug not in self._web3_cache:
            rpc_url = self._rpc_urls[network_slug]
            self._web3_cache[network_slug] = Web3(HTTPProvider(rpc_url))

        return self._web3_cache[network_slug]

    def get_network_name(self, network_slug: NetworkSlug) -> str:

        return JUMPER_NETWORKS_NAME.get(network_slug, "UNKNOWN")


# # Пример использования
# if __name__ == "__main__":
#     # Создаем экземпляр
#     multi_web3 = MultiNetworkWeb3(NETWORK_RPC_URLS)
#
#     # Получаем web3 для Ethereum
#     eth_web3 = multi_web3.get_web3(NetworkSlug.ETHEREUM)
#     network_name = multi_web3.get_network_name(NetworkSlug.ETHEREUM)
#
#     # Пример вызова какого-то метода (получение номера последнего блока)
#     latest_block = eth_web3.eth.block_number
#     print(f"Последний блок в сети {network_name} ({NetworkSlug.ETHEREUM}): {latest_block}")
#
#     # Аналогично можно получить доступ к другим сетям:
#     bsc_web3 = multi_web3.get_web3(NetworkSlug.BSC)
#     print(f"BSC provider: {bsc_web3.provider.endpoint_uri}")
