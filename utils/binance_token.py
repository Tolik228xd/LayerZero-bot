import aiohttp

async def get_token_price(token_symbol: str) -> float:
    token_symbol = token_symbol.upper()  # Приводим к верхнему регистру

    # Список стейблкоинов
    stable_tokens = ["USDC", "USDT", "DAI", "USDC.E"]  # Используем верхний регистр для консистентности
    if token_symbol in stable_tokens:
        return 1.0

    # Если токен не в списке стейблкоинов, пробуем получить цену через Binance API
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.binance.com/api/v3/ticker/price?symbol={token_symbol}USDT') as response:
            data = await response.json()
            if 'price' in data:
                return float(data['price'])

        async with session.get(f'https://api.binance.com/api/v3/ticker/price?symbol={token_symbol}USDC') as response:
            data = await response.json()
            if 'price' in data:
                return float(data['price'])

    raise ValueError(f"Не удалось получить цену для токена {token_symbol}")