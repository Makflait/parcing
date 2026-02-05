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
USE_POSTGRES = os.getenv('DATABASE_URL') is not None
REQUIRE_AUTH = os.getenv('REQUIRE_AUTH', 'false').lower() == 'true'

# Инициализация приложения
app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
CORS(app, supports_credentials=True)

# PostgreSQL + Auth режим
if USE_POSTGRES:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    from .database import db, init_db, User, Blogger, VideoHistory
    from .auth import auth_bp, init_auth, get_current_user, jwt_required, get_jwt_identity
    from .admin import admin_bp

    init_db(app)
    init_auth(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

# Импорт Trend Watcher
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
        if REQUIRE_AUTH and USE_POSTGRES:
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
        'mode': 'postgres' if USE_POSTGRES else 'local',
        'auth_required': REQUIRE_AUTH,
        'trends_available': HAS_TRENDS,
        'spy_available': HAS_SPY
    })


# ==================== API: STATS ====================

@app.route('/api/stats')
@optional_auth
def get_stats():
    """Получение общей статистики"""
    try:
        client = get_sheets_client()
        config = load_config()
        spreadsheet = client.open(config.get('spreadsheet_name', 'Blogger Stats'))

        config_bloggers = {b['name'] for b in config.get('bloggers', [])}

        stats = {
            'total_videos': 0,
            'total_views': 0,
            'total_likes': 0,
            'total_comments': 0,
            'bloggers': [],
            'platforms': {'YouTube': {'videos': 0, 'views': 0}, 'TikTok': {'videos': 0, 'views': 0}}
        }

        sheets_by_name = {sheet.title: sheet for sheet in spreadsheet.worksheets()}

        for blogger in config.get('bloggers', []):
            blogger_name = blogger['name']

            blogger_stats = {
                'name': blogger_name,
                'videos': 0,
                'views': 0,
                'likes': 0,
                'comments': 0,
                'youtube_views': 0,
                'tiktok_views': 0,
                'avg_views': 0,
                'engagement': 0
            }

            if blogger_name in sheets_by_name:
                sheet = sheets_by_name[blogger_name]
                data = sheet.get_all_values()

                for row in data[1:]:
                    if len(row) >= 9:
                        try:
                            platform = row[0]
                            views = int(row[5]) if row[5] else 0
                            likes = int(row[6]) if row[6] else 0
                            comments = int(row[7]) if row[7] else 0

                            blogger_stats['videos'] += 1
                            blogger_stats['views'] += views
                            blogger_stats['likes'] += likes
                            blogger_stats['comments'] += comments

                            stats['total_videos'] += 1
                            stats['total_views'] += views
                            stats['total_likes'] += likes
                            stats['total_comments'] += comments

                            if platform == 'YouTube':
                                blogger_stats['youtube_views'] += views
                                stats['platforms']['YouTube']['videos'] += 1
                                stats['platforms']['YouTube']['views'] += views
                            elif platform == 'TikTok':
                                blogger_stats['tiktok_views'] += views
                                stats['platforms']['TikTok']['videos'] += 1
                                stats['platforms']['TikTok']['views'] += views
                        except:
                            continue

                if blogger_stats['videos'] > 0:
                    blogger_stats['avg_views'] = blogger_stats['views'] // blogger_stats['videos']
                    blogger_stats['engagement'] = round(blogger_stats['likes'] / blogger_stats['views'] * 100, 2) if blogger_stats['views'] > 0 else 0

            stats['bloggers'].append(blogger_stats)

        stats['bloggers'].sort(key=lambda x: x['views'], reverse=True)
        stats['avg_views'] = stats['total_views'] // stats['total_videos'] if stats['total_videos'] > 0 else 0
        stats['engagement'] = round(stats['total_likes'] / stats['total_views'] * 100, 2) if stats['total_views'] > 0 else 0

        return jsonify(stats)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/blogger/<name>')
@optional_auth
def get_blogger_details(name):
    """Детальная информация о блогере"""
    try:
        client = get_sheets_client()
        config = load_config()
        spreadsheet = client.open(config.get('spreadsheet_name', 'Blogger Stats'))

        try:
            sheet = spreadsheet.worksheet(name)
        except:
            return jsonify({'error': 'Блогер не найден'}), 404

        data = sheet.get_all_values()
        videos = []

        for row in data[1:]:
            if len(row) >= 9:
                try:
                    videos.append({
                        'platform': row[0],
                        'publish_date': row[1],
                        'last_update': row[2],
                        'title': row[3][:80] + '...' if len(row[3]) > 80 else row[3],
                        'url': row[4],
                        'views': int(row[5]) if row[5] else 0,
                        'likes': int(row[6]) if row[6] else 0,
                        'comments': int(row[7]) if row[7] else 0,
                        'shares': int(row[8]) if row[8] else 0
                    })
                except:
                    continue

        videos.sort(key=lambda x: x['views'], reverse=True)

        blogger_config = None
        for b in config.get('bloggers', []):
            if b['name'] == name:
                blogger_config = b
                break

        return jsonify({
            'name': name,
            'config': blogger_config,
            'videos': videos,
            'total_videos': len(videos),
            'total_views': sum(v['views'] for v in videos),
            'total_likes': sum(v['likes'] for v in videos),
            'youtube_videos': len([v for v in videos if v['platform'] == 'YouTube']),
            'tiktok_videos': len([v for v in videos if v['platform'] == 'TikTok'])
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== API: BLOGGERS CRUD ====================

@app.route('/api/bloggers')
@optional_auth
def get_bloggers():
    """Список блогеров"""
    config = load_config()
    return jsonify(config.get('bloggers', []))


@app.route('/api/bloggers', methods=['POST'])
@optional_auth
def add_blogger():
    """Добавление блогера"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        youtube = data.get('youtube', '').strip()
        tiktok = data.get('tiktok', '').strip()

        if not name:
            return jsonify({'error': 'Имя обязательно'}), 400
        if not youtube and not tiktok:
            return jsonify({'error': 'Нужна хотя бы одна ссылка'}), 400

        config = load_config()

        for b in config.get('bloggers', []):
            if b['name'].lower() == name.lower():
                return jsonify({'error': 'Блогер уже существует'}), 400

        new_blogger = {'name': name}
        if youtube:
            new_blogger['youtube'] = youtube
        if tiktok:
            new_blogger['tiktok'] = tiktok
        if data.get('instagram'):
            new_blogger['instagram'] = data.get('instagram', '').strip()

        config.setdefault('bloggers', []).append(new_blogger)
        save_config(config)

        return jsonify({'success': True, 'blogger': new_blogger})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bloggers/<name>', methods=['PUT'])
@optional_auth
def update_blogger(name):
    """Обновление блогера"""
    try:
        data = request.json
        config = load_config()

        for blogger in config.get('bloggers', []):
            if blogger['name'] == name:
                if data.get('name'):
                    blogger['name'] = data['name']
                if 'youtube' in data:
                    blogger['youtube'] = data['youtube']
                if 'tiktok' in data:
                    blogger['tiktok'] = data['tiktok']
                if 'instagram' in data:
                    blogger['instagram'] = data['instagram']
                save_config(config)
                return jsonify({'success': True, 'blogger': blogger})

        return jsonify({'error': 'Блогер не найден'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bloggers/<name>', methods=['DELETE'])
@optional_auth
def delete_blogger(name):
    """Удаление блогера"""
    try:
        config = load_config()
        original_count = len(config.get('bloggers', []))
        config['bloggers'] = [b for b in config.get('bloggers', []) if b['name'] != name]

        if len(config['bloggers']) == original_count:
            return jsonify({'error': 'Блогер не найден'}), 404

        save_config(config)
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== API: PARSER ====================

def run_parser_thread():
    """Запуск парсера в отдельном потоке"""
    global parser_status
    parser_status['running'] = True
    parser_status['progress'] = 0
    parser_status['log'] = []

    try:
        process = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, 'main.py')],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE_DIR
        )

        for line in process.stdout:
            line = line.strip()
            if line:
                parser_status['log'].append(line)
                if 'Обработка:' in line:
                    parser_status['current_blogger'] = line.split('Обработка:')[-1].strip()
                if '%|' in line:
                    try:
                        pct = int(line.split('%')[0].split()[-1])
                        parser_status['progress'] = pct
                    except:
                        pass

        process.wait()
        parser_status['progress'] = 100

    except Exception as e:
        parser_status['log'].append(f'Ошибка: {str(e)}')

    finally:
        parser_status['running'] = False


@app.route('/api/parser/start', methods=['POST'])
@optional_auth
def start_parser():
    """Запуск парсера"""
    global parser_status

    if parser_status['running']:
        return jsonify({'error': 'Парсер уже запущен'}), 400

    thread = threading.Thread(target=run_parser_thread)
    thread.start()

    return jsonify({'success': True, 'message': 'Парсер запущен'})


@app.route('/api/parser/status')
@optional_auth
def get_parser_status():
    """Статус парсера"""
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
    print("=" * 50)
    print("Blogger Analytics Web Interface v3.0")
    print(f"Mode: {'PostgreSQL' if USE_POSTGRES else 'Local (SQLite/JSON)'}")
    print(f"Auth: {'Required' if REQUIRE_AUTH else 'Optional'}")
    print("http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000, host='0.0.0.0')
