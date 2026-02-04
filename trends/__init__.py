"""
Trend Watching Module v2.0
Автоматическое отслеживание трендов и velocity видео
"""
from .db import TrendDB
from .watcher import TrendWatcher
from .discovery import TrendDiscovery

__all__ = ['TrendDB', 'TrendWatcher', 'TrendDiscovery']
