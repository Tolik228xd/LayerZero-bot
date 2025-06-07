
import logging
from eth_typing import ChecksumAddress

logger = logging.getLogger(__name__)

async def check_allowance_or_approve(
    account_client,
    token_amount,
    allowance_factor: float,
    spender_address: ChecksumAddress,
):

    client = account_client.client
    account_address = account_client.address
    network = client.network

    token_allowance = await account_client.get_token_allowance(
        token=token_amount.token,
        spender_address=spender_address,
    )

    required_allowance = int(int(token_amount.Wei) * allowance_factor)

    if token_allowance < required_allowance:
        txn_hash = await account_client.approve_token_spend(
            token=token_amount.token,
            amount=required_allowance,
            spender_address=spender_address,
        )

        client.wait_for_transaction_receipt(txn_hash)
    else:
        pass
