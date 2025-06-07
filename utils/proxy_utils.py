# proxy_utils.py
from random import choice

proxy_list: list[str] = []

try:
    with open('data/proxies.txt', 'r', encoding='utf-8-sig') as f:
        for row in f:
            line = row.strip()
            if not line:
                continue
            # Не добавляем префикс http://, если указан socks5:// или другой протокол
            if '://' not in line:
                line = f'http://{line}'
            proxy_list.append(line)
except FileNotFoundError:
    print("Файл data/proxies.txt не найден, прокси не будут использоваться.")

def get_proxy() -> str | None:
    if proxy_list:
        return choice(proxy_list)
    return None

def get_proxy_dict() -> dict | None:
    proxy = get_proxy()
    if proxy:
        return {"http": proxy, "https": proxy}
    return None