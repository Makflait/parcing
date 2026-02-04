"""
Authentication Module
JWT-based authentication with refresh tokens
"""
import os
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)

from .database import db, User, Session, ActivityLog, UserLimits

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')
jwt = JWTManager()


def init_auth(app):
    """Инициализация JWT"""
    app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=15)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
    jwt.init_app(app)


def hash_password(password: str) -> str:
    """Хэширование пароля"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Проверка пароля"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def log_activity(user_id: int, action: str, details: dict = None):
    """Запись активности в лог"""
    try:
        log = ActivityLog(
            user_id=user_id,
            action=action,
            details=details or {},
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass


def get_user_limits(user: User) -> dict:
    """Получить лимиты пользователя"""
    limits = UserLimits.query.filter_by(plan=user.plan).first()
    if limits:
        return {
            'max_bloggers': limits.max_bloggers,
            'max_videos_per_day': limits.max_videos_per_day,
            'trend_watch_enabled': limits.trend_watch_enabled,
            'api_rate_limit': limits.api_rate_limit
        }
    return {
        'max_bloggers': 5,
        'max_videos_per_day': 100,
        'trend_watch_enabled': False,
        'api_rate_limit': 100
    }


# Decorators

def admin_required(f):
    """Декоратор для проверки админских прав"""
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Получить текущего пользователя"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)


# Routes

@auth_bp.route('/register', methods=['POST'])
def register():
    """Регистрация нового пользователя"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '').strip()

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    # Проверить существование
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    # Создать пользователя
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name or email.split('@')[0],
        role='user',
        plan='free'
    )
    db.session.add(user)
    db.session.commit()

    log_activity(user.id, 'register', {'email': email})

    # Создать токены
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify({
        'success': True,
        'user': user.to_dict(),
        'access_token': access_token,
        'refresh_token': refresh_token
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """Вход пользователя"""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not verify_password(password, user.password_hash):
        return jsonify({'error': 'Invalid credentials'}), 401

    if not user.is_active:
        return jsonify({'error': 'Account is deactivated'}), 403

    # Обновить last_login
    user.last_login = datetime.utcnow()
    db.session.commit()

    log_activity(user.id, 'login', {'email': email})

    # Создать токены
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify({
        'success': True,
        'user': user.to_dict(),
        'limits': get_user_limits(user),
        'access_token': access_token,
        'refresh_token': refresh_token
    })


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Выход пользователя"""
    user_id = get_jwt_identity()
    log_activity(user_id, 'logout', {})
    return jsonify({'success': True, 'message': 'Logged out'})


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Обновить access token"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user or not user.is_active:
        return jsonify({'error': 'Invalid user'}), 401

    access_token = create_access_token(identity=user_id)
    return jsonify({
        'access_token': access_token
    })


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    """Получить текущего пользователя"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'user': user.to_dict(),
        'limits': get_user_limits(user),
        'bloggers_count': user.bloggers.filter_by(is_active=True).count()
    })


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Смена пароля"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    data = request.get_json()

    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not verify_password(old_password, user.password_hash):
        return jsonify({'error': 'Invalid current password'}), 401

    if len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    user.password_hash = hash_password(new_password)
    db.session.commit()

    log_activity(user_id, 'change_password', {})

    return jsonify({'success': True, 'message': 'Password changed'})


# JWT Callbacks

@jwt.user_identity_loader
def user_identity_lookup(user_id):
    return user_id


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return User.query.get(identity)


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'error': 'Token expired',
        'message': 'Please refresh your token'
    }), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        'error': 'Invalid token',
        'message': str(error)
    }), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({
        'error': 'Authorization required',
        'message': 'Token is missing'
    }), 401
