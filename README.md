# GFP Parts Scraper

Збирає каталог запчастин → зберігає в CSV + Google Sheets.

**Колонки виводу:** `path | year | model | assembly | ref | oem | description`


### 1. Встановити Python

Завантажити з https://python.org/downloads — під час встановлення поставити галочку **"Add Python to PATH"**.

```
python --version
```

### 2. Скопіювати файли проекту

Розмістити папку проекту:
```
C:\scraper\
```

### 3. Встановити залежності

```
cd C:\scraper
pip install playwright gspread google-auth python-dotenv
playwright install chromium
```

### 4. Налаштувати Google Sheets

**4.1 Створити Google Cloud проект**
1. Відкрити https://console.cloud.google.com → **New Project**
2. Увімкнути API: **Google Sheets API** + **Google Drive API**
3. **IAM & Admin → Service Accounts → Create Service Account** → завантажити JSON-ключ

**4.2 Додати ключ у проект**
```
C:\scraper\credentials\service_account.json
```

**4.3 Створити Google таблицю**
1. Відкрити https://sheets.google.com → створити порожню таблицю, назвати `GFP_Parts_Scrape`
2. Натиснути **Share** → вставити email сервісного акаунту з JSON-файлу → роль **Editor**
3. Скопіювати ID таблиці з URL:
   ```
   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
   ```

**4.4 файл `.env`**
```
GOOGLE_SA_PATH=credentials/service_account.json
GOOGLE_SPREADSHEET_ID=SPREADSHEET_ID
```

### 5. Запустити

```
cd C:\scraper
python scraper.py
```

Очікуваний вивід:
```
Run started: 2026-06-12 10:00:00
Year 2024 Models: 2 models
Year 2025 Models: 2 models
...
DONE  —  duration: 5m 10s
Models: 4  Assemblies: 46  Parts scraped: 318
CSV:    output/parts.csv  |  added: 318  updated: 0  total: 318
Sheets: added: 318  updated: 0
```

При повторних запусках: `added: 0` — дублів не буде.

---

## Автозапуск через Windows Task Scheduler

### Крок 1 — Відкрити планувальник задач

`Win + R` → ввести `taskschd.msc` → Enter

### Крок 2 — Створити задачу

На панелі праворуч → **Create Task** (не Basic Task)

**Вкладка General:**
- Name: `GFP Parts Scraper`
- Поставити галочку: **Run whether user is logged on or not**
- Поставити галочку: **Run with highest privileges**

**Вкладка Triggers → New:**
- Begin the task: **On a schedule**
- Settings: **Weekly** → вибрати день
- Start time: `08:00:00`
- Галочка: **Enabled**

**Вкладка Actions → New:**
- Action: **Start a program**
- Program/script:
  ```
  C:\Python310\python.exe
  ```
  *(шлях перевірити командою `where python`)*
- Add arguments:
  ```
  scraper.py
  ```
- Start in:
  ```
  C:\scraper
  ```

**Вкладка Settings:**
- Галочка: **If the task fails, restart every** `10 minutes`, up to `3 times`
- Галочка: **Stop the task if it runs longer than** `30 minutes`

### Крок 3 — Зберегти

OK → ввести пароль Windows-акаунту → OK

### Крок 4 — Перевірити

Правий клік на задачі → **Run** → переконатись що лог з'явився в `C:\scraper\logs\`

---

## Структура файлів

```
C:\scraper\
  scraper.py                  # головний скрипт
  sheets.py                   # модуль Google Sheets
  .env                        # конфіг з ключами 
  credentials\
    service_account.json      # ключ сервісного акаунту
  output\
    parts.csv                 # зібрані дані (оновлюється при кожному запуску)
  logs\
    scrape_YYYYMMDD.log       # щоденний лог
```

---

## Логіка upsert (без дублів)

Кожен запуск зливає нові дані з існуючими в CSV та Google Sheets.

Унікальний ключ: `oem | ref | path`

| Ситуація | Результат |
|---       |        ---|
| Нова запчастина, якої раніше не було | Додається |
| Та сама запчастина, дані не змінились | Пропускається |
| Та сама запчастина, опис змінився | Оновлюється |
| Повторний запуск з тими самими даними | `added: 0, updated: 0` |

---

## Вирішення типових проблем

**`ModuleNotFoundError: No module named 'playwright'`**
```
pip install playwright
playwright install chromium
```

**`APIError: [403] The caller does not have permission`**
→ Перевірити що таблиця розшарена з email сервісного акаунту з файлу `credentials/service_account.json`

**`FileNotFoundError: credentials/service_account.json`**
→ Перевірити `GOOGLE_SA_PATH` у файлі `.env` та наявність самого файлу

**Скрапер отримав 0 assemblies для моделі**
→ Сайт відповідав повільно; запустити повторно — upsert допише відсутні рядки автоматично

**Task Scheduler запускається але лог не з'являється**
→ Перевірити поле **Start in** в налаштуваннях задачі — має вказувати на папку проекту
