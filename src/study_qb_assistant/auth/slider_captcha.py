"""滑动拼图验证码服务。"""

from __future__ import annotations

import base64
import io
import secrets
import time
import uuid
from threading import Lock
from typing import Any

from PIL import Image, ImageDraw


class SliderCaptchaService:
    """提供纯内存、免存储依赖的轻量滑动拼图生成与校验。"""

    def __init__(self, tolerance: int = 12, expiry_seconds: int = 300) -> None:
        self._tolerance = tolerance
        self._expiry_seconds = expiry_seconds
        self._lock = Lock()
        self._challenges: dict[str, dict[str, Any]] = {}
        self._verified_tokens: dict[str, tuple[float, str]] = {}

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired_challenges = [
            cid for cid, item in self._challenges.items() if now - item["created_at"] > self._expiry_seconds
        ]
        for cid in expired_challenges:
            self._challenges.pop(cid, None)

        expired_tokens = [
            token
            for token, (created_at, _client_ip) in self._verified_tokens.items()
            if now - created_at > self._expiry_seconds
        ]
        for tok in expired_tokens:
            self._verified_tokens.pop(tok, None)

    def create_challenge(self, *, client_ip: str = "") -> dict[str, Any]:
        with self._lock:
            self._cleanup_expired()
            width, height = 300, 160
            puzzle_w, puzzle_h = 48, 48
            random_source = secrets.SystemRandom()

            bg_color = (
                random_source.randint(180, 240),
                random_source.randint(180, 240),
                random_source.randint(180, 240),
            )
            bg = Image.new("RGB", (width, height), color=bg_color)
            draw = ImageDraw.Draw(bg)

            # 绘制背景干扰图形。
            for _ in range(12):
                x1 = random_source.randint(0, width)
                y1 = random_source.randint(0, height)
                x2 = random_source.randint(0, width)
                y2 = random_source.randint(0, height)
                color = (
                    random_source.randint(100, 220),
                    random_source.randint(100, 220),
                    random_source.randint(100, 220),
                )
                draw.line(
                    [(x1, y1), (x2, y2)],
                    fill=color,
                    width=random_source.randint(1, 3),
                )

            for _ in range(6):
                rx = random_source.randint(0, width - 40)
                ry = random_source.randint(0, height - 40)
                ellipse_width = random_source.randint(20, 50)
                ellipse_height = random_source.randint(20, 50)
                draw.ellipse(
                    [(rx, ry), (rx + ellipse_width, ry + ellipse_height)],
                    fill=(
                        random_source.randint(150, 230),
                        random_source.randint(150, 230),
                        random_source.randint(150, 230),
                    ),
                )

            target_x = random_source.randint(70, width - puzzle_w - 20)
            target_y = random_source.randint(20, height - puzzle_h - 20)

            # 裁剪拼图滑块。
            block = bg.crop((target_x, target_y, target_x + puzzle_w, target_y + puzzle_h))

            # 在原背景上打暗抠图区域。
            overlay = Image.new("RGBA", (puzzle_w, puzzle_h), (0, 0, 0, 160))
            bg.paste(overlay, (target_x, target_y), overlay)

            draw = ImageDraw.Draw(bg)
            draw.rectangle(
                [(target_x, target_y), (target_x + puzzle_w, target_y + puzzle_h)],
                outline=(255, 255, 255),
                width=2,
            )

            block_bg = Image.new("RGBA", (puzzle_w, puzzle_h), (0, 0, 0, 0))
            block_bg.paste(block, (0, 0))
            draw_block = ImageDraw.Draw(block_bg)
            draw_block.rectangle(
                [(0, 0), (puzzle_w - 1, puzzle_h - 1)],
                outline=(255, 255, 255),
                width=2,
            )

            bg_buf = io.BytesIO()
            bg.save(bg_buf, format="PNG")
            bg_base64 = "data:image/png;base64," + base64.b64encode(bg_buf.getvalue()).decode("ascii")

            block_buf = io.BytesIO()
            block_bg.save(block_buf, format="PNG")
            block_base64 = "data:image/png;base64," + base64.b64encode(block_buf.getvalue()).decode("ascii")

            challenge_id = uuid.uuid4().hex
            self._challenges[challenge_id] = {
                "x": target_x,
                "created_at": time.time(),
                "client_ip": client_ip,
            }

            return {
                "challenge_id": challenge_id,
                "bg_image": bg_base64,
                "puzzle_image": block_base64,
                "y": target_y,
                "width": width,
                "height": height,
                "puzzle_width": puzzle_w,
                "puzzle_height": puzzle_h,
            }

    def verify_challenge(
        self, challenge_id: str, x: float, *, client_ip: str = ""
    ) -> str | None:
        with self._lock:
            self._cleanup_expired()
            item = self._challenges.pop(challenge_id, None)
            if not item:
                return None
            if item["client_ip"] != client_ip:
                return None
            target_x = item["x"]
            if abs(x - target_x) <= self._tolerance:
                token = "cap_" + uuid.uuid4().hex
                self._verified_tokens[token] = (time.time(), client_ip)
                return token
            return None

    def consume_token(self, token: str, *, client_ip: str = "") -> bool:
        with self._lock:
            self._cleanup_expired()
            if not token:
                return False
            record = self._verified_tokens.get(token)
            if record is not None and record[1] == client_ip:
                del self._verified_tokens[token]
                return True
            return False
