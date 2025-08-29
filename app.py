from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

# Инициализация приложения
app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'instance', 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширений
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'

# Модели базы данных
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    services = db.relationship('UserService', backref='user', lazy=True)
    balance = db.Column(db.Float, default=0.0)  # Баланс для клиентов

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}, Role: {self.role}>'

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    users = db.relationship('UserService', backref='service', lazy=True)

class UserService(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    price_at_connection = db.Column(db.Float)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'service_id', name='_user_service_uc'),
    )

# Загрузчик пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Маршруты
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = bool(request.form.get('remember_me'))
        
        if not username or not password:
            flash('Пожалуйста, заполните все поля.', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Неверное имя пользователя или пароль.', 'error')
            return render_template('login.html')
        
        if not user.is_active:
            flash('Ваш аккаунт деактивирован.', 'error')
            return render_template('login.html')
        
        login_user(user, remember=remember_me)
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        role = request.form.get('role', '').strip()
        
        errors = []
        
        if not all([username, email, password, password_confirm, role]):
            errors.append('Все поля обязательны для заполнения.')
        
        if len(username) < 3:
            errors.append('Имя пользователя должно содержать минимум 3 символа.')
        
        if len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов.')
        
        if password != password_confirm:
            errors.append('Пароли не совпадают.')
        
        if role not in ['client', 'customer', 'admin']:
            errors.append('Указана неверная роль.')
        
        if User.query.filter_by(username=username).first():
            errors.append('Пользователь с таким именем уже существует.')
        
        if User.query.filter_by(email=email).first():
            errors.append('Пользователь с таким email уже существует.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html')
        
        try:
            new_user = User(
                username=username,
                email=email,
                role=role
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла ошибка при регистрации: {str(e)}', 'error')
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        flash('Доступ запрещен. Только для администраторов.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

# ================== УПРАВЛЕНИЕ УСЛУГАМИ ДЛЯ ЗАКАЗЧИКА ==================

@app.route('/customer/services')
@login_required
def customer_services():
    """Страница управления услугами для заказчика"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    services = Service.query.filter_by(customer_id=current_user.id).order_by(Service.created_at.desc()).all()
    return render_template('customer_services.html', services=services)

@app.route('/customer/service/create', methods=['POST'])
@login_required
def create_service():
    """Создание новой услуги"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('customer_services'))
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    
    try:
        price = float(request.form.get('price', 0))
    except ValueError:
        flash('Неверная цена услуги', 'error')
        return redirect(url_for('customer_services'))
    
    if not name or not description or price <= 0:
        flash('Все поля обязательны для заполнения', 'error')
        return redirect(url_for('customer_services'))
    
    try:
        new_service = Service(
            name=name,
            description=description,
            price=price,
            customer_id=current_user.id
        )
        db.session.add(new_service)
        db.session.commit()
        flash('Услуга успешно создана!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при создании услуги: {str(e)}', 'error')
    
    return redirect(url_for('customer_services'))

@app.route('/customer/service/update/<int:service_id>', methods=['POST'])
@login_required
def update_service(service_id):
    """Обновление услуги"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('customer_services'))
    
    service = Service.query.filter_by(id=service_id, customer_id=current_user.id).first()
    if not service:
        flash('Услуга не найдена', 'error')
        return redirect(url_for('customer_services'))
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    
    try:
        price = float(request.form.get('price', 0))
    except ValueError:
        flash('Неверная цена услуги', 'error')
        return redirect(url_for('customer_services'))
    
    if not name or not description or price <= 0:
        flash('Все поля обязательны для заполнения', 'error')
        return redirect(url_for('customer_services'))
    
    try:
        service.name = name
        service.description = description
        service.price = price
        db.session.commit()
        flash('Услуга успешно обновлена!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении услуги: {str(e)}', 'error')
    
    return redirect(url_for('customer_services'))

@app.route('/customer/service/delete/<int:service_id>')
@login_required
def delete_service(service_id):
    """Удаление услуги"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    service = Service.query.filter_by(id=service_id, customer_id=current_user.id).first()
    if not service:
        flash('Услуга не найдена', 'error')
        return redirect(url_for('customer_services'))
    
    try:
        # Удаляем все связи пользователей с этой услугой
        UserService.query.filter_by(service_id=service_id).delete()
        # Удаляем саму услугу
        db.session.delete(service)
        db.session.commit()
        flash('Услуга успешно удалена!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении услуги: {str(e)}', 'error')
    
    return redirect(url_for('customer_services'))

@app.route('/customer/service/toggle/<int:service_id>')
@login_required
def toggle_service(service_id):
    """Включение/выключение услуги"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    service = Service.query.filter_by(id=service_id, customer_id=current_user.id).first()
    if not service:
        flash('Услуга не найдена', 'error')
        return redirect(url_for('customer_services'))
    
    try:
        service.is_active = not service.is_active
        db.session.commit()
        status = "активирована" if service.is_active else "деактивирована"
        flash(f'Услуга "{service.name}" {status}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при изменении статуса услуги: {str(e)}', 'error')
    
    return redirect(url_for('customer_services'))

# ================== ЛИЧНЫЙ КАБИНЕТ КЛИЕНТА - МОИ УСЛУГИ ==================

@app.route('/client/services')
@login_required
def client_services():
    """Страница моих услуг для клиента"""
    if current_user.role != 'client':
        flash('Доступ запрещен. Только для клиентов.', 'error')
        return redirect(url_for('index'))
    
    # Получаем все доступные услуги
    all_services = Service.query.filter_by(is_active=True).all()
    
    # Получаем услуги, подключенные текущим клиентом
    user_services = UserService.query.filter_by(user_id=current_user.id).all()
    connected_service_ids = [us.service_id for us in user_services]
    
    return render_template('client_services.html', 
                         services=all_services,
                         connected_service_ids=connected_service_ids,
                         user_services=user_services)

@app.route('/client/service/connect/<int:service_id>')
@login_required
def connect_service(service_id):
    """Подключение услуги клиентом"""
    if current_user.role != 'client':
        flash('Доступ запрещен. Только для клиентов.', 'error')
        return redirect(url_for('index'))
    
    service = Service.query.filter_by(id=service_id, is_active=True).first()
    if not service:
        flash('Услуга не найдена или неактивна', 'error')
        return redirect(url_for('client_services'))
    
    # Проверяем, не подключена ли уже услуга
    existing_connection = UserService.query.filter_by(
        user_id=current_user.id, 
        service_id=service_id
    ).first()
    
    if existing_connection:
        flash('Услуга уже подключена', 'info')
        return redirect(url_for('client_services'))
    
    # Проверяем баланс
    if current_user.balance < service.price:
        flash('Недостаточно средств на балансе', 'error')
        return redirect(url_for('client_services'))
    
    try:
        # Списываем средства
        current_user.balance -= service.price
        
        # Подключаем услугу
        user_service = UserService(
            user_id=current_user.id,
            service_id=service_id,
            price_at_connection=service.price,
            is_active=True
        )
        db.session.add(user_service)
        db.session.commit()
        
        flash(f'Услуга "{service.name}" успешно подключена!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при подключении услуги: {str(e)}', 'error')
    
    return redirect(url_for('client_services'))

@app.route('/client/service/disconnect/<int:service_id>')
@login_required
def disconnect_service(service_id):
    """Отключение услуги клиентом"""
    if current_user.role != 'client':
        flash('Доступ запрещен. Только для клиентов.', 'error')
        return redirect(url_for('index'))
    
    user_service = UserService.query.filter_by(
        user_id=current_user.id, 
        service_id=service_id
    ).first()
    
    if not user_service:
        flash('Услуга не подключена', 'error')
        return redirect(url_for('client_services'))
    
    try:
        # Возвращаем средства (50% от стоимости)
        refund_amount = user_service.price_at_connection * 0.5
        current_user.balance += refund_amount
        
        # Удаляем подключение
        db.session.delete(user_service)
        db.session.commit()
        
        flash(f'Услуга отключена. Возвращено {refund_amount:.2f} руб.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при отключении услуги: {str(e)}', 'error')
    
    return redirect(url_for('client_services'))

@app.route('/client/add_balance', methods=['POST'])
@login_required
def add_balance():
    """Пополнение баланса клиента"""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    try:
        amount = float(request.form.get('amount', 0))
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Сумма должна быть положительной'}), 400
        
        current_user.balance += amount
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'new_balance': current_user.balance,
            'message': f'Баланс пополнен на {amount} руб.'
        })
        
    except ValueError:
        return jsonify({'success': False, 'message': 'Неверная сумма'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ================== СОЗДАНИЕ БАЗЫ ДАННЫХ ==================

def create_tables():
    """Создание таблиц в базе данных с тестовыми данными"""
    with app.app_context():
        db.create_all()
        
        # Создаем тестового администратора
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
        
        # Создаем тестового заказчика
        if not User.query.filter_by(username='customer1').first():
            customer = User(username='customer1', email='customer1@example.com', role='customer')
            customer.set_password('cust123')
            db.session.add(customer)
            db.session.flush()
            
            # Создаем стандартные услуги
            services = [
                {
                    'name': 'Пинг сервера',
                    'description': 'Мониторинг доступности серверов с отправкой уведомлений о простоях',
                    'price': 299.99
                },
                {
                    'name': 'Слежка за погодой', 
                    'description': 'Прогноз погоды и уведомления об изменениях погодных условий',
                    'price': 199.99
                },
                {
                    'name': 'Порт чекер',
                    'description': 'Проверка открытых портов и мониторинг сетевой безопасности',
                    'price': 399.99
                }
            ]
            
            for service_data in services:
                service = Service(
                    name=service_data['name'],
                    description=service_data['description'],
                    price=service_data['price'],
                    customer_id=customer.id
                )
                db.session.add(service)
        
        # Создаем тестового клиента
        if not User.query.filter_by(username='client1').first():
            client = User(username='client1', email='client1@example.com', role='client', balance=1000.0)
            client.set_password('client123')
            db.session.add(client)
        
        db.session.commit()
        print('✅ База данных инициализирована с тестовыми данными')
        print('👑 Администратор: admin / admin123')
        print('👔 Заказчик: customer1 / cust123')
        print('👤 Клиент: client1 / client123 (баланс: 1000 руб.)')

if __name__ == '__main__':
    create_tables()
    app.run(debug=True)