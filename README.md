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
   - `CLIENTS_KEY` (или `CLIENTS_KEY_FILE`)

Важно: `data/clients.enc` не является ключом. Ключ короткий (обычно 44 символа, заканчивается `=`).

## 5) Как обновлять справочники
1. `data/products.json`, `data/locations.json`, `data/aliases.json`:
   - редактируете -> `git push` -> Render auto deploy.
2. Клиенты:
   - обновляете локальный `data/clients.json`;
   - снова шифруете `clients.enc`;
   - обновляете `data/clients.enc` в репозитории;
   - `git push`.
