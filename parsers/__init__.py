"""
Парсеры для различных платформ
"""
from .youtube_parser import YouTubeParser
from .tiktok_parser import TikTokParser
from .instagram_parser import InstagramParser

__all__ = ['YouTubeParser', 'TikTokParser', 'InstagramParser']
