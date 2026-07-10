# AI Discord Bot

Небольшой мультимодальный Discord-бот на Python. Он читает сообщения, учитывает
контекст канала и отвечает в заданной персоне через OpenAI Responses API.

Бот умеет:

- отвечать на обычный текст, упоминания и Reply на свои сообщения;
- случайно выбирать часть сообщений или просматривать все сообщения;
- самостоятельно решать, уместно ли вступать в разговор;
- анализировать изображения;
- извлекать несколько кадров из загруженных GIF и GIF-ссылок Discord;
- извлекать несколько кадров из видео;
- хранить все настройки, персону и токены в одном локальном `config.toml`.

## Структура проекта

```text
AI-Discord-Bot/
|-- bot.py                  # Discord-события и выбор сообщений
|-- config.py               # чтение и проверка config.toml
|-- media.py                # изображения, GIF, видео и Discord embeds
|-- openai_service.py       # запросы к OpenAI Responses API
|-- config.example.toml     # безопасный пример конфигурации
|-- requirements.txt        # зависимости Python
|-- tests/                  # небольшие автоматические тесты
`-- README.md
```

`config.toml` содержит секреты и поэтому не попадает в Git. В репозиторий нужно
добавлять только `config.example.toml`.

## 1. Создание Discord-бота

1. Открой [Discord Developer Portal](https://discord.com/developers/applications).
2. Создай приложение, затем открой раздел **Bot** и создай бота.
3. Включи **MESSAGE CONTENT INTENT**.
4. Скопируй токен бота.
5. В **OAuth2 -> URL Generator** выбери scope `bot` и разрешения:
   `View Channels`, `Send Messages` и `Read Message History`.
6. Открой полученную ссылку и добавь бота на сервер.

## 2. Установка

Нужен Python 3.11 или новее.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.toml config.toml
```

### Linux или macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp config.example.toml config.toml
```

## 3. Конфигурация

Открой `config.toml` и сначала укажи два токена:

```toml
[discord]
token = "токен Discord-бота"

[openai]
api_key = "ключ OpenAI API"
model = "gpt-5.4-nano"
```

Для более качественных ответов и анализа изображений можно выбрать
`gpt-5.4-mini`. Для более дешёвых и быстрых ответов подходит
`gpt-5.4-nano`. Выбранная модель должна поддерживать image input.

Персона задаётся многострочным текстом прямо в том же файле:

```toml
[bot]
persona = """
Ты ироничный участник Discord-сервера.
Пиши коротко, естественно и не вмешивайся в законченные разговоры.
"""
```

### Настройки OpenAI

| Параметр | Что делает |
| --- | --- |
| `model` | Модель OpenAI для решений, текста и изображений. |
| `max_output_tokens` | Максимальный бюджет ответа. Если модель возвращает пустой текст, значение стоит увеличить. |
| `request_timeout_seconds` | Сколько секунд ждать ответ OpenAI. |

### Поведение бота

| Параметр | Что делает |
| --- | --- |
| `reply_to_mentions` | Всегда отвечать, когда бота упомянули. |
| `reply_to_replies` | Всегда отвечать на Reply к сообщению бота. |
| `read_all_messages` | Рассматривать каждое обычное текстовое сообщение. |
| `random_response_chance` | Вероятность выборки от `0.0` до `1.0`, если `read_all_messages = false`. Например, `0.15` означает примерно 15%. |
| `decision_filter_enabled` | Разрешить персоне после выборки решить, отвечать или промолчать. Упоминания и Reply обходят фильтр. |
| `context_messages` | Число прошлых сообщений из истории Discord. `0` полностью отключает контекст. |
| `max_discord_chars` | Размер одной части ответа. Длинный ответ автоматически делится. |
| `log_level` | Подробность логов: `DEBUG`, `INFO`, `WARNING` или `ERROR`. |

Если нужен бот, который видит весь чат, но вступает только по ситуации:

```toml
read_all_messages = true
decision_filter_enabled = true
```

Если нужен случайный ответ примерно на каждое десятое сообщение:

```toml
read_all_messages = false
random_response_chance = 0.10
decision_filter_enabled = true
```

### Медиа

| Параметр | Что делает |
| --- | --- |
| `analyze_images` | Анализировать изображения и image embeds. |
| `analyze_gifs` | Анализировать загруженные GIF и Discord GIF embeds. |
| `analyze_videos` | Анализировать несколько кадров видео. |
| `media_messages_are_candidates` | Сразу рассматривать сообщения с включённым типом медиа. При `false` действует обычная случайная выборка. |
| `max_download_mb` | Максимальный размер одного скачиваемого файла. |
| `max_media_per_message` | Максимальное число медиафайлов из одного сообщения. |
| `max_image_side` | Максимальная ширина или высота кадра перед отправкой в OpenAI. |
| `image_detail` | Детализация OpenAI: `low`, `high`, `auto` или `original`. |
| `gif_frames` | Сколько кадров равномерно взять из GIF. |
| `video_frames` | Сколько кадров взять из видео. |
| `video_sample_interval_seconds` | Интервал между кадрами видео и GIF-видео. |
| `download_timeout_seconds` | Таймаут скачивания Discord embeds. |

OpenAI принимает статические изображения и не принимает анимированный GIF как
анимацию. Поэтому бот сам скачивает GIF, выбирает несколько кадров по всей длине
и отправляет их модели по порядку. GIF-ссылки Tenor Discord часто представляет
как MP4; они разбираются тем же способом, что и видео. Это соответствует
[требованиям OpenAI к image input](https://developers.openai.com/api/docs/guides/images-vision#image-input-requirements).

Текстовые GPT-модели также не принимают видео напрямую, поэтому бот анализирует
только выбранные видеокадры, без звука. Для извлечения кадров используется
`imageio-ffmpeg`, который обычно устанавливает подходящий FFmpeg вместе с Python-
зависимостями.

## 4. Проверка и запуск

Проверить конфиг без подключения к Discord:

```powershell
.\.venv\Scripts\python.exe bot.py --check-config
```

Запустить тесты конфигурации, GIF, видео и разбиения длинных сообщений:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Запустить бота:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Другой конфиг можно передать явно:

```powershell
.\.venv\Scripts\python.exe bot.py --config config.dev.toml
```

## Контекст и память

У проекта нет базы данных и постоянной памяти. При каждом ответе бот читает
последние `context_messages` сообщений непосредственно из Discord. После
перезапуска он может снова увидеть ту же историю канала, но ничего отдельно не
сохраняет. Значение `context_messages = 0` отключает это поведение.

## Подготовка к GitHub

Перед первым commit проверь, что локальный конфиг игнорируется:

```powershell
git init
git check-ignore config.toml
git add .
git status
```

В выводе `git status` не должно быть `config.toml` и `.env`. Если секрет когда-то
уже попал в commit или публичный репозиторий, удаления файла недостаточно: токен
нужно отозвать и выпустить заново.

## Частые проблемы

**Бот онлайн, но не видит текст.** Проверь `MESSAGE CONTENT INTENT` в Discord
Developer Portal и перезапусти процесс.

**Бот долго печатает и не отправляет ответ.** Посмотри ошибку в консоли. Частые
причины: неверный API-ключ, отсутствующий баланс, недоступная модель, таймаут или
слишком маленький `max_output_tokens`.

**Бот не понимает GIF-ссылку или видео.** Переустанови зависимости командой
`python -m pip install -r requirements.txt`. В логах с уровнем `INFO` или
`DEBUG` будет указано, удалось ли извлечь кадры.
