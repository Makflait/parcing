"""
Scheduler Module
Автоматический ежедневный парсинг блогеров
"""
import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scheduler')

scheduler = None


def parse_all_users_bloggers(app):
    """Парсинг всех блогеров всех пользователей"""
    logger.info(f"[Scheduler] Starting daily parsing at {datetime.now()}")

    try:
        from web.parser_service import get_parser_service
        from web.database import User, Blogger

        ps = get_parser_service()
        if not ps:
            logger.warning("[Scheduler] Parser service not available")
            return

        with app.app_context():
            # Получаем всех активных пользователей
            users = User.query.filter_by(is_active=True).all()

            total_bloggers = 0
            total_parsed = 0

            for user in users:
                bloggers = Blogger.query.filter_by(
                    user_id=user.id,
                    is_active=True
                ).all()

                for blogger in bloggers:
                    total_bloggers += 1
                    try:
                        result = ps.parse_blogger(blogger.id, user.id)
                        if result.get('success'):
                            total_parsed += 1
                            logger.info(f"[Scheduler] Parsed blogger {blogger.name}: {result.get('total_videos', 0)} videos")
                    except Exception as e:
                        logger.error(f"[Scheduler] Error parsing {blogger.name}: {e}")

            logger.info(f"[Scheduler] Daily parsing completed: {total_parsed}/{total_bloggers} bloggers")

    except Exception as e:
        logger.error(f"[Scheduler] Error in daily parsing: {e}")


def init_scheduler(app):
    """Инициализация планировщика"""
    global scheduler

    if scheduler is not None:
        logger.info("[Scheduler] Already initialized")
        return scheduler

    scheduler = BackgroundScheduler()

    # Ежедневный парсинг в 3:00 ночи (когда нагрузка минимальная)
    parse_hour = int(os.getenv('PARSE_HOUR', '3'))
    parse_minute = int(os.getenv('PARSE_MINUTE', '0'))

    scheduler.add_job(
        func=lambda: parse_all_users_bloggers(app),
        trigger=CronTrigger(hour=parse_hour, minute=parse_minute),
        id='daily_parsing',
        name='Daily bloggers parsing',
        replace_existing=True,
        misfire_grace_time=3600  # Если пропустили - выполнить в течение часа
    )

    scheduler.start()
    logger.info(f"[Scheduler] Started. Daily parsing scheduled at {parse_hour:02d}:{parse_minute:02d}")

    return scheduler


def get_scheduler():
    """Получить экземпляр планировщика"""
    return scheduler


def trigger_manual_parse(app, user_id=None):
    """Запуск ручного парсинга (для тестов или админки)"""
    from web.parser_service import get_parser_service
    from web.database import User, Blogger

    ps = get_parser_service()
    if not ps:
        return {'error': 'Parser service not available'}

    with app.app_context():
        if user_id:
            # Парсим только блогеров конкретного пользователя
            bloggers = Blogger.query.filter_by(user_id=user_id, is_active=True).all()
        else:
            # Парсим всех
            bloggers = Blogger.query.filter_by(is_active=True).all()

        results = []
        for blogger in bloggers:
            try:
                result = ps.parse_blogger(blogger.id, blogger.user_id)
                results.append({
                    'blogger': blogger.name,
                    'success': result.get('success', False),
                    'videos': result.get('total_videos', 0)
                })
            except Exception as e:
                results.append({
                    'blogger': blogger.name,
                    'success': False,
                    'error': str(e)
                })

        return {
            'total': len(bloggers),
            'parsed': len([r for r in results if r.get('success')]),
            'results': results
        }


def shutdown_scheduler():
    """Остановка планировщика"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("[Scheduler] Shutdown complete")
