"""
Blogger Analytics Web App v3.0
Flask Backend API with Multi-tenancy Support
"""
from flask import Flask, jsonify, request, send_from_directory, Response, g
from flask_cors import CORS
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import subprocess
import threading
import sys
from datetime import datetime
from functools import wraps

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загрузка env переменных
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Пути к файлам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Определяем режим работы
# DATABASE_URL может быть PostgreSQL или SQLite
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL and os.path.exists(os.path.join(BASE_DIR, 'data', 'blogger_analytics.db')):
    DATABASE_URL = f'sqlite:///{os.path.join(BASE_DIR, "data", "blogger_analytics.db")}'

USE_DATABASE = DATABASE_URL is not None
REQUIRE_AUTH = os.getenv('REQUIRE_AUTH', 'false').lower() == 'true'

# Инициализация приложения
app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
CORS(app, supports_credentials=True)

# Database + Auth режим (PostgreSQL или SQLite)
if USE_DATABASE:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    try:
        # Относительный импорт (если запущен как модуль)
        from .database import db, init_db, User, Blogger, VideoHistory
        from .auth import auth_bp, init_auth, get_current_user, jwt_required, get_jwt_identity
        from .admin import admin_bp
    except ImportError:
        # Абсолютный импорт (если запущен как скрипт)
        from database import db, init_db, User, Blogger, VideoHistory
        from auth import auth_bp, init_auth, get_current_user, jwt_required, get_jwt_identity
        from admin import admin_bp

    init_db(app)
    init_auth(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # Инициализация Parser Service
    try:
        from web.parser_service import init_parser_service
        init_parser_service(app)
    except ImportError:
        try:
            from parser_service import init_parser_service
            init_parser_service(app)
        except ImportError:
            print("[Warning] Parser service not available")

    # ????????????? Scheduler (?????????? ???????????)
    if ENABLE_SCHEDULER:
        try:
            from web.scheduler import init_scheduler
            init_scheduler(app)
        except ImportError:
            try:
                from scheduler import init_scheduler
                init_scheduler(app)
            except ImportError:
                print("[Warning] Scheduler not available")
        except Exception as e:
            print(f"[Warning] Scheduler init error: {e}")

# ?????? Trend Watcher
try:
    from trends import TrendWatcher, TrendDB
    trend_watcher = TrendWatcher()
    HAS_TRENDS = True
except ImportError:
    trend_watcher = None
    HAS_TRENDS = False

# Импорт Spy Service
try:
    from trends.spy_service import TrendSpyService
    spy_service = TrendSpyService()
    HAS_SPY = True
except ImportError:
    spy_service = None
    HAS_SPY = False


# Статус парсера
parser_status = {
    'running': False,
    'progress': 0,
    'current_blogger': '',
    'log': []
}


# ==================== HELPERS ====================

def optional_auth(f):
    """Декоратор: auth обязателен только если REQUIRE_AUTH=true"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if REQUIRE_AUTH and USE_DATABASE:
            from flask_jwt_extended import jwt_required, get_jwt_identity
            @jwt_required()
            def inner():
                g.user_id = get_jwt_identity()
                return f(*args, **kwargs)
            return inner()
        else:
            g.user_id = None  # Local mode
            return f(*args, **kwargs)
    return decorated


def get_sheets_client():
    """Подключение к Google Sheets"""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)


def load_config():
    """Загрузка конфигурации"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'spreadsheet_name': 'Blogger Stats', 'bloggers': []}


def save_config(config):
    """Сохранение конфигурации"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ==================== ROUTES ====================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/login.html')
def login_page():
    return send_from_directory('static', 'login.html')


@app.route('/admin.html')
def admin_page():
    return send_from_directory('static', 'admin.html')


@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)


@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'mode': 'database' if USE_DATABASE else 'local',
        'database': DATABASE_URL.split('://')[0] if USE_DATABASE else None,
        'auth_required': REQUIRE_AUTH,
        'trends_available': HAS_TRENDS,
        'spy_available': HAS_SPY
    })


# ==================== API: STATS (Database) ====================

@app.route('/api/stats')
@jwt_required()
def get_stats():
    """Получение общей статистики пользователя"""
    try:
        user_id = int(get_jwt_identity())

        stats = {
            'total_videos': 0,
            'total_views': 0,
            'total_likes': 0,
            'total_comments': 0,
            'bloggers': [],
            'platforms': {
                'youtube': {'videos': 0, 'views': 0},
                'tiktok': {'videos': 0, 'views': 0},
                'instagram': {'videos': 0, 'views': 0}
            }
        }

        # Получаем блогеров пользователя
        bloggers = Blogger.query.filter_by(user_id=user_id, is_active=True).all()

        for blogger in bloggers:
            blogger_stats = {
                'id': blogger.id,
                'name': blogger.name,
                'youtube': blogger.youtube_url,
                'tiktok': blogger.tiktok_url,
                'instagram': blogger.instagram_url,
                'videos': 0,
                'views': 0,
                'likes': 0,
                'comments': 0,
                'youtube_views': 0,
                'tiktok_views': 0,
                'instagram_views': 0,
                'avg_views': 0,
                'engagement': 0
            }

            # Агрегация по платформам
            platform_stats = db.session.query(
                VideoHistory.platform,
                db.func.count(VideoHistory.id).label('videos'),
                db.func.sum(VideoHistory.views).label('views'),
                db.func.sum(VideoHistory.likes).label('likes'),
                db.func.sum(VideoHistory.comments).label('comments')
            ).filter(
                VideoHistory.blogger_id == blogger.id,
                VideoHistory.user_id == user_id
            ).group_by(VideoHistory.platform).all()

            for ps in platform_stats:
                platform = ps.platform or 'unknown'
                videos_count = ps.videos or 0
                views_count = int(ps.views or 0)
                likes_count = int(ps.likes or 0)
                comments_count = int(ps.comments or 0)

                blogger_stats['videos'] += videos_count
                blogger_stats['views'] += views_count
                blogger_stats['likes'] += likes_count
                blogger_stats['comments'] += comments_count

                stats['total_videos'] += videos_count
                stats['total_views'] += views_count
                stats['total_likes'] += likes_count
                stats['total_comments'] += comments_count

                if platform in stats['platforms']:
                    stats['platforms'][platform]['videos'] += videos_count
                    stats['platforms'][platform]['views'] += views_count

                if platform == 'youtube':
                    blogger_stats['youtube_views'] = views_count
                elif platform == 'tiktok':
                    blogger_stats['tiktok_views'] = views_count
                elif platform == 'instagram':
                    blogger_stats['instagram_views'] = views_count

            if blogger_stats['videos'] > 0:
                blogger_stats['avg_views'] = blogger_stats['views'] // blogger_stats['videos']
            if blogger_stats['views'] > 0:
                blogger_stats['engagement'] = round(blogger_stats['likes'] / blogger_stats['views'] * 100, 2)

            stats['bloggers'].append(blogger_stats)

        stats['bloggers'].sort(key=lambda x: x['views'], reverse=True)

        if stats['total_videos'] > 0:
            stats['avg_views'] = stats['total_views'] // stats['total_videos']
        else:
            stats['avg_views'] = 0

        if stats['total_views'] > 0:
            stats['engagement'] = round(stats['total_likes'] / stats['total_views'] * 100, 2)
        else:
            stats['engagement'] = 0

        return jsonify(stats)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/blogger/<int:blogger_id>')
@jwt_required()
def get_blogger_details(blogger_id):
    """Детальная информация о блогере"""
    try:
        user_id = int(get_jwt_identity())

        blogger = Blogger.query.filter_by(id=blogger_id, user_id=user_id).first()
        if not blogger:
            return jsonify({'error': 'Блогер не найден'}), 404

        # Получаем видео
        videos = VideoHistory.query.filter_by(
            blogger_id=blogger_id,
            user_id=user_id
        ).order_by(VideoHistory.views.desc()).limit(100).all()

        videos_data = []
        for v in videos:
            videos_data.append({
                'id': v.id,
                'platform': v.platform,
                'title': v.title[:80] + '...' if v.title and len(v.title) > 80 else v.title,
                'url': v.video_url,
                'views': v.views,
                'likes': v.likes,
                'comments': v.comments,
                'shares': v.shares,
                'engagement_rate': v.engagement_rate,
                'recorded_at': v.recorded_at.isoformat() if v.recorded_at else None
            })

        # Статистика по платформам
        platform_stats = {}
        for platform in ['youtube', 'tiktok', 'instagram']:
            count = len([v for v in videos_data if v['platform'] == platform])
            views = sum([v['views'] for v in videos_data if v['platform'] == platform])
            platform_stats[platform] = {'videos': count, 'views': views}

        return jsonify({
            'id': blogger.id,
            'name': blogger.name,
            'youtube': blogger.youtube_url,
            'tiktok': blogger.tiktok_url,
            'instagram': blogger.instagram_url,
            'created_at': blogger.created_at.isoformat() if blogger.created_at else None,
            'updated_at': blogger.updated_at.isoformat() if blogger.updated_at else None,
            'videos': videos_data,
            'total_videos': len(videos_data),
            'total_views': sum(v['views'] for v in videos_data),
            'total_likes': sum(v['likes'] for v in videos_data),
            'platforms': platform_stats
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== API: BLOGGERS CRUD (Database) ====================

@app.route('/api/bloggers')
@jwt_required()
def get_bloggers():
    """Список блогеров текущего пользователя со статистикой"""
    user_id = int(get_jwt_identity())

    bloggers = Blogger.query.filter_by(user_id=user_id, is_active=True).all()

    result = []
    for blogger in bloggers:
        blogger_data = blogger.to_dict()

        # Агрегируем статистику из VideoHistory
        stats = db.session.query(
            VideoHistory.platform,
            db.func.count(VideoHistory.id).label('videos'),
            db.func.sum(VideoHistory.views).label('views'),
            db.func.sum(VideoHistory.likes).label('likes'),
            db.func.sum(VideoHistory.comments).label('comments')
        ).filter(
            VideoHistory.blogger_id == blogger.id,
            VideoHistory.user_id == user_id
        ).group_by(VideoHistory.platform).all()

        blogger_data['videos'] = 0
        blogger_data['views'] = 0
        blogger_data['likes'] = 0
        blogger_data['comments'] = 0
        blogger_data['youtube_views'] = 0
        blogger_data['tiktok_views'] = 0
        blogger_data['instagram_views'] = 0

        for stat in stats:
            blogger_data['videos'] += stat.videos or 0
            blogger_data['views'] += int(stat.views or 0)
            blogger_data['likes'] += int(stat.likes or 0)
            blogger_data['comments'] += int(stat.comments or 0)

            if stat.platform == 'youtube':
                blogger_data['youtube_views'] = int(stat.views or 0)
            elif stat.platform == 'tiktok':
                blogger_data['tiktok_views'] = int(stat.views or 0)
            elif stat.platform == 'instagram':
                blogger_data['instagram_views'] = int(stat.views or 0)

        if blogger_data['videos'] > 0:
            blogger_data['avg_views'] = blogger_data['views'] // blogger_data['videos']
        else:
            blogger_data['avg_views'] = 0

        if blogger_data['views'] > 0:
            blogger_data['engagement'] = round(blogger_data['likes'] / blogger_data['views'] * 100, 2)
        else:
            blogger_data['engagement'] = 0

        result.append(blogger_data)

    return jsonify(result)


@app.route('/api/bloggers', methods=['POST'])
@jwt_required()
def add_blogger():
    """Добавление блогера с автоматическим парсингом"""
    try:
        user_id = int(get_jwt_identity())
        data = request.json

        name = data.get('name', '').strip()
        youtube = data.get('youtube', '').strip()
        tiktok = data.get('tiktok', '').strip()
        instagram = data.get('instagram', '').strip()

        if not name:
            return jsonify({'error': 'Имя обязательно'}), 400
        if not youtube and not tiktok and not instagram:
            return jsonify({'error': 'Нужна хотя бы одна ссылка'}), 400

        # Проверяем дубликат
        existing = Blogger.query.filter_by(user_id=user_id, name=name, is_active=True).first()
        if existing:
            return jsonify({'error': 'Блогер уже существует'}), 400

        # Создаём блогера
        blogger = Blogger(
            user_id=user_id,
            name=name,
            youtube_url=youtube or None,
            tiktok_url=tiktok or None,
            instagram_url=instagram or None
        )
        db.session.add(blogger)
        db.session.commit()

        blogger_data = blogger.to_dict()
        blogger_data['videos'] = 0
        blogger_data['views'] = 0
        blogger_data['likes'] = 0
        blogger_data['youtube_views'] = 0
        blogger_data['tiktok_views'] = 0
        blogger_data['instagram_views'] = 0
        blogger_data['parsing'] = True

        # Запускаем парсинг в фоне
        try:
            from parser_service import get_parser_service
            ps = get_parser_service()
            if ps:
                ps.parse_blogger_async(blogger.id, user_id)
        except:
            blogger_data['parsing'] = False

        return jsonify({
            'success': True,
            'blogger': blogger_data,
            'message': 'Блогер добавлен, данные загружаются...'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bloggers/<int:blogger_id>', methods=['PUT'])
@jwt_required()
def update_blogger(blogger_id):
    """Обновление блогера"""
    try:
        user_id = int(get_jwt_identity())
        data = request.json

        blogger = Blogger.query.filter_by(id=blogger_id, user_id=user_id).first()
        if not blogger:
            return jsonify({'error': 'Блогер не найден'}), 404

        if data.get('name'):
            blogger.name = data['name']
        if 'youtube' in data:
            blogger.youtube_url = data['youtube'] or None
        if 'tiktok' in data:
            blogger.tiktok_url = data['tiktok'] or None
        if 'instagram' in data:
            blogger.instagram_url = data['instagram'] or None

        blogger.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'success': True, 'blogger': blogger.to_dict()})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bloggers/<int:blogger_id>', methods=['DELETE'])
@jwt_required()
def delete_blogger(blogger_id):
    """Удаление блогера (soft delete)"""
    try:
        user_id = int(get_jwt_identity())

        blogger = Blogger.query.filter_by(id=blogger_id, user_id=user_id).first()
        if not blogger:
            return jsonify({'error': 'Блогер не найден'}), 404

        blogger.is_active = False
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bloggers/<int:blogger_id>/parse', methods=['POST'])
@jwt_required()
def parse_single_blogger(blogger_id):
    """Запуск парсинга конкретного блогера"""
    try:
        user_id = int(get_jwt_identity())

        blogger = Blogger.query.filter_by(id=blogger_id, user_id=user_id).first()
        if not blogger:
            return jsonify({'error': 'Блогер не найден'}), 404

        try:
            from parser_service import get_parser_service
            ps = get_parser_service()
            if ps:
                result = ps.parse_blogger_async(blogger.id, user_id)
                return jsonify(result)
        except Exception as e:
            return jsonify({'error': f'Parser error: {str(e)}'}), 500

        return jsonify({'error': 'Parser not available'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== API: PARSER ====================

@app.route('/api/parser/start', methods=['POST'])
@jwt_required()
def start_parser():
    """Запуск парсинга всех блогеров пользователя"""
    try:
        user_id = int(get_jwt_identity())

        from parser_service import get_parser_service
        ps = get_parser_service()

        if not ps:
            return jsonify({'error': 'Parser service not available'}), 500

        if ps.status['running']:
            return jsonify({'error': 'Парсер уже запущен'}), 400

        # Запускаем парсинг всех блогеров в фоне
        def run_all():
            ps.status['running'] = True
            try:
                result = ps.parse_all_user_bloggers(user_id)
                ps.status['total_parsed'] = result.get('parsed', 0)
                ps.status['errors'] = result.get('errors', [])
                ps.status['last_run'] = datetime.utcnow().isoformat()
            finally:
                ps.status['running'] = False
                ps.status['progress'] = 100

        thread = threading.Thread(target=run_all, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': 'Парсер запущен'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/parser/status')
@jwt_required()
def get_parser_status():
    """Статус парсера"""
    try:
        from parser_service import get_parser_service
        ps = get_parser_service()

        if ps:
            return jsonify(ps.status)

        return jsonify(parser_status)

    except:
        return jsonify(parser_status)


# ==================== API: TREND WATCH (Legacy) ====================

@app.route('/api/trends/analyze')
@optional_auth
def analyze_trends():
    """Анализ трендов (legacy)"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        analysis = trend_watcher.analyze_trends()
        return jsonify(analysis)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/sources')
@optional_auth
def get_trend_sources():
    """Список источников для отслеживания"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        sources = trend_watcher.get_sources()
        return jsonify(sources)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/sources', methods=['POST'])
@optional_auth
def add_trend_source():
    """Добавить источник"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        data = request.json
        url = data.get('url', '').strip()
        name = data.get('name', '').strip()

        if not url:
            return jsonify({'error': 'URL обязателен'}), 400

        result = trend_watcher.add_source(url, name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/sources', methods=['DELETE'])
@optional_auth
def remove_trend_source():
    """Удалить источник"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        data = request.json
        url = data.get('url', '')
        success = trend_watcher.remove_source(url)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/collect', methods=['POST'])
@optional_auth
def collect_trend_data():
    """Собрать свежие данные с источников"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        result = trend_watcher.collect_snapshots()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/discover', methods=['POST'])
@optional_auth
def discover_trends():
    """Автоматически обнаружить трендовый контент"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        max_per_source = request.json.get('max_per_source', 5) if request.json else 5
        result = trend_watcher.auto_discover(max_per_source=max_per_source)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/discover-stream')
@optional_auth
def discover_trends_stream():
    """SSE endpoint для обнаружения трендов с прогрессом"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    def generate():
        try:
            from trends.discovery import TrendDiscovery
            discovery = TrendDiscovery()

            final_result = None

            for progress in discovery.discover_with_progress(max_per_source=5):
                if progress.get('type') == 'progress':
                    yield f"data: {json.dumps(progress)}\n\n"
                else:
                    final_result = progress

            if final_result and 'videos' in final_result:
                collected = 0
                for video in final_result.get('videos', []):
                    try:
                        trend_watcher.db.record_video_snapshot(video)
                        collected += 1
                    except:
                        pass

                final_result['collected'] = collected
                yield f"data: {json.dumps({'type': 'complete', 'result': final_result})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/trends/video/<path:video_url>')
@optional_auth
def get_video_trend_detail(video_url):
    """Детальная информация о видео"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        detail = trend_watcher.get_video_detail(video_url)
        if not detail:
            return jsonify({'error': 'Video not found'}), 404
        return jsonify(detail)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/stats')
@optional_auth
def get_trend_stats():
    """Статистика trend watcher"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        stats = trend_watcher.db.get_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/history')
@optional_auth
def get_trend_history():
    """История обнаруженных трендов"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        trends = trend_watcher.db.get_recent_trends(limit=50)
        return jsonify(trends)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trends/recent')
@optional_auth
def get_recent_videos():
    """Недавно обнаруженные видео"""
    if not HAS_TRENDS:
        return jsonify({'error': 'Trend module not available'}), 500

    try:
        limit = request.args.get('limit', 50, type=int)
        videos = trend_watcher.db.get_recent_videos(limit=limit)
        return jsonify(videos)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== API: SPY SERVICE (New) ====================

@app.route('/api/spy/discover', methods=['POST'])
@optional_auth
def spy_discover():
    """Spy Service: обнаружить новые видео"""
    if not HAS_SPY:
        return jsonify({'error': 'Spy service not available'}), 500

    try:
        max_per_source = request.json.get('max_per_source', 30) if request.json else 30
        results = spy_service.discover_videos(max_per_source=max_per_source)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spy/analyze', methods=['POST'])
@optional_auth
def spy_analyze():
    """Spy Service: анализ трендов"""
    if not HAS_SPY:
        return jsonify({'error': 'Spy service not available'}), 500

    try:
        videos = request.json.get('videos', []) if request.json else []
        analysis = spy_service.analyze_trends(videos)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spy/report')
@optional_auth
def spy_report():
    """Spy Service: текстовый отчет"""
    if not HAS_SPY:
        return jsonify({'error': 'Spy service not available'}), 500

    try:
        # Сначала discover, потом analyze
        discovered = spy_service.discover_videos(max_per_source=20)
        all_videos = discovered.get('youtube', []) + discovered.get('tiktok', [])

        # Симулируем velocity для анализа
        import random
        for v in all_videos:
            v['velocity'] = v.get('views', 0) / max(24, 1)
            v['acceleration'] = 1.0 + random.random()

        analysis = spy_service.analyze_trends(all_videos)
        report = spy_service.generate_report(analysis)

        return jsonify({
            'report': report,
            'analysis': analysis,
            'discovered': discovered['total']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    print("=" * 50)
    print("Blogger Analytics Web Interface v3.0")
    print(f"Mode: {'PostgreSQL' if USE_DATABASE else 'Local (SQLite/JSON)'}")
    print(f"Auth: {'Required' if REQUIRE_AUTH else 'Optional'}")
    print(f"http://localhost:{port}")
    print("=" * 50)
    print()
    print("Startup commands:")
    print(f"  CMD:        cd web & python app.py")
    print(f"  PowerShell: cd web; python app.py")
    print(f"  Custom port (PS): $env:PORT='5001'; python app.py")
    print(f"  Custom port (CMD): set PORT=5001 & python app.py")
    print()
    app.run(debug=True, port=port, host='0.0.0.0', use_reloader=False)
