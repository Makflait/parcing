"""
Admin Module
API для администрирования системы
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

try:
    from .database import db, User, Blogger, VideoHistory, TrendVideo, DetectedTrend, ActivityLog
    from .auth import admin_required, hash_password, log_activity
except ImportError:
    from database import db, User, Blogger, VideoHistory, TrendVideo, DetectedTrend, ActivityLog
    from auth import admin_required, hash_password, log_activity

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    """Общая статистика системы"""
    users_count = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    bloggers_count = Blogger.query.count()
    videos_count = VideoHistory.query.count()
    trends_count = DetectedTrend.query.count()

    # Пользователи по ролям
    users_by_role = db.session.query(
        User.role, func.count(User.id)
    ).group_by(User.role).all()

    # Активность за последние 7 дней
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_logins = ActivityLog.query.filter(
        ActivityLog.action == 'login',
        ActivityLog.created_at >= week_ago
    ).count()

    # Новые пользователи за неделю
    new_users = User.query.filter(User.created_at >= week_ago).count()

    return jsonify({
        'users': {
            'total': users_count,
            'active': active_users,
            'by_role': {role: count for role, count in users_by_role},
            'new_this_week': new_users
        },
        'bloggers': bloggers_count,
        'videos_recorded': videos_count,
        'trends_detected': trends_count,
        'recent_logins': recent_logins
    })


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """Список всех пользователей"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '')

    query = User.query

    if search:
        query = query.filter(
            (User.email.ilike(f'%{search}%')) |
            (User.name.ilike(f'%{search}%'))
        )

    if role_filter:
        query = query.filter(User.role == role_filter)

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    users = []
    for user in pagination.items:
        user_data = user.to_dict()
        user_data['bloggers_count'] = user.bloggers.filter_by(is_active=True).count()
        users.append(user_data)

    return jsonify({
        'users': users,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """Детальная информация о пользователе"""
    user = User.query.get_or_404(user_id)

    # Получить блогеров пользователя
    bloggers = [b.to_dict() for b in user.bloggers.filter_by(is_active=True).all()]

    # Последняя активность
    recent_activity = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(ActivityLog.created_at.desc())\
        .limit(10).all()

    return jsonify({
        'user': user.to_dict(),
        'bloggers': bloggers,
        'activity': [{
            'action': a.action,
            'details': a.details,
            'ip': a.ip_address,
            'time': a.created_at.isoformat()
        } for a in recent_activity]
    })


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Обновить пользователя"""
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if 'name' in data:
        user.name = data['name']

    if 'email' in data:
        existing = User.query.filter(User.email == data['email'], User.id != user_id).first()
        if existing:
            return jsonify({'error': 'Email already in use'}), 409
        user.email = data['email']

    if 'role' in data and data['role'] in ['user', 'admin']:
        user.role = data['role']

    if 'is_active' in data:
        user.is_active = bool(data['is_active'])

    if 'password' in data and data['password']:
        user.password_hash = hash_password(data['password'])

    db.session.commit()

    admin_id = get_jwt_identity()
    log_activity(admin_id, 'admin_update_user', {'user_id': user_id, 'changes': list(data.keys())})

    return jsonify({
        'success': True,
        'user': user.to_dict()
    })


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Удалить пользователя"""
    user = User.query.get_or_404(user_id)

    # Нельзя удалить себя
    admin_id = get_jwt_identity()
    if user_id == admin_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400

    # Soft delete
    user.is_active = False
    db.session.commit()

    log_activity(admin_id, 'admin_delete_user', {'user_id': user_id, 'email': user.email})

    return jsonify({
        'success': True,
        'message': f'User {user.email} deactivated'
    })


@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Создать нового пользователя"""
    data = request.get_json()

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '')
    role = data.get('role', 'user')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name or email.split('@')[0],
        role=role if role in ['user', 'admin'] else 'user'
    )
    db.session.add(user)
    db.session.commit()

    admin_id = get_jwt_identity()
    log_activity(admin_id, 'admin_create_user', {'user_id': user.id, 'email': email})

    return jsonify({
        'success': True,
        'user': user.to_dict()
    }), 201


@admin_bp.route('/logs', methods=['GET'])
@admin_required
def get_logs():
    """Получить логи активности"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')

    query = ActivityLog.query

    if user_id:
        query = query.filter_by(user_id=user_id)

    if action:
        query = query.filter_by(action=action)

    query = query.order_by(ActivityLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    logs = []
    for log in pagination.items:
        user = User.query.get(log.user_id) if log.user_id else None
        logs.append({
            'id': log.id,
            'user_email': user.email if user else 'system',
            'action': log.action,
            'details': log.details,
            'ip': log.ip_address,
            'time': log.created_at.isoformat()
        })

    return jsonify({
        'logs': logs,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@admin_bp.route('/trends/stats', methods=['GET'])
@admin_required
def trends_stats():
    """Статистика Trend Watch"""
    monitoring = TrendVideo.query.filter_by(status='monitoring').count()
    trending = TrendVideo.query.filter_by(status='trending').count()
    total_trends = DetectedTrend.query.count()

    # Top trends
    top_trends = DetectedTrend.query\
        .order_by(DetectedTrend.score.desc())\
        .limit(10).all()

    return jsonify({
        'videos_monitoring': monitoring,
        'videos_trending': trending,
        'trends_detected': total_trends,
        'top_trends': [t.to_dict() for t in top_trends]
    })
