
class Network:


    def __init__(self, slug: str, chain_id: int, txn_explorer_url: str = ""):
        self.slug = slug
        self.chain_id = chain_id
        self.txn_explorer_url = txn_explorer_url

    def __repr__(self):
        return f"Network(slug={self.slug}, chain_id={self.chain_id}, txn_explorer_url={self.txn_explorer_url})"
