import asyncio
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

from media import gif_to_data_urls, video_to_data_urls


class GifTests(unittest.TestCase):
    def test_extracts_frames_from_the_whole_animation(self) -> None:
        colors = ["red", "green", "blue", "yellow", "black"]
        frames = [Image.new("RGB", (32, 32), color) for color in colors]
        data = BytesIO()
        frames[0].save(
            data,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )

        result = gif_to_data_urls(data.getvalue(), frame_count=3, max_side=64)

        self.assertEqual(len(result), 3)
        self.assertTrue(all(item.startswith("data:image/jpeg;base64,") for item in result))


class VideoTests(unittest.TestCase):
    def test_extracts_configured_number_of_video_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=64x64:rate=10",
                    "-t",
                    "2",
                    "-c:v",
                    "mpeg4",
                    "-y",
                    str(video_path),
                ],
                check=True,
            )

            result = asyncio.run(
                video_to_data_urls(
                    video_path.read_bytes(),
                    filename=video_path.name,
                    frame_count=3,
                    sample_interval_seconds=0.5,
                    max_side=64,
                )
            )

        self.assertEqual(len(result), 3)
        self.assertTrue(all(item.startswith("data:image/jpeg;base64,") for item in result))


if __name__ == "__main__":
    unittest.main()
