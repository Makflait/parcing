"""
PostgreSQL Database Module
Модуль для работы с PostgreSQL и SQLAlchemy
"""
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    """Модель пользователя"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    role = db.Column(db.String(50), default='user')  # user, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    bloggers = db.relationship('Blogger', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active
        }


class Blogger(db.Model):
    """Модель блогера (multi-tenant)"""
    __tablename__ = 'bloggers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    youtube_url = db.Column(db.String(500))
    tiktok_url = db.Column(db.String(500))
    instagram_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'youtube': self.youtube_url,
            'tiktok': self.tiktok_url,
            'instagram': self.instagram_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active
        }


class VideoHistory(db.Model):
    """История видео"""
    __tablename__ = 'video_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    blogger_id = db.Column(db.Integer, db.ForeignKey('bloggers.id', ondelete='CASCADE'))
    video_url = db.Column(db.String(500), nullable=False)
    platform = db.Column(db.String(50))
    title = db.Column(db.Text)
    uploader = db.Column(db.String(255))
    upload_date = db.Column(db.Date)
    views = db.Column(db.BigInteger, default=0)
    likes = db.Column(db.BigInteger, default=0)
    comments = db.Column(db.BigInteger, default=0)
    shares = db.Column(db.BigInteger, default=0)
    engagement_rate = db.Column(db.Float, default=0)
    viral_score = db.Column(db.Float, default=0)
    velocity = db.Column(db.Float, default=0)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    hashtags = db.Column(db.JSON, default=list)
    extra_data = db.Column(db.JSON, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'video_url': self.video_url,
            'platform': self.platform,
            'title': self.title,
            'uploader': self.uploader,
            'views': self.views,
            'likes': self.likes,
            'comments': self.comments,
            'engagement_rate': self.engagement_rate,
            'viral_score': self.viral_score,
            'velocity': self.velocity,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
            'hashtags': self.hashtags
        }


class TrendVideo(db.Model):
    """Видео для мониторинга трендов"""
    __tablename__ = 'trend_videos'

    id = db.Column(db.Integer, primary_key=True)
    video_url = db.Column(db.String(500), unique=True, nullable=False)
    platform = db.Column(db.String(50))
    title = db.Column(db.Text)
    uploader = db.Column(db.String(255))
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime)
    initial_views = db.Column(db.BigInteger, default=0)
    current_views = db.Column(db.BigInteger, default=0)
    velocity = db.Column(db.Float, default=0)
    acceleration = db.Column(db.Float, default=0)
    status = db.Column(db.String(50), default='monitoring')
    hashtags = db.Column(db.JSON, default=list)
    topics = db.Column(db.JSON, default=list)
    extra_data = db.Column(db.JSON, default=dict)

    # Relationships
    snapshots = db.relationship('TrendSnapshot', backref='video', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'video_url': self.video_url,
            'platform': self.platform,
            'title': self.title,
            'uploader': self.uploader,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'initial_views': self.initial_views,
            'current_views': self.current_views,
            'velocity': self.velocity,
            'acceleration': self.acceleration,
            'status': self.status,
            'hashtags': self.hashtags,
            'topics': self.topics
        }


class TrendSnapshot(db.Model):
    """Снимки метрик для трендов"""
    __tablename__ = 'trend_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('trend_videos.id', ondelete='CASCADE'))
    views = db.Column(db.BigInteger, default=0)
    likes = db.Column(db.BigInteger, default=0)
    comments = db.Column(db.BigInteger, default=0)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)


class DetectedTrend(db.Model):
    """Обнаруженные тренды"""
    __tablename__ = 'detected_trends'

    id = db.Column(db.Integer, primary_key=True)
    trend_type = db.Column(db.String(50))
    trend_key = db.Column(db.String(255))
    video_count = db.Column(db.Integer, default=0)
    avg_velocity = db.Column(db.Float, default=0)
    score = db.Column(db.Float, default=0)
    video_urls = db.Column(db.JSON, default=list)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='active')

    def to_dict(self):
        return {
            'id': self.id,
            'trend_type': self.trend_type,
            'trend_key': self.trend_key,
            'video_count': self.video_count,
            'avg_velocity': self.avg_velocity,
            'score': self.score,
            'video_urls': self.video_urls,
            'detected_at': self.detected_at.isoformat() if self.detected_at else None,
            'status': self.status
        }


class Session(db.Model):
    """Сессии пользователей"""
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    token = db.Column(db.String(500), unique=True, nullable=False)
    refresh_token = db.Column(db.String(500), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref='sessions')


class ActivityLog(db.Model):
    """Логи активности"""
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.JSON, default=dict)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='logs')


def init_db(app):
    """Инициализация БД"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
