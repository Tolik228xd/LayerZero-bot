
from eth_account import Account
from eth_account.signers.local import LocalAccount
from solders.keypair import Keypair
from mnemonic import Mnemonic
from hdwallets import BIP32


def evm_check_private_key(account_data: str) -> tuple[bool, LocalAccount | None]:
    try:
        acc = Account.from_key(account_data)
        return True, acc
    except:
        return False, None


def evm_check_mnemonic(account_data: str) -> tuple[bool, LocalAccount | None]:
    try:
        acc = Account.from_mnemonic(account_data)
        return True, acc
    except:
        return False, None


def solana_check_private_key(account_data: str) -> tuple[bool, Keypair | None]:
    try:
        kp = Keypair.from_base58_string(account_data.strip())
        return True, kp
    except:
        return False, None


def solana_check_mnemonic(account_data: str) -> tuple[bool, Keypair | None]:
    try:
        seed = Mnemonic('english').to_seed(account_data)
        root = BIP32.from_seed(seed)
        path = "m/44'/501'/0'/0'"
        derived = root.get_privkey_from_path(path)
        kp = Keypair.from_bytes(derived)
        return True, kp
    except:
        return False, None


def get_account(account_data: str) -> tuple[int, LocalAccount | Keypair | None]:

    is_evm_mnemonic, evm_acc = evm_check_mnemonic(account_data)
    if is_evm_mnemonic:
        return (1, evm_acc)

    is_evm_pkey, evm_acc2 = evm_check_private_key(account_data)
    if is_evm_pkey:
        return (1, evm_acc2)

    is_sol_pkey, sol_kp = solana_check_private_key(account_data)
    if is_sol_pkey:
        return (2, sol_kp)

    is_sol_mnemonic, sol_kp2 = solana_check_mnemonic(account_data)
    if is_sol_mnemonic:
        return (2, sol_kp2)

    return (0, None)
