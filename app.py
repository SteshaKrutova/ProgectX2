import atexit
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from flask_mail import Mail, Message
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta  # Добавьте timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import requests  # Добавьте этот импорт
import os
from dotenv import load_dotenv  # Добавьте этот импорт

# Инициализация приложения
app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'instance', 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Конфигурация Email
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')  # Ваш email
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')  # Пароль приложения
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# Инициализация расширений
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'
# Инициализация Flask-Mail для email уведомлений
mail = Mail(app)


# Функция отправки email
def send_email(to, subject, template, **kwargs):
    """
    Отправка email уведомления
    :param to: Email получателя
    :param subject: Тема письма
    :param template: Шаблон письма (текстовый)
    :param kwargs: Дополнительные параметры для шаблона
    """
    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            html=template.format(**kwargs),
            charset='utf-8'
        )
        mail.send(msg)
        app.logger.info(f"Email отправлен на {to}")
    except Exception as e:
        app.logger.error(f"Ошибка отправки email: {str(e)}")

# Шаблоны email сообщений
EMAIL_TEMPLATES = {
    'service_connected': {
        'subject': '✅ Услуга подключена - ProjectX2',
        'template': '''
        <h2>Услуга успешно подключена!</h2>
        <p>Здравствуйте, {username}!</p>
        <p>Вы успешно подключили услугу <strong>"{service_name}"</strong>.</p>
        <p><strong>Стоимость:</strong> {price} руб.</p>
        <p><strong>Дата подключения:</strong> {connection_date}</p>
        <p><strong>Описание услуги:</strong><br>{description}</p>
        <hr>
        <p>С уважением,<br>Команда ProjectX2</p>
        '''
    },
    'service_disconnected': {
        'subject': '❌ Услуга отключена - ProjectX2',
        'template': '''
        <h2>Услуга отключена</h2>
        <p>Здравствуйте, {username}!</p>
        <p>Вы отключили услугу <strong>"{service_name}"</strong>.</p>
        <p><strong>Возвращено средств:</strong> {refund_amount} руб.</p>
        <p><strong>Дата отключения:</strong> {disconnection_date}</p>
        <hr>
        <p>С уважением,<br>Команда ProjectX2</p>
        '''
    },
    'balance_replenished': {
        'subject': '💰 Баланс пополнен - ProjectX2',
        'template': '''
        <h2>Баланс успешно пополнен</h2>
        <p>Здравствуйте, {username}!</p>
        <p>Ваш баланс был пополнен на <strong>{amount} руб.</strong></p>
        <p><strong>Текущий баланс:</strong> {new_balance} руб.</p>
        <p><strong>Дата операции:</strong> {operation_date}</p>
        <hr>
        <p>С уважением,<br>Команда ProjectX2</p>
        '''
    },
    # Добавьте в EMAIL_TEMPLATES
    'new_customer_connection': {
        'subject': '🎉 Новое подключение услуги - ProjectX2',
    'template': '''
    <h2>Новая услуга подключена!</h2>
    <p>Здравствуйте!</p>
    <p>Клиент <strong>{client_name}</strong> подключил вашу услугу <strong>"{service_name}"</strong>.</p>
    <p><strong>Стоимость:</strong> {price} руб.</p>
    <p><strong>Дата подключения:</strong> {connection_date}</p>
    <p><strong>Email клиента:</strong> {client_email}</p>
    <hr>
    <p>С уважением,<br>Команда ProjectX2</p>
    '''
}   
}

# Модели базы данных
# определения моделей базы данных
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

class UsedPromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    promo_code = db.Column(db.String(50), nullable=False)
    used_at = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    
    user = db.relationship('User', backref=db.backref('used_promo_codes', lazy=True))

    def __repr__(self):
        return f'<UsedPromoCode {self.promo_code} by User {self.user_id}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'expense' или 'refund'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=True)
    
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))
    service = db.relationship('Service', backref=db.backref('transactions', lazy=True))

    def __repr__(self):
        return f'<Transaction {self.type} {self.amount} by User {self.user_id}>'
    
class PromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)  # Любые символы
    amount = db.Column(db.Float, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    creator = db.relationship('User', backref=db.backref('created_promo_codes', lazy=True))

    def __repr__(self):
        return f'<PromoCode {self.code} - {self.amount} руб.>'
    
class PingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # IPv6 поддерживает до 45 символов
    result = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('ping_history', lazy=True))

    def __repr__(self):
        return f'<PingHistory {self.ip_address} by User {self.user_id}>'
    
class ServerMonitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    is_online = db.Column(db.Boolean, default=True)
    last_check = db.Column(db.DateTime, default=datetime.utcnow)
    last_notification = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('monitored_servers', lazy=True))

    def __repr__(self):
        return f'<ServerMonitor {self.ip_address} - {"Online" if self.is_online else "Offline"}>'
    
class WeatherMonitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    last_check = db.Column(db.DateTime, default=datetime.utcnow)
    last_notification = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('weather_monitors', lazy=True))

    def __repr__(self):
        return f'<WeatherMonitor {self.city} - User {self.user_id}>'
    
def get_weather_data(city):
    """Получение данных о погоде с OpenWeatherMap API"""
    try:
        API_KEY = os.environ.get('OPENWEATHER_API_KEY') or 'your_api_key_here'
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric&lang=ru"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            return {
                'success': True,
                'city': data['name'],
                'temperature': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'humidity': data['main']['humidity'],
                'description': data['weather'][0]['description'],
                'weather_main': data['weather'][0]['main'],
                'wind_speed': data['wind']['speed'],
                'uv_index': 2  # Для демо, в реальности нужно использовать другой API для UV
            }
        else:
            return {'success': False, 'error': data.get('message', 'Ошибка получения погоды')}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
def generate_weather_recommendations(weather_data):
    """Генерация рекомендаций на основе данных о погоде"""
    recommendations = []
    
    # Проверка УФ индекса
    if weather_data['uv_index'] > 2:
        recommendations.append("🧴 Используйте солнцезащитный крем (SPF)")
    
    # Проверка температуры
    if weather_data['temperature'] < 10:
        recommendations.append("🧣 Тепло оденьтесь")
    elif weather_data['temperature'] > 25:
        recommendations.append("🧢 Наденьте головной убор от солнца")
    
    # Проверка осадков
    if 'дождь' in weather_data['description'].lower() or weather_data['weather_main'] == 'Rain':
        recommendations.append("☂️ Возьмите зонт")
    elif weather_data['weather_main'] == 'Clear':
        recommendations.append("😎 Солнезащитные очки будут кстати")
    
    # Проверка ветра
    if weather_data['wind_speed'] > 5:
        recommendations.append("🧥 Ветровка не помешает")
    
    # Проверка мороза
    if weather_data['temperature'] < 0:
        recommendations.append("🧤 Не забудьте перчатки и гигиеническую помаду")
    
    return recommendations

def send_weather_report():
    """Функция для отправки ежедневного отчета о погоде"""
    with app.app_context():
        try:
            # Получаем всех пользователей с подключенной услугой погоды
            weather_service = Service.query.filter_by(name='Слежка за погодой').first()
            
            if weather_service:
                user_services = UserService.query.filter_by(
                    service_id=weather_service.id,
                    is_active=True
                ).all()
                
                for user_service in user_services:
                    user = user_service.user
                    weather_monitors = WeatherMonitor.query.filter_by(user_id=user.id).all()
                    
                    for monitor in weather_monitors:
                        weather_data = get_weather_data(monitor.city)
                        
                        if weather_data['success']:
                            recommendations = generate_weather_recommendations(weather_data)
                            
                            template_data = {
                                'subject': f'🌤️ Прогноз погоды в {weather_data["city"]} - ProjectX2',
                                'template': '''
                                <h2>Ежедневный прогноз погоды</h2>
                                <p>Здравствуйте, {username}!</p>
                                <p>Прогноз погоды в <strong>{city}</strong> на сегодня:</p>
                                
                                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 15px 0;">
                                    <p><strong>🌡️ Температура:</strong> {temperature}°C (ощущается как {feels_like}°C)</p>
                                    <p><strong>💧 Влажность:</strong> {humidity}%</p>
                                    <p><strong>🌬️ Ветер:</strong> {wind_speed} м/с</p>
                                    <p><strong>☀️ УФ индекс:</strong> {uv_index}</p>
                                    <p><strong>📝 Описание:</strong> {description}</p>
                                </div>
                                
                                <h3>🎯 Рекомендации:</h3>
                                <ul>
                                    {recommendations}
                                </ul>
                                
                                <p><strong>⏰ Время обновления:</strong> {update_time}</p>
                                <hr>
                                <p>С уважением,<br>Команда ProjectX2</p>
                                '''
                            }
                            
                            recommendations_html = ''
                            if recommendations:
                                recommendations_html = ''.join([f'<li>{rec}</li>' for rec in recommendations])
                            else:
                                recommendations_html = '<li>Отличная погода! Особых рекомендаций нет.</li>'
                            
                            send_email(
                                to=user.email,
                                subject=template_data['subject'],
                                template=template_data['template'],
                                username=user.username,
                                city=weather_data['city'],
                                temperature=weather_data['temperature'],
                                feels_like=weather_data['feels_like'],
                                humidity=weather_data['humidity'],
                                wind_speed=weather_data['wind_speed'],
                                uv_index=weather_data['uv_index'],
                                description=weather_data['description'],
                                recommendations=recommendations_html,
                                update_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M')
                            )
                            
                            monitor.last_notification = datetime.utcnow()
                            db.session.commit()
                            
        except Exception as e:
            app.logger.error(f'Ошибка отправки отчета о погоде: {str(e)}')
def check_monitored_servers():
    """Функция для периодической проверки серверов"""
    with app.app_context():
        servers_to_check = ServerMonitor.query.filter(
            ServerMonitor.last_check < datetime.utcnow() - timedelta(minutes=5)
        ).all()
        
        for server in servers_to_check:
            try:
                import platform
                import subprocess
                
                param = '-n' if platform.system().lower() == 'windows' else '-c'
                command = ['ping', param, '4', server.ip_address]
                
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                is_online = result.returncode == 0
                
                # Если статус изменился
                if server.is_online != is_online:
                    server.is_online = is_online
                    server.last_notification = datetime.utcnow()
                    
                    # Отправляем мгновенное уведомление о смене статуса
                    template_data = {
                        'subject': '⚠️ Изменение статуса сервера - ProjectX2' if not is_online else '✅ Сервер доступен - ProjectX2',
                        'template': '''
                        <h2>{title}</h2>
                        <p>Здравствуйте, {username}!</p>
                        <p>Статус сервера <strong>{ip_address}</strong> изменился.</p>
                        <p><strong>Новый статус:</strong> {status}</p>
                        <p><strong>Время изменения:</strong> {change_time}</p>
                        <p><strong>Результат ping:</strong></p>
                        <pre>{ping_result}</pre>
                        <hr>
                        <p>С уважением,<br>Команда ProjectX2</p>
                        '''
                    }
                    
                    send_email(
                        to=server.user.email,
                        subject=template_data['subject'],
                        template=template_data['template'],
                        username=server.user.username,
                        ip_address=server.ip_address,
                        title='Сервер стал недоступен' if not is_online else 'Сервер снова доступен',
                        status='Недоступен ❌' if not is_online else 'Доступен ✅',
                        change_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M'),
                        ping_result=result.stdout if result.returncode == 0 else result.stderr
                    )
                
                # Ежечасное уведомление о доступности
                elif (server.last_notification is None or 
                      server.last_notification < datetime.utcnow() - timedelta(hours=1)):
                    if server.is_online:
                        template_data = {
                            'subject': '📊 Сервер доступен - ProjectX2',
                            'template': '''
                            <h2>Сервер доступен</h2>
                            <p>Здравствуйте, {username}!</p>
                            <p>Сервер <strong>{ip_address}</strong> работает стабильно.</p>
                            <p><strong>Статус:</strong> Доступен ✅</p>
                            <p><strong>Последняя проверка:</strong> {check_time}</p>
                            <p><strong>Результат ping:</strong></p>
                            <pre>{ping_result}</pre>
                            <hr>
                            <p>С уважением,<br>Команда ProjectX2</p>
                            '''
                        }
                        
                        send_email(
                            to=server.user.email,
                            subject=template_data['subject'],
                            template=template_data['template'],
                            username=server.user.username,
                            ip_address=server.ip_address,
                            check_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M'),
                            ping_result=result.stdout
                        )
                    
                    server.last_notification = datetime.utcnow()
                
                server.last_check = datetime.utcnow()
                db.session.commit()
                
            except Exception as e:
                app.logger.error(f'Ошибка проверки сервера {server.ip_address}: {str(e)}')

# Планировщик задач
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_monitored_servers, trigger="interval", minutes=5)
scheduler.add_job(func=send_weather_report, trigger="cron", hour=7, minute=0)
scheduler.start()
atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)



# Загрузчик пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Маршруты
@app.route('/')
def index():
    if current_user.is_authenticated:
        # Статистика для дашборда
        active_services_count = Service.query.filter_by(is_active=True).count()
        total_connections = UserService.query.filter_by(is_active=True).count()
        
        # Расчет оборота (сумма всех подключенных услуг)
        total_revenue = db.session.query(db.func.sum(UserService.price_at_connection)).scalar() or 0
        
        # Последняя активность (последние 5 подключений)
        recent_connections = UserService.query.order_by(UserService.connected_at.desc()).limit(5).all()
        recent_activity = len(recent_connections)
        
        # Формируем список последних активностей
        recent_activities = []
        for conn in recent_connections:
            recent_activities.append({
                'icon': '✅',
                'message': f'Пользователь {conn.user.username} подключил услугу "{conn.service.name}"',
                'timestamp': conn.connected_at.strftime('%d.%m.%Y %H:%M')
            })
        
        return render_template('index.html',
                             active_services_count=active_services_count,
                             total_connections=total_connections,
                             total_revenue=total_revenue,
                             recent_activity=recent_activity,
                             recent_activities=recent_activities)
    
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
        
        # Проверка активности аккаунта
        if not user.is_active:
            flash('Данный аккаунт заблокирован. Обратитесь к администратору.', 'error')
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
        
        # Все новые пользователи автоматически становятся клиентами
        role = 'client'
        
        errors = []
        
        if not all([username, email, password, password_confirm]):
            errors.append('Все поля обязательны для заполнения.')
        
        if len(username) < 3:
            errors.append('Имя пользователя должно содержать минимум 3 символа.')
        
        if len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов.')
        
        if password != password_confirm:
            errors.append('Пароли не совпадают.')
        
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
            
            flash('Регистрация успешна! Теперь вы можете войти в систему.', 'success')
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

@app.route('/customer/stats')
@login_required
def customer_stats():
    """Страница статистики для заказчика"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    # Получаем услуги текущего заказчика
    services = Service.query.filter_by(customer_id=current_user.id).all()
    
    # Статистика
    active_services_count = Service.query.filter_by(
        customer_id=current_user.id, 
        is_active=True
    ).count()
    
    total_connections = UserService.query.join(Service).filter(
        Service.customer_id == current_user.id,
        UserService.is_active == True
    ).count()
    
    # Расчет общего дохода
    total_revenue = db.session.query(
        db.func.sum(UserService.price_at_connection)
    ).join(Service).filter(
        Service.customer_id == current_user.id
    ).scalar() or 0
    
    # Активность за последние 24 часа
    recent_activity = UserService.query.join(Service).filter(
        Service.customer_id == current_user.id,
        UserService.connected_at >= datetime.utcnow() - timedelta(hours=24)
    ).count()
    
    return render_template('customer_stats.html',
                         services=services,
                         active_services_count=active_services_count,
                         total_connections=total_connections,
                         total_revenue=total_revenue,
                         recent_activity=recent_activity)

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
    """Подключение услуги клиентом с отправкой уведомления"""
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
        
        # ★★★★ ДОБАВЛЯЕМ АВТОМАТИЧЕСКУЮ НАСТРОЙКУ САНКТ-ПЕТЕРБУРГА ★★★★
        if service.name == 'Слежка за погодой':
            # Создаем запись для мониторинга погоды в СПб по умолчанию
            weather_monitor = WeatherMonitor(
                user_id=current_user.id,
                city='Санкт-Петербург'
            )
            db.session.add(weather_monitor)
            flash('Автоматически настроен мониторинг погоды в Санкт-Петербурге!', 'info')
        
        db.session.commit()
        
        # Отправляем email уведомление о подключении услуги
        if service.name == 'Слежка за погодой':
            template_data = {
                'subject': '🌤️ Подключена слежка за погодой - ProjectX2',
                'template': '''
                <h2>Услуга "Слежка за погодой" подключена!</h2>
                <p>Здравствуйте, {username}!</p>
                <p>Вы подключили услугу: <strong>"{service_name}"</strong></p>
                <p><strong>Стоимость:</strong> {price} руб.</p>
                <p><strong>Описание:</strong> {description}</p>
                <p><strong>Дата подключения:</strong> {connection_date}</p>
                
                <h3>🎯 Автоматически настроено:</h3>
                <ul>
                    <li>📍 Город: <strong>Санкт-Петербург</strong></li>
                    <li>⏰ Ежедневные отчеты: <strong>7:00 утра</strong></li>
                </ul>
                
                <h3>📋 Возможности услуги:</h3>
                <ul>
                    <li>🌤️ Ежедневные отчеты о погоде</li>
                    <li>📧 Персональные рекомендации по одежде</li>
                    <li>🔔 Уведомления о необходимости SPF защиты</li>
                    <li>⏰ Проверка погоды по требованию</li>
                </ul>
                
                <h3>🎯 Что делать дальше:</h3>
                <ol>
                    <li>Проверьте первый отчет о погоде завтра в 7:00</li>
                    <li>Используйте кнопку "Проверить погоду" для мгновенных отчетов</li>
                    <li>При необходимости измените город в настройках</li>
                </ol>
                
                <hr>
                <p>С уважением,<br>Команда ProjectX2</p>
                '''
            }
        else:
            template_data = {
                'subject': '🎉 Услуга подключена - ProjectX2',
                'template': '''
                <h2>Услуга успешно подключена!</h2>
                <p>Здравствуйте, {username}!</p>
                <p>Вы подключили услугу: <strong>"{service_name}"</strong></p>
                <p><strong>Стоимость:</strong> {price} руб.</p>
                <p><strong>Описание:</strong> {description}</p>
                <p><strong>Дата подключения:</strong> {connection_date}</p>
                <h3>📋 Возможности услуги:</h3>
                <ul>
                    <li>🔍 Ping любых IP-адресов и доменов</li>
                    <li>📊 Мониторинг доступности серверов</li>
                    <li>📧 Уведомления о статусе серверов</li>
                    <li>📋 История выполненных проверок</li>
                </ul>
                <p>Для начала работы перейдите в <a href="{ping_url}">раздел Ping сервиса</a></p>
                <hr>
                <p>С уважением,<br>Команда ProjectX2</p>
                '''
            }
        
        send_email(
            to=current_user.email,
            subject=template_data['subject'],
            template=template_data['template'],
            username=current_user.username,
            service_name=service.name,
            price=service.price,
            description=service.description,
            connection_date=datetime.utcnow().strftime('%d.%m.%Y %H:%M'),
            ping_url=url_for('ping_service', _external=True)
        )
        
        flash(f'Услуга "{service.name}" успешно подключена! Проверьте указанную почту для подробностей.', 'success')
        
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
    
    user_service = db.session.query(UserService).options(
    selectinload(UserService.service)  # Явно загружаем связанный объект service
).filter_by(
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
        
        # Отправляем email уведомление :cite[7]
        template_data = EMAIL_TEMPLATES['service_disconnected']
        send_email(
            to=current_user.email,
            subject=template_data['subject'],
            template=template_data['template'],
            username=current_user.username,
            service_name=user_service.service.name,
            refund_amount=refund_amount,
            disconnection_date=datetime.utcnow().strftime('%d.%m.%Y %H:%M')
        )
        
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
        
        # Отправляем email уведомление :cite[7]
        template_data = EMAIL_TEMPLATES['balance_replenished']
        send_email(
            to=current_user.email,
            subject=template_data['subject'],
            template=template_data['template'],
            username=current_user.username,
            amount=amount,
            new_balance=current_user.balance,
            operation_date=datetime.utcnow().strftime('%d.%m.%Y %H:%M')
        )
        
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
    
##для админов
@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    """Добавление нового пользователя администратором"""
    if current_user.role != 'admin':
        flash('Доступ запрещен. Только для администраторов.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        role = request.form.get('role', '').strip()
        balance = request.form.get('balance', '0').strip()
        
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
        
        try:
            balance = float(balance)
            if balance < 0:
                errors.append('Баланс не может быть отрицательным.')
        except ValueError:
            errors.append('Неверный формат баланса.')
        
        if User.query.filter_by(username=username).first():
            errors.append('Пользователь с таким именем уже существует.')
        
        if User.query.filter_by(email=email).first():
            errors.append('Пользователь с таким email уже существует.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('admin_add_user.html')
        
        try:
            new_user = User(
                username=username,
                email=email,
                role=role,
                balance=balance
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            flash(f'Пользователь {username} успешно создан!', 'success')
            return redirect(url_for('admin_users'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла ошибка при создании пользователя: {str(e)}', 'error')
            return render_template('admin_add_user.html')
    
    return render_template('admin_add_user.html')

@app.route('/add-balance')
@login_required
def add_balance_page():
    """Страница пополнения баланса"""
    if current_user.role != 'client':
        flash('Эта страница доступна только клиентам', 'error')
        return redirect(url_for('index'))
    
    # Проверяем, использовал ли пользователь уже промокод
    promo_used = UsedPromoCode.query.filter_by(
        user_id=current_user.id, 
        promo_code='progectx2'
    ).first() is not None
    
    return render_template('add_balance.html', promo_used=promo_used)

@app.route('/apply-promo', methods=['POST'])
@login_required
def apply_promo():
    if current_user.role != 'client':
        flash('Эта функция доступна только клиентам', 'error')
        return redirect(url_for('index'))
    
    promo_code = request.form.get('promo_code', '').strip()
    
    # Ищем промокод в базе данных (точное совпадение)
    promo = PromoCode.query.filter_by(code=promo_code, is_active=True).first()
    
    if promo:
        # Проверяем, не использовал ли уже пользователь этот промокод
        already_used = UsedPromoCode.query.filter_by(
            user_id=current_user.id, 
            promo_code=promo_code
        ).first()
        
        if already_used:
            flash('❌ Вы уже использовали этот промокод ранее', 'error')
        else:
            # Добавляем бонус и записываем использование
            current_user.balance += promo.amount
            new_used_promo = UsedPromoCode(
                user_id=current_user.id,
                promo_code=promo_code,
                amount=promo.amount
            )
            db.session.add(new_used_promo)
            db.session.commit()
            flash(f'🎉 Промокод успешно активирован! На ваш баланс добавлено {promo.amount} рублей.', 'success')
    else:
        flash('❌ Неверный промокод', 'error')
    
    return redirect(url_for('add_balance_page'))

@app.route('/client/expense-history')
@login_required
def expense_history():
    """Страница истории расходов клиента"""
    if current_user.role != 'client':
        flash('Эта страница доступна только клиентам', 'error')
        return redirect(url_for('index'))
    
    # Получаем подключенные услуги пользователя
    user_services = UserService.query.filter_by(user_id=current_user.id).all()
    
    return render_template('expense_history.html', 
                         user_services=user_services,
                         user=current_user)

# Блокировка/разблокировка пользователя
@app.route('/admin/user/toggle/<int:user_id>')
@login_required
def toggle_user(user_id):
    """Блокировка/разблокировка пользователя"""
    if current_user.role != 'admin':
        flash('Доступ запрещен. Только для администраторов.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Нельзя заблокировать собственный аккаунт', 'error')
        return redirect(url_for('admin_users'))
    
    try:
        user.is_active = not user.is_active
        db.session.commit()
        
        status = "разблокирован" if user.is_active else "заблокирован"
        flash(f'Пользователь {user.username} {status}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при изменении статуса пользователя: {str(e)}', 'error')
    
    return redirect(url_for('admin_users'))

# Добавим проверку в декоратор login_required или в начало каждой функции
@app.before_request
def check_user_active():
    if current_user.is_authenticated and not current_user.is_active:
        logout_user()
        flash('Ваш аккаунт заблокирован. Обратитесь к администратору.', 'error')
        return redirect(url_for('login'))
    
@app.route('/admin/user/delete/<int:user_id>')
@login_required
def delete_user(user_id):
    """Полное удаление пользователя из системы"""
    if current_user.role != 'admin':
        flash('Доступ запрещен. Только для администраторов.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Нельзя удалить собственный аккаунт', 'error')
        return redirect(url_for('admin_users'))
    
    try:
        # Удаляем все связанные данные пользователя
        UserService.query.filter_by(user_id=user_id).delete()
        UsedPromoCode.query.filter_by(user_id=user_id).delete()
        Transaction.query.filter_by(user_id=user_id).delete()
        
        # Удаляем самого пользователя
        db.session.delete(user)
        db.session.commit()
        
        flash(f'Пользователь {user.username} полностью удален из системы!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении пользователя: {str(e)}', 'error')
    
    return redirect(url_for('admin_users'))
# система  промокодов для заказчиков
@app.route('/customer/promo-codes')
@login_required
def customer_promo_codes():
    """Страница управления промокодами для заказчика"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    promo_codes = PromoCode.query.filter_by(created_by=current_user.id).order_by(PromoCode.created_at.desc()).all()
    return render_template('customer_promo_codes.html', promo_codes=promo_codes)

@app.route('/customer/promo-code/create', methods=['POST'])
@login_required
def create_promo_code():
    """Создание промокода"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('customer_promo_codes'))
    
    code = request.form.get('code', '').strip()
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Неверная сумма промокода', 'error')
        return redirect(url_for('customer_promo_codes'))
    
    if not code or amount <= 0:
        flash('Все поля обязательны для заполнения', 'error')
        return redirect(url_for('customer_promo_codes'))
    
    # Проверяем, не существует ли уже такой промокод (без приведения к верхнему регистру)
    existing_promo = PromoCode.query.filter_by(code=code).first()
    if existing_promo:
        flash('Промокод с таким названием уже существует', 'error')
        return redirect(url_for('customer_promo_codes'))
    
    try:
        new_promo = PromoCode(
            code=code,
            amount=amount,
            created_by=current_user.id
        )
        db.session.add(new_promo)
        db.session.commit()
        flash('Промокод успешно создан!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при создании промокода: {str(e)}', 'error')
    
    return redirect(url_for('customer_promo_codes'))

@app.route('/customer/promo-code/toggle/<int:promo_id>')
@login_required
def toggle_promo_code(promo_id):
    """Активация/деактивация промокода"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    promo_code = PromoCode.query.filter_by(id=promo_id, created_by=current_user.id).first()
    if not promo_code:
        flash('Промокод не найден', 'error')
        return redirect(url_for('customer_promo_codes'))
    
    try:
        promo_code.is_active = not promo_code.is_active
        db.session.commit()
        status = "активирован" if promo_code.is_active else "деактивирован"
        flash(f'Промокод "{promo_code.code}" {status}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при изменении статуса промокода: {str(e)}', 'error')
    
    return redirect(url_for('customer_promo_codes'))

@app.route('/customer/promo-code/delete/<int:promo_id>')
@login_required
def delete_promo_code(promo_id):
    """Удаление промокода"""
    if current_user.role != 'customer':
        flash('Доступ запрещен. Только для заказчиков.', 'error')
        return redirect(url_for('index'))
    
    promo_code = PromoCode.query.filter_by(id=promo_id, created_by=current_user.id).first()
    if not promo_code:
        flash('Промокод не найден', 'error')
        return redirect(url_for('customer_promo_codes'))
    
    try:
        db.session.delete(promo_code)
        db.session.commit()
        flash('Промокод успешно удален!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении промокода: {str(e)}', 'error')
    
    return redirect(url_for('customer_promo_codes'))

#Создадим маршруты для услуги Ping
@app.route('/client/ping')
@login_required
def ping_service():
    """Страница услуги Ping"""
    if current_user.role != 'client':
        flash('Доступ запрещен. Только для клиентов.', 'error')
        return redirect(url_for('index'))
    
    # Проверяем, подключена ли услуга Ping у пользователя
    ping_service = Service.query.filter_by(name='Пинг сервера').first()
    if not ping_service:
        flash('Услуга "Пинг сервера" не найдена в системе', 'error')
        return redirect(url_for('client_services'))
    
    user_has_service = UserService.query.filter_by(
        user_id=current_user.id, 
        service_id=ping_service.id
    ).first()
    
    if not user_has_service:
        flash('У вас не подключена услуга "Пинг сервера"', 'error')
        return redirect(url_for('client_services'))
    
    # Получаем историю пингов пользователя
    ping_history = PingHistory.query.filter_by(user_id=current_user.id)\
        .order_by(PingHistory.created_at.desc())\
        .limit(10)\
        .all()
    
    return render_template('ping_service.html', 
                         ping_history=ping_history,
                         user=current_user)

@app.route('/client/ping/execute', methods=['POST'])
@login_required
def execute_ping():
    """Выполнение ping команды и мониторинг сервера с отправкой уведомления"""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    ip_address = request.form.get('ip_address', '').strip()
    
    if not ip_address:
        return jsonify({'success': False, 'message': 'Введите IP-адрес'}), 400
    
    # Валидация IP-адреса
    try:
        import socket
        socket.inet_pton(socket.AF_INET, ip_address)
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, ip_address)
        except socket.error:
            # Проверяем, может быть это домен
            try:
                socket.gethostbyname(ip_address)
            except socket.error:
                return jsonify({'success': False, 'message': 'Неверный формат IP-адреса или домена'}), 400
    
    try:
        # Выполняем ping с правильной кодировкой
        import platform
        import subprocess
        
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '4', ip_address]
        
        # Устанавливаем правильную кодировку для Windows
        if platform.system().lower() == 'windows':
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='cp866')
        else:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, encoding='utf-8')
        
        is_online = result.returncode == 0
        ping_result = result.stdout if is_online else result.stderr
        
        # Конвертируем результат в английский если нужно (для Windows)
        if platform.system().lower() == 'windows' and 'ЋвўҐв' in ping_result:
            # Простая замена русских фраз на английские
            ping_result = ping_result.replace('ЋвўҐв ®в', 'Reply from')
            ping_result = ping_result.replace('зЁб«® Ў ©в=', 'bytes=')
            ping_result = ping_result.replace('ўаҐ¬п=', 'time=')
            ping_result = ping_result.replace('¬б', 'ms')
            ping_result = ping_result.replace('‘в вЁбвЁЄ Ping', 'Ping statistics')
            ping_result = ping_result.replace('Џ ЄҐв®ў: ®вЇа ў«Ґ® =', 'Packets: Sent =')
            ping_result = ping_result.replace('Ї®«гзҐ® =', 'Received =')
            ping_result = ping_result.replace('Ї®вҐап® =', 'Lost =')
            ping_result = ping_result.replace('ЏаЁЎ«Ё§ЁвҐ«м®Ґ ўаҐ¬п ЇаЁҐ¬ -ЇҐаҐ¤ зЁ ў ¬б:', 'Approximate round trip times in milli-seconds:')
            ping_result = ping_result.replace('ЊЁЁ¬ «м®Ґ =', 'Minimum =')
            ping_result = ping_result.replace('Њ ЄбЁ¬ «м®Ґ =', 'Maximum =')
            ping_result = ping_result.replace('‘аҐ¤ҐҐ =', 'Average =')
            ping_result = ping_result.replace('¬бҐЄ', 'ms')
        
        # Сохраняем результат в историю
        ping_record = PingHistory(
            user_id=current_user.id,
            ip_address=ip_address,
            result=ping_result
        )
        db.session.add(ping_record)
        
        # Отправляем email уведомление о результате ping
        template_data = {
            'subject': '✅ Ping выполнен успешно - ProjectX2' if is_online else '❌ Ping не удался - ProjectX2',
            'template': '''
            <h2>Результат выполнения Ping</h2>
            <p>Здравствуйте, {username}!</p>
            <p>Результат ping для <strong>{ip_address}</strong>:</p>
            <p><strong>Статус:</strong> {status}</p>
            <p><strong>Время выполнения:</strong> {ping_time}</p>
            <p><strong>Результат:</strong></p>
            <pre style="background: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto;">{ping_result}</pre>
            <p><strong>Команда:</strong> {command}</p>
            <hr>
            <p>С уважением,<br>Команда ProjectX2</p>
            '''
        }
        
        send_email(
            to=current_user.email,
            subject=template_data['subject'],
            template=template_data['template'],
            username=current_user.username,
            ip_address=ip_address,
            status='Доступен ✅' if is_online else 'Недоступен ❌',
            ping_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S'),
            ping_result=ping_result,
            command=' '.join(command)
        )
        
        # Проверяем, мониторится ли уже этот сервер
        server_monitor = ServerMonitor.query.filter_by(
            user_id=current_user.id,
            ip_address=ip_address
        ).first()
        
        if not server_monitor:
            # Первое добавление сервера для мониторинга
            server_monitor = ServerMonitor(
                user_id=current_user.id,
                ip_address=ip_address,
                is_online=is_online,
                last_notification=datetime.utcnow() if not is_online else None
            )
            db.session.add(server_monitor)
            
            # Отправляем письмо о начале мониторинга
            monitor_template = {
                'subject': '🚀 Начало мониторинга сервера - ProjectX2',
                'template': '''
                <h2>Мониторинг сервера активирован!</h2>
                <p>Здравствуйте, {username}!</p>
                <p>Мы начали мониторить сервер <strong>{ip_address}</strong>.</p>
                <p><strong>Статус:</strong> {status}</p>
                <p><strong>Дата начала мониторинга:</strong> {start_date}</p>
                <p>Вы будете получать уведомления:</p>
                <ul>
                    <li>📧 Ежечасно о доступности сервера</li>
                    <li>⚠️ Мгновенно при недоступности сервера</li>
                    <li>📋 После каждого выполненного ping</li>
                </ul>
                <hr>
                <p>С уважением,<br>Команда ProjectX2</p>
                '''
            }
            
            send_email(
                to=current_user.email,
                subject=monitor_template['subject'],
                template=monitor_template['template'],
                username=current_user.username,
                ip_address=ip_address,
                status='Доступен' if is_online else 'Недоступен',
                start_date=datetime.utcnow().strftime('%d.%m.%Y %H:%M')
            )
            
            flash('✅ Проверьте указанную почту! Начался мониторинг сервера.', 'success')
        
        else:
            # Обновляем статус существующего мониторинга
            server_monitor.is_online = is_online
            server_monitor.last_check = datetime.utcnow()
        
        db.session.commit()
        
        if is_online:
            return jsonify({
                'success': True, 
                'result': ping_result,
                'message': 'Ping выполнен успешно. Проверьте почту для подробностей.'
            })
        else:
            return jsonify({
                'success': False, 
                'result': ping_result,
                'message': 'Ping не удался. Проверьте почту для подробностей.'
            })
            
    except subprocess.TimeoutExpired:
        # Отправляем уведомление о таймауте
        timeout_template = {
            'subject': '⏰ Таймаут выполнения Ping - ProjectX2',
            'template': '''
            <h2>Таймаут выполнения Ping</h2>
            <p>Здравствуйте, {username}!</p>
            <p>Ping для <strong>{ip_address}</strong> превысил время ожидания.</p>
            <p><strong>Время выполнения:</strong> {ping_time}</p>
            <p><strong>Статус:</strong> Таймаут ⏰</p>
            <p>Возможные причины:</p>
            <ul>
                <li>Сервер не отвечает</li>
                <li>Проблемы с сетью</li>
                <li>Блокировка ICMP запросов</li>
            </ul>
            <hr>
            <p>С уважением,<br>Команда ProjectX2</p>
            '''
        }
        
        send_email(
            to=current_user.email,
            subject=timeout_template['subject'],
            template=timeout_template['template'],
            username=current_user.username,
            ip_address=ip_address,
            ping_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')
        )
        
        return jsonify({'success': False, 'message': 'Таймаут выполнения ping. Проверьте почту для подробностей.'}), 408
        
    except Exception as e:
        # Отправляем уведомление об ошибке
        error_template = {
            'subject': '❌ Ошибка выполнения Ping - ProjectX2',
            'template': '''
            <h2>Ошибка выполнения Ping</h2>
            <p>Здравствуйте, {username}!</p>
            <p>При выполнении ping для <strong>{ip_address}</strong> произошла ошибка.</p>
            <p><strong>Время выполнения:</strong> {ping_time}</p>
            <p><strong>Ошибка:</strong> {error_message}</p>
            <hr>
            <p>С уважением,<br>Команда ProjectX2</p>
            '''
        }
        
        send_email(
            to=current_user.email,
            subject=error_template['subject'],
            template=error_template['template'],
            username=current_user.username,
            ip_address=ip_address,
            ping_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S'),
            error_message=str(e)
        )
        
        return jsonify({'success': False, 'message': f'Ошибка выполнения: {str(e)}. Проверьте почту для подробностей.'}), 500
    
# маршруты для управления погодой
@app.route('/client/weather/set_city', methods=['POST'])
@login_required
def set_weather_city():
    """Установка города для слежки за погодой"""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    city = request.form.get('city', '').strip()
    
    if not city:
        return jsonify({'success': False, 'message': 'Введите город'}), 400
    
    # Проверяем, подключена ли услуга погоды
    weather_service = Service.query.filter_by(name='Слежка за погодой').first()
    if not weather_service:
        return jsonify({'success': False, 'message': 'Услуга не найдена'}), 404
    
    user_has_service = UserService.query.filter_by(
        user_id=current_user.id, 
        service_id=weather_service.id
    ).first()
    
    if not user_has_service:
        return jsonify({'success': False, 'message': 'Услуга не подключена'}), 403
    
    try:
        # Проверяем, существует ли уже мониторинг для этого города
        weather_monitor = WeatherMonitor.query.filter_by(
            user_id=current_user.id,
            city=city
        ).first()
        
        if not weather_monitor:
            weather_monitor = WeatherMonitor(
                user_id=current_user.id,
                city=city
            )
            db.session.add(weather_monitor)
            db.session.commit()
            
            flash(f'Начался мониторинг погоды в городе {city}! Отчеты будут приходить ежедневно в 7:00.', 'success')
        else:
            flash(f'Мониторинг погоды в городе {city} уже активен.', 'info')
            
        return jsonify({'success': True, 'message': 'Город установлен'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/client/weather/check')
@login_required
def check_weather_now():
    """Проверка погоды по требованию"""
    if current_user.role != 'client':
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    weather_service = Service.query.filter_by(name='Слежка за погодой').first()
    if not weather_service:
        flash('Услуга не найдена', 'error')
        return redirect(url_for('client_services'))
    
    user_has_service = UserService.query.filter_by(
        user_id=current_user.id, 
        service_id=weather_service.id
    ).first()
    
    if not user_has_service:
        flash('Услуга не подключена', 'error')
        return redirect(url_for('client_services'))
    
    weather_monitor = WeatherMonitor.query.filter_by(user_id=current_user.id).first()
    
    if not weather_monitor:
        flash('Сначала установите город для мониторинга', 'error')
        return redirect(url_for('client_services'))
    
    try:
        weather_data = get_weather_data(weather_monitor.city)
        
        if weather_data['success']:
            recommendations = generate_weather_recommendations(weather_data)
            
            # Отправляем email
            template_data = {
                'subject': f'🌤️ Проверка погоды в {weather_data["city"]} - ProjectX2',
                'template': '''
                <h2>Проверка погоды по вашему запросу</h2>
                <p>Здравствуйте, {username}!</p>
                <p>Текущая погода в <strong>{city}</strong>:</p>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 15px 0;">
                    <p><strong>🌡️ Температура:</strong> {temperature}°C (ощущается как {feels_like}°C)</p>
                    <p><strong>💧 Влажность:</strong> {humidity}%</p>
                    <p><strong>🌬️ Ветер:</strong> {wind_speed} м/с</p>
                    <p><strong>☀️ УФ индекс:</strong> {uv_index}</p>
                    <p><strong>📝 Описание:</strong> {description}</p>
                </div>
                
                <h3>🎯 Рекомендации:</h3>
                <ul>
                    {recommendations}
                </ul>
                
                <p><strong>⏰ Время проверки:</strong> {check_time}</p>
                <hr>
                <p>С уважением,<br>Команда ProjectX2</p>
                '''
            }
            
            recommendations_html = ''
            if recommendations:
                recommendations_html = ''.join([f'<li>{rec}</li>' for rec in recommendations])
            else:
                recommendations_html = '<li>Отличная погода! Особых рекомендаций нет.</li>'
            
            send_email(
                to=current_user.email,
                subject=template_data['subject'],
                template=template_data['template'],
                username=current_user.username,
                city=weather_data['city'],
                temperature=weather_data['temperature'],
                feels_like=weather_data['feels_like'],
                humidity=weather_data['humidity'],
                wind_speed=weather_data['wind_speed'],
                uv_index=weather_data['uv_index'],
                description=weather_data['description'],
                recommendations=recommendations_html,
                check_time=datetime.utcnow().strftime('%d.%m.%Y %H:%M')
            )
            
            flash('✅ Проверка погоды выполнена! Проверьте вашу почту.', 'success')
        else:
            flash(f'Ошибка получения погоды: {weather_data["error"]}', 'error')
            
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(url_for('client_services'))
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
                    'description': 'Мониторинг доступности серверов с отправкой уведомлений о простоях. Возможность ping любых IP-адресов и доменов.',
                    'price': 299.99
                },
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





# Остановка планировщика при выходе
atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)

if __name__ == '__main__':
    create_tables()
    app.run(debug=True)