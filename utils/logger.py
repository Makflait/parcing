"""
Модуль для настройки логирования
"""
import logging
import os
from datetime import datetime


def setup_logger(name='blogger_stats', log_dir='logs'):
    """
    Настройка логгера с выводом в файл и консоль

    Args:
        name: имя логгера
        log_dir: директория для лог-файлов

    Returns:
        logging.Logger: настроенный логгер
    """
    # Создаем директорию для логов если её нет
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Очищаем существующие обработчики
    logger.handlers = []

    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Обработчик для файла (детальные логи)
    log_file = os.path.join(log_dir, f'parser_{datetime.now().strftime("%Y%m%d")}.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Обработчик для консоли (только важные сообщения)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# Создаем глобальный экземпляр логгера
logger = setup_logger()
