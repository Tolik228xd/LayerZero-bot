# i10s/entities/commands/swap.py

class BaseSwapCommand:
    def __init__(self, client, account_client, settings, from_token_amount,
                 from_token, to_token, is_from_token_native=False):
        self._client = client
        self._account_client = account_client
        self._settings = settings
        self._from_token_amount = from_token_amount
        self._from_token = from_token
        self._to_token = to_token
        self._is_from_token_native = is_from_token_native

    async def _swap(self):
        raise NotImplementedError("Метод _swap должен быть переопределён в наследниках.")
