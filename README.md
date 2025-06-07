### Follow: https://t.me/cryptofizic

#Quick start
1. Создайте виртуальное окружение:
```
python -m venv venv
```
2. Заполните accounts.txt (приватники от метамаска,) Пример:(address,privatekey)
2. Что бы установить зависимости:
```
pip install -r requirements.txt
```

2. Что бы запустить скрипт:
```
python main.py

#Доступные сети
bsc,polygon,optimism,arbitrum_one,eth,abstract,linea

# режимы
1 - режим проверки баланса,скрипт проверяет все балансы и токены которые вы укажите в config_bridge.json
2 - обычные свапы,настройки для них указывать в config_bridge.json
3 - круговые свапы - скрипт прогонит по кругу между всеми сетями указанные токены и в итоге соберет все монеты переведет их в указанную и в указанную сеть

```
#Круговой прогон - что бы сделать круговой прогон в конфиг файле укажите все сети и все токены которые вы хотите прогонять
После чего скрипт предложит выбрать конечную сеть и токен который будет прогоняться

Настройки в config_bridge.json:
Доступные сети: ethereum,arbitrum_one,optimism,linea,base
1. sourceNetworks - с какой сети бридж(можно указать несколько сетей,выбирает на каждый аккаунт случайную)
2. destinationNetworks - в какую бридж(можно так же как и в sourceNetworks указать несколько сетей)
3. fromTokens - токены для бриджа(доступны usdt,eth,usdc.e)
4. toTokens - токены для бриджа(доступны usdt,eth,usdc.e)
5. percentageRange - рандомный процент от токена для свапа
6. transactionCount - Общее количество транзакций для всех аккаунтов
7. delayBetweenAccounts - Задержка между аккаунтами в секундах
8. transactionDelay - Задержка между транзакциями в секундах
9. threads - количество потоков
10. bridgeMode - режим свапа(fast - быстрый, slow - медленный) - fast режим отображаеться в сканере l0, укажите процент с каким процентом транзакций будет использоваться fast режим или slow
11. gasPriceLimits - лимиты газа для каждой сети  
12. randomBridge - вы указываете процент с кототорым транзакция пройдет не через бридж старгейта,а через случайный роут



#ВЫВОД НА БИРЖУ

   Заполните файл exchange_wallet.txt кошельками бирж,каждый с нового ряда
  "withdrawNetwork": "arbitrum_one",      // Сеть, из которой выводим
  "withdrawToken": "ETH",                // Токен для вывода
  "withdrawMode": "percentage",          // "percentage" или "fixed"
  "withdrawPercentage": [90, 100],       // Процент для вывода (если mode = percentage)
  "withdrawAmount": 0.01


# ДЕПОЗИТ С БИРЖИ

Функция депозита позволяет выводить средства с бирж (Binance, OKX, Bybit, Gate, KuCoin, MEXC, Huobi) на кошельки.

В файле api_keys.py укажите API ключи для выбранной биржи:

class API:
    binance_apikey = "your_api_key"
    binance_apisecret = "your_api_secret"
    okx_apikey = ""
    okx_apisecret = ""
    okx_passphrase = ""



### Настройка
1. **Настройте `data/config_bridge.json`**:
   ```json
   {
     "depositCex": "binance",                    // Биржа: binance, okx, bybit, gate, kucoin, mexc, huobi
     "depositToken": "USDT",                    // Токен: USDT, ETH, BTC и т.д.
     "depositNetwork": "Arbitrum One",          // Сеть: Arbitrum One, ERC20, BSC и т.д.
     "depositAmountRange": [1.5, 2.5],          // Диапазон суммы вывода (мин, макс)
     "depositDecimalPlaces": 2,                 // Знаков после запятой (2 для 1.50 USDT)
     "depositDelayRange": [35, 85],             // Задержка между выводами, сек (мин, макс)
     "shuffleWallets": "no",                    // Перемешивать кошельки: yes/no
     "useProxy": true                           // Прокси: true/false
   }



Настройки в config_filter.json:
Data_from - с какой даты фильтровать транзакции
Data_to - по какую дату фильтровать транзакции


Настройки прокси в proxies.txt:
Софт поддерживает http и socks5,указывать в таком формате
http://login:pass@ip:port
Что бы включить или выключить прокси перейдите в файл config_bridge.json и там "useProxy": true ибо ставьте false что бы выключить




Как создать виртуальное окружение
Виртуальное окружение позволяет изолировать зависимости проекта, чтобы избежать конфликтов между различными версиями библиотек в разных проектах.

Убедитесь, что у вас установлен Python. Проверить это можно с помощью команды python --version или python3 --version. Если Python не установлен, скачайте и установите его с официального сайта: https://www.python.org/.

Для создания виртуального окружения выполните следующую команду в терминале внутри корневой папки проекта:

На Windows: python -m venv venv
На macOS / Linux: python3 -m venv venv
Эта команда создаст папку venv в вашем проекте.

Далее активируйте виртуальное окружение:

На Windows: venv\Scripts\activate
На macOS / Linux: source venv/bin/activate
После активации в терминале вы увидите название окружения перед приглашением, например: (venv) user@machine:~$.

Если у проекта есть файл requirements.txt, установите зависимости с помощью команды:
pip install -r requirements.txt.

Когда закончите работу, деактивируйте виртуальное окружение командой deactivate.

### Donate :)

ERC-20 - `0xF807A0957fe63753b0CbD4848cA3341E52094051`



