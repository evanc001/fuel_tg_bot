# fuel_tg_bot

Telegram-бот для генерации только DOCX-допсоглашений из шаблонов `docxtpl`.

## 1) Как создать токен бота и не светить его
1. В Telegram откройте `@BotFather`.
2. Выполните `/newbot` и получите токен.
3. Никогда не сохраняйте токен в коде, только в ENV (`BOT_TOKEN`).

## 2) Как подготовить `clients.enc`
1. Локально положите файл `data/clients.json` (он не должен попадать в git).
2. Запустите:
   ```powershell
   py -3 scripts/encrypt_clients.py --in data/clients.json --out data/clients.enc
   ```
3. Если `CLIENTS_KEY` не задан, скрипт выведет новый ключ в консоль.
4. Опционально можно сохранить ключ в файл:
   ```powershell
   py -3 scripts/encrypt_clients.py --in data/clients.json --out data/clients.enc --key-out data/clients.key
   ```
5. Добавьте в Render Secrets:
   - либо `CLIENTS_KEY` (сам ключ),
   - либо `CLIENTS_KEY_FILE` (путь к файлу с ключом).
6. Удалите/не коммитьте `data/clients.json` и проверьте, что он в `.gitignore`.

## 2.1) Альтернатива без `clients.enc` на сервере (рекомендуется для Render)
1. Сформируйте base64 из локального `data/clients.json`:
   ```powershell
   py -3 -c "import base64, pathlib; print(base64.urlsafe_b64encode(pathlib.Path('data/clients.json').read_text(encoding='utf-8-sig').encode('utf-8')).decode('utf-8'))"
   ```
2. Скопируйте строку и добавьте в Render ENV:
   - `CLIENTS_JSON_B64` = `<скопированная строка>`
3. В этом режиме `CLIENTS_KEY`/`CLIENTS_KEY_FILE` не обязательны.

## 3) Локальный запуск
```powershell
pip install -r requirements.txt
set BOT_TOKEN=... 
set CLIENTS_KEY=... 
python bot.py
```
или
```powershell
set BOT_TOKEN=...
set CLIENTS_KEY_FILE=data/clients.key
python bot.py
```

## 4) Деплой на Render
1. Подключите GitHub-репозиторий к Render.
2. Build Command:
   ```
   pip install -r requirements.txt
   ```
3. Start Command:
   ```
   python bot.py
   ```
4. Добавьте ENV-переменные:
   - `BOT_TOKEN`
   - один из вариантов:
     - `CLIENTS_JSON_B64` (рекомендуется),
     - `CLIENTS_KEY` (для `clients.enc`),
     - `CLIENTS_KEY_FILE` (для `clients.enc` через файл).

Важно: `data/clients.enc` не является ключом. Ключ короткий (обычно 44 символа, заканчивается `=`).

## 5) Как обновлять справочники
1. `data/products.json`, `data/locations.json`, `data/aliases.json`:
   - редактируете -> `git push` -> Render auto deploy.
2. Клиенты:
   - обновляете локальный `data/clients.json`;
   - снова шифруете `clients.enc`;
   - обновляете `data/clients.enc` в репозитории;
   - `git push`.
