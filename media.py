from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import shutil
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
import discord
from PIL import Image, ImageOps, UnidentifiedImageError

from config import MediaSettings


logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
GIF_EXTENSIONS = {".gif"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}


class MediaError(RuntimeError):
    """Raised when a media item cannot be downloaded or decoded."""


@dataclass(frozen=True)
class MediaSource:
    kind: str
    label: str
    attachment: discord.Attachment | None = None
    url: str | None = None
    fallback_url: str | None = None


@dataclass(frozen=True)
class PreparedMedia:
    image_parts: list[dict[str, Any]]
    notes: list[str]


def attachment_content_type(attachment: discord.Attachment) -> str:
    if attachment.content_type:
        return attachment.content_type.split(";", maxsplit=1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(attachment.filename)
    return guessed or "application/octet-stream"


def _kind_from_attachment(
    attachment: discord.Attachment, settings: MediaSettings
) -> str | None:
    content_type = attachment_content_type(attachment)
    extension = Path(attachment.filename).suffix.lower()

    if (content_type == "image/gif" or extension in GIF_EXTENSIONS) and settings.analyze_gifs:
        return "gif"
    if (
        content_type.startswith("image/") or extension in IMAGE_EXTENSIONS
    ) and settings.analyze_images:
        return "image"
    if (
        content_type.startswith("video/") or extension in VIDEO_EXTENSIONS
    ) and settings.analyze_videos:
        return "video"
    return None


def _proxy_url(proxy: Any) -> str | None:
    value = getattr(proxy, "url", None)
    return str(value) if value else None


def collect_media_sources(
    message: discord.Message, settings: MediaSettings
) -> list[MediaSource]:
    sources: list[MediaSource] = []
    used_urls: set[str] = set()

    for attachment in message.attachments:
        kind = _kind_from_attachment(attachment, settings)
        if kind is not None:
            sources.append(
                MediaSource(kind=kind, label=attachment.filename, attachment=attachment)
            )

    for index, embed in enumerate(message.embeds, start=1):
        if embed.type == "gifv" and settings.analyze_gifs:
            video_url = _proxy_url(embed.video)
            fallback_url = _proxy_url(embed.image) or _proxy_url(embed.thumbnail)
            if video_url and video_url not in used_urls:
                used_urls.add(video_url)
                sources.append(
                    MediaSource(
                        kind="gif_embed",
                        label=f"embedded GIF #{index}",
                        url=video_url,
                        fallback_url=fallback_url,
                    )
                )
                continue

        video_url = _proxy_url(embed.video)
        if video_url and settings.analyze_videos and video_url not in used_urls:
            used_urls.add(video_url)
            sources.append(
                MediaSource(kind="video", label=f"embedded video #{index}", url=video_url)
            )
            continue

        image_url = _proxy_url(embed.image)
        if image_url and settings.analyze_images and image_url not in used_urls:
            used_urls.add(image_url)
            sources.append(
                MediaSource(kind="image", label=f"embedded image #{index}", url=image_url)
            )

    return sources[: settings.max_media_per_message]


def message_has_enabled_media(message: discord.Message, settings: MediaSettings) -> bool:
    return bool(collect_media_sources(message, settings))


def _data_url(data: bytes, content_type: str = "image/jpeg") -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _frame_to_jpeg(frame: Image.Image, max_side: int) -> str:
    frame = frame.copy()
    frame.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    if frame.mode in {"RGBA", "LA"} or "transparency" in frame.info:
        rgba = frame.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        rgb = background.convert("RGB")
    else:
        rgb = frame.convert("RGB")

    output = BytesIO()
    rgb.save(output, format="JPEG", quality=86, optimize=True)
    return _data_url(output.getvalue())


def image_to_data_url(data: bytes, max_side: int) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            image.seek(0)
            frame = ImageOps.exif_transpose(image)
            return _frame_to_jpeg(frame, max_side)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError(f"unsupported or damaged image: {exc}") from exc


def _sample_indexes(total_frames: int, requested_frames: int) -> list[int]:
    count = min(total_frames, requested_frames)
    if count <= 1:
        return [0]
    return [round(index * (total_frames - 1) / (count - 1)) for index in range(count)]


def gif_to_data_urls(data: bytes, frame_count: int, max_side: int) -> list[str]:
    try:
        with Image.open(BytesIO(data)) as image:
            total_frames = getattr(image, "n_frames", 1)
            frames: list[str] = []
            for frame_index in _sample_indexes(total_frames, frame_count):
                image.seek(frame_index)
                frames.append(_frame_to_jpeg(image.convert("RGBA"), max_side))
            return frames
    except (UnidentifiedImageError, EOFError, OSError) as exc:
        raise MediaError(f"unsupported or damaged GIF: {exc}") from exc


def _ffmpeg_executable() -> str | None:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None


async def video_to_data_urls(
    data: bytes,
    filename: str,
    frame_count: int,
    sample_interval_seconds: float,
    max_side: int,
) -> list[str]:
    ffmpeg = _ffmpeg_executable()
    if ffmpeg is None:
        raise MediaError("FFmpeg is not available")

    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        suffix = ".mp4"

    with tempfile.TemporaryDirectory(prefix="discord-ai-media-") as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / f"input{suffix}"
        output_pattern = temp_path / "frame-%03d.jpg"
        input_path.write_bytes(data)

        process = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-vf",
            f"fps=1/{sample_interval_seconds}",
            "-frames:v",
            str(frame_count),
            "-q:v",
            "3",
            str(output_pattern),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        frame_paths = sorted(temp_path.glob("frame-*.jpg"))
        if process.returncode != 0 and not frame_paths:
            error = stderr.decode("utf-8", errors="replace").strip()
            raise MediaError(f"FFmpeg could not decode the video: {error[:180]}")
        if not frame_paths:
            raise MediaError("FFmpeg did not extract any frames")

        return [
            image_to_data_url(frame_path.read_bytes(), max_side)
            for frame_path in frame_paths
        ]


async def _download_url(
    session: aiohttp.ClientSession, url: str, max_bytes: int
) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise MediaError("unsupported media URL")

    try:
        async with session.get(url, allow_redirects=True) as response:
            response.raise_for_status()
            content_length = response.content_length
            if content_length is not None and content_length > max_bytes:
                raise MediaError("file is larger than the configured download limit")

            data = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise MediaError("file is larger than the configured download limit")

            content_type = response.headers.get("Content-Type", "application/octet-stream")
            return bytes(data), content_type.split(";", maxsplit=1)[0].lower()
    except aiohttp.ClientError as exc:
        raise MediaError(f"download failed: {exc}") from exc


async def _read_source(
    source: MediaSource,
    session: aiohttp.ClientSession,
    max_bytes: int,
) -> tuple[bytes, str]:
    if source.attachment is not None:
        if source.attachment.size > max_bytes:
            raise MediaError("file is larger than the configured download limit")
        try:
            return await source.attachment.read(), attachment_content_type(source.attachment)
        except discord.HTTPException as exc:
            raise MediaError(f"Discord download failed: {exc}") from exc

    if source.url is None:
        raise MediaError("media source has no URL")
    return await _download_url(session, source.url, max_bytes)


def _input_image(url: str, detail: str) -> dict[str, Any]:
    return {"type": "input_image", "image_url": url, "detail": detail}


async def prepare_media(
    message: discord.Message, settings: MediaSettings
) -> PreparedMedia:
    sources = collect_media_sources(message, settings)
    if not sources:
        return PreparedMedia(image_parts=[], notes=[])

    max_bytes = settings.max_download_mb * 1024 * 1024
    timeout = aiohttp.ClientTimeout(total=settings.download_timeout_seconds)
    image_parts: list[dict[str, Any]] = []
    notes: list[str] = []

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for source in sources:
            try:
                data, content_type = await _read_source(source, session, max_bytes)

                if source.kind == "image":
                    urls = [
                        await asyncio.to_thread(
                            image_to_data_url, data, settings.max_image_side
                        )
                    ]
                    notes.append(f"{source.label}: image analyzed")
                elif source.kind == "gif":
                    urls = await asyncio.to_thread(
                        gif_to_data_urls,
                        data,
                        settings.gif_frames,
                        settings.max_image_side,
                    )
                    notes.append(
                        f"{source.label}: {len(urls)} GIF frames analyzed in chronological order"
                    )
                elif source.kind == "gif_embed" and content_type == "image/gif":
                    urls = await asyncio.to_thread(
                        gif_to_data_urls,
                        data,
                        settings.gif_frames,
                        settings.max_image_side,
                    )
                    notes.append(
                        f"{source.label}: {len(urls)} GIF frames analyzed in chronological order"
                    )
                else:
                    frame_limit = (
                        settings.gif_frames
                        if source.kind == "gif_embed"
                        else settings.video_frames
                    )
                    urls = await video_to_data_urls(
                        data=data,
                        filename=source.label,
                        frame_count=frame_limit,
                        sample_interval_seconds=settings.video_sample_interval_seconds,
                        max_side=settings.max_image_side,
                    )
                    media_name = "GIF animation" if source.kind == "gif_embed" else "video"
                    notes.append(
                        f"{source.label}: {len(urls)} {media_name} frames analyzed "
                        f"every {settings.video_sample_interval_seconds:g} seconds; audio was not analyzed"
                    )

                image_parts.extend(
                    _input_image(url, settings.image_detail) for url in urls
                )
            except (MediaError, asyncio.TimeoutError) as exc:
                logger.warning("Could not process %s: %s", source.label, exc)

                if source.kind == "gif_embed" and source.fallback_url:
                    try:
                        fallback_data, _ = await _download_url(
                            session, source.fallback_url, max_bytes
                        )
                        fallback_url = await asyncio.to_thread(
                            image_to_data_url, fallback_data, settings.max_image_side
                        )
                        image_parts.append(
                            _input_image(fallback_url, settings.image_detail)
                        )
                        notes.append(
                            f"{source.label}: animation decoding failed; preview image analyzed"
                        )
                        continue
                    except (MediaError, asyncio.TimeoutError) as fallback_exc:
                        logger.warning(
                            "Could not process fallback for %s: %s",
                            source.label,
                            fallback_exc,
                        )

                notes.append(f"{source.label}: skipped ({exc})")

    return PreparedMedia(image_parts=image_parts, notes=notes)
