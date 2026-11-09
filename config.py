"""
Configuration module for REELFIX bot
"""
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()


class Config:
    """Configuration class for the bot"""
    
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Video Processing
    MAX_VIDEO_SIZE: int = int(os.getenv("MAX_VIDEO_SIZE", "500"))
    ALLOWED_VIDEO_FORMATS: str = os.getenv("ALLOWED_VIDEO_FORMATS", "mp4,webm,mov,avi,mkv")
    MAX_PROCESSING_TIME: int = int(os.getenv("MAX_PROCESSING_TIME", "3600"))
    
    # Whisper
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cuda")
    WHISPER_LANGUAGE: str = os.getenv("WHISPER_LANGUAGE", "ru")
    
    # FFmpeg
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg")
    
    # Quality Enhancement
    UPSCALE_FACTOR: int = int(os.getenv("UPSCALE_FACTOR", "2"))
    SHARPEN_STRENGTH: float = float(os.getenv("SHARPEN_STRENGTH", "1.0"))
    DENOISE_STRENGTH: float = float(os.getenv("DENOISE_STRENGTH", "0.5"))
    
    # Audio Enhancement
    AUDIO_NORMALIZE: bool = os.getenv("AUDIO_NORMALIZE", "True").lower() == "true"
    AUDIO_NOISE_REDUCTION: bool = os.getenv("AUDIO_NOISE_REDUCTION", "True").lower() == "true"
    
    # Subtitle
    SUBTITLE_FONT: str = os.getenv("SUBTITLE_FONT", "Roboto")
    SUBTITLE_FONT_SIZE: int = int(os.getenv("SUBTITLE_FONT_SIZE", "24"))
    SUBTITLE_COLOR: str = os.getenv("SUBTITLE_COLOR", "white")
    SUBTITLE_STROKE: str = os.getenv("SUBTITLE_STROKE", "black")
    SUBTITLE_BG_COLOR: str = os.getenv("SUBTITLE_BG_COLOR", "rgba(0,0,0,0.5)")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        return True


# Available subtitle styles
SUBTITLE_STYLES = {
    "classic": {
        "font_size": 24,
        "color": "white",
        "stroke": "black",
        "bg_color": "rgba(0,0,0,0.5)",
        "position": "bottom",
        "alignment": "center"
    },
    "modern": {
        "font_size": 28,
        "color": "#00ff88",
        "stroke": "none",
        "bg_color": "rgba(0,0,0,0.3)",
        "position": "bottom",
        "alignment": "center"
    },
    "minimal": {
        "font_size": 20,
        "color": "white",
        "stroke": "none",
        "bg_color": "none",
        "position": "bottom",
        "alignment": "center"
    },
    "bold": {
        "font_size": 32,
        "color": "yellow",
        "stroke": "black",
        "bg_color": "rgba(0,0,0,0.7)",
        "position": "bottom",
        "alignment": "center"
    },
    "elegant": {
        "font_size": 26,
        "color": "#ff6b6b",
        "stroke": "none",
        "bg_color": "rgba(255,255,255,0.2)",
        "position": "bottom",
        "alignment": "center"
    }
}