# AI Discord Bot

A small multimodal Discord bot written in Python. It reads messages, uses recent
channel context, and replies in a configurable persona through the OpenAI
Responses API.

The bot can:

- reply to regular messages, mentions, and replies to its own messages;
- randomly select some messages or consider every message;
- decide whether joining a conversation is appropriate;
- analyze images;
- extract multiple frames from uploaded GIFs and Discord GIF links;
- extract multiple frames from videos;
- keep all settings, the persona, and API tokens in one local `config.toml` file.

## Project Structure

```text
AI-Discord-Bot/
|-- bot.py                  # Discord events and message selection
|-- config.py               # config.toml loading and validation
|-- media.py                # image, GIF, video, and Discord embed processing
|-- openai_service.py       # OpenAI Responses API requests
|-- config.example.toml     # safe configuration template
|-- requirements.txt        # Python dependencies
|-- tests/                  # small automated test suite
`-- README.md
```

`config.toml` contains secrets and is ignored by Git. Only
`config.example.toml` should be committed to the repository.

## 1. Create a Discord Bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create an application, then open the **Bot** section and add a bot.
3. Enable **MESSAGE CONTENT INTENT**.
4. Copy the bot token.
5. In **OAuth2 -> URL Generator**, select the `bot` scope and these permissions:
   `View Channels`, `Send Messages`, and `Read Message History`.
6. Open the generated URL and add the bot to your server.

## 2. Installation

Python 3.11 or newer is required.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.toml config.toml
```

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp config.example.toml config.toml
```

## 3. Configuration

Open `config.toml` and set the two required tokens first:

```toml
[discord]
token = "your Discord bot token"

[openai]
api_key = "your OpenAI API key"
model = "gpt-5.4-nano"
```

Choose `gpt-5.4-mini` for higher-quality responses and image analysis, or
`gpt-5.4-nano` for lower-cost and faster responses. The selected model must
support image input.

The persona is a multiline string in the same file:

```toml
[bot]
persona = """
You are a witty Discord server participant.
Write naturally and briefly. Do not interrupt conversations that have ended.
"""
```

### OpenAI Settings

| Setting | Description |
| --- | --- |
| `model` | OpenAI model used for decisions, text, and image analysis. |
| `max_output_tokens` | Maximum response budget. Increase it if the model returns empty text. |
| `request_timeout_seconds` | How long to wait for an OpenAI response. |

### Bot Behavior

| Setting | Description |
| --- | --- |
| `reply_to_mentions` | Always reply when the bot is mentioned. |
| `reply_to_replies` | Always reply when someone replies to a bot message. |
| `read_all_messages` | Consider every regular text message. |
| `random_response_chance` | Selection probability from `0.0` to `1.0` when `read_all_messages = false`. For example, `0.15` means roughly 15%. |
| `decision_filter_enabled` | Lets the persona decide whether to reply after selection. Mentions and replies bypass this filter. |
| `context_messages` | Number of previous messages read from Discord history. `0` disables context completely. |
| `max_discord_chars` | Maximum size of one reply chunk. Long responses are split automatically. |
| `log_level` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |

To make the bot see every message but join only when appropriate:

```toml
read_all_messages = true
decision_filter_enabled = true
```

To make the bot reply to roughly one in ten messages:

```toml
read_all_messages = false
random_response_chance = 0.10
decision_filter_enabled = true
```

### Media

| Setting | Description |
| --- | --- |
| `analyze_images` | Analyze uploaded images and image embeds. |
| `analyze_gifs` | Analyze uploaded GIFs and Discord GIF embeds. |
| `analyze_videos` | Analyze selected video frames. |
| `media_messages_are_candidates` | Immediately consider messages containing an enabled media type. When `false`, normal random selection applies. |
| `max_download_mb` | Maximum size of one downloaded file. |
| `max_media_per_message` | Maximum number of media files processed from one message. |
| `max_image_side` | Maximum frame width or height before it is sent to OpenAI. |
| `image_detail` | OpenAI image detail level: `low`, `high`, `auto`, or `original`. |
| `gif_frames` | Number of evenly sampled GIF frames. |
| `video_frames` | Number of video frames to extract. |
| `video_sample_interval_seconds` | Interval between extracted video and GIF-video frames. |
| `download_timeout_seconds` | Download timeout for Discord embeds. |

OpenAI accepts static images, but it does not treat an animated GIF as an
animation. The bot downloads each GIF, samples several frames from across its
duration, and sends those frames to the model in chronological order. Discord
often exposes Tenor GIF links as MP4 files, which are processed like videos. This
follows the [OpenAI image input requirements](https://developers.openai.com/api/docs/guides/images-vision#image-input-requirements).

Text GPT models also do not accept video directly, so the bot only analyzes the
selected video frames and does not analyze audio. Frame extraction uses
`imageio-ffmpeg`, which usually installs a suitable FFmpeg binary with the Python
dependencies.

## 4. Validate and Run

Validate the configuration without connecting to Discord:

```powershell
.\.venv\Scripts\python.exe bot.py --check-config
```

Run the configuration, GIF, video, and long-message tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Start the bot:

```powershell
.\.venv\Scripts\python.exe bot.py
```

You can explicitly provide another configuration file:

```powershell
.\.venv\Scripts\python.exe bot.py --config config.dev.toml
```

## Context and Memory

The project has no database or persistent memory. Before every reply, the bot
reads the last `context_messages` entries directly from Discord. After a restart,
it can read the same channel history again, but it does not store anything on its
own. Set `context_messages = 0` to disable this behavior.

## Preparing for GitHub

Before the first commit, make sure the local configuration is ignored:

```powershell
git init
git check-ignore config.toml
git add .
git status
```

`config.toml` and `.env` must not appear in `git status`. If a secret was ever
committed or published, removing the file is not enough: revoke the token and
generate a new one.

## Troubleshooting

**The bot is online but does not see text messages.** Check **MESSAGE CONTENT
INTENT** in the Discord Developer Portal, then restart the process.

**The bot keeps typing but does not send a response.** Check the console error.
Common causes are an invalid API key, no available API balance, an unavailable
model, a timeout, or an overly small `max_output_tokens` value.

**The bot does not understand a GIF link or video.** Reinstall dependencies with
`python -m pip install -r requirements.txt`. The `INFO` or `DEBUG` logs will show
whether frame extraction succeeded.
