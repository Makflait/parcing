"""
Инициализация базы данных и создание первого администратора
Работает с SQLite (локально) или PostgreSQL (production)
"""
import os
import sys

# Определяем базовую директорию
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Создаём папку data если нет
os.makedirs(DATA_DIR, exist_ok=True)

# Для локального режима используем SQLite с абсолютным путём
if not os.getenv('DATABASE_URL'):
    db_path = os.path.join(DATA_DIR, 'blogger_analytics.db')
    # Windows путь нужно с прямыми слэшами
    db_path = db_path.replace('\\', '/')
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

from flask import Flask
from web.database import db, User
import bcrypt

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

db.init_app(app)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def init_database():
    """Инициализация БД и создание таблиц"""
    with app.app_context():
        db.create_all()
        print("[OK] Таблицы созданы")

def create_admin(email: str, password: str, name: str = None):
    """Создание администратора"""
    with app.app_context():
        # Проверяем существование
        existing = User.query.filter_by(email=email.lower()).first()
        if existing:
            print(f"[!] Пользователь {email} уже существует")
            return False

        admin = User(
            email=email.lower(),
            password_hash=hash_password(password),
            name=name or 'Admin',
            role='admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()

        print(f"[OK] Администратор создан:")
        print(f"  Email: {email}")
        print(f"  Пароль: {password}")
        print(f"  Роль: admin")
        return True

def list_users():
    """Список пользователей"""
    with app.app_context():
        users = User.query.all()
        if not users:
            print("Пользователей нет")
            return

        print(f"\nВсего пользователей: {len(users)}")
        print("-" * 50)
        for u in users:
            print(f"  {u.email} | {u.role} | {'Активен' if u.is_active else 'Заблокирован'}")

if __name__ == '__main__':
    print("=" * 50)
    print("Blogger Analytics - Инициализация")
    print("=" * 50)

    # Инициализация БД
    print("\n[1] Инициализация базы данных...")
    init_database()
    print("[OK] База данных готова")

    # Проверяем есть ли уже админ
    with app.app_context():
        admin_exists = User.query.filter_by(role='admin').first()

    if admin_exists:
        print(f"\n[!] Администратор уже существует: {admin_exists.email}")
        list_users()
    else:
        # Создаём первого админа
        print("\n[2] Создание первого администратора...")

        if len(sys.argv) >= 3:
            email = sys.argv[1]
            password = sys.argv[2]
            name = sys.argv[3] if len(sys.argv) > 3 else 'Admin'
        else:
            # Дефолтные данные
            email = 'admin@blogger-analytics.local'
            password = 'admin2026!'
            name = 'Admin'

        create_admin(email, password, name)

    print("\n" + "=" * 50)
    print("Готово! Запустите сервер: python web/app.py")
    print("Затем откройте: http://localhost:5000/login.html")
    print("=" * 50)
