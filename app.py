import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime

# Инициализация приложения
app = Flask(__name__)
app.secret_key = 'your-secret-key-123'  # Измените на свой секретный ключ
Bootstrap(app)

# Конфигурация
UPLOAD_FOLDER = 'static/img/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Создаем папки, если их нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT,
        about TEXT,
        avatar TEXT DEFAULT 'default_avatar.png',
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (sender_id) REFERENCES users (id),
        FOREIGN KEY (receiver_id) REFERENCES users (id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS friends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        friend_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (friend_id) REFERENCES users (id),
        UNIQUE(user_id, friend_id)
    )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Маршруты
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    return render_template('index.html', user=user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        first_name = request.form.get('first_name', '')
        last_name = request.form.get('last_name', '')
        
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO users (username, password, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (username, password, first_name, last_name))
            conn.commit()
            flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Это имя пользователя уже занято', 'danger')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/profile/<username>')
def profile(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    if not user:
        conn.close()
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('index'))
    
    # Проверка дружбы
    friendship_status = None
    if user['id'] != session['user_id']:
        friendship = conn.execute('''
            SELECT * FROM friends 
            WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)
        ''', (session['user_id'], user['id'], user['id'], session['user_id'])).fetchone()
        
        if friendship:
            friendship_status = friendship['status']
    
    # Количество друзей
    friends_count = conn.execute('''
        SELECT COUNT(*) FROM friends 
        WHERE (user_id = ? OR friend_id = ?) AND status = 'accepted'
    ''', (user['id'], user['id'])).fetchone()[0]
    
    conn.close()
    
    return render_template('profile.html', 
                         user=user,
                         is_own_profile=(user['id'] == session['user_id']),
                         friendship_status=friendship_status,
                         friends_count=friends_count)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if request.method == 'POST':
        first_name = request.form.get('first_name', '')
        last_name = request.form.get('last_name', '')
        about = request.form.get('about', '')
        
        # Обработка аватара
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{session['user_id']}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                # Удаляем старый аватар, если он не дефолтный
                if user['avatar'] != 'default_avatar.png':
                    old_avatar = os.path.join(app.config['UPLOAD_FOLDER'], user['avatar'])
                    if os.path.exists(old_avatar):
                        os.remove(old_avatar)
                
                conn.execute('UPDATE users SET avatar = ? WHERE id = ?', 
                           (filename, session['user_id']))
        
        conn.execute('''
            UPDATE users 
            SET first_name = ?, last_name = ?, about = ?
            WHERE id = ?
        ''', (first_name, last_name, about, session['user_id']))
        
        conn.commit()
        conn.close()
        return redirect(url_for('profile', username=session['username']))
    
    conn.close()
    return render_template('edit_profile.html', user=user)

@app.route('/add_friend/<int:friend_id>', methods=['POST'])
def add_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Проверяем, не отправили ли уже запрос
    existing = conn.execute('''
        SELECT * FROM friends 
        WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)
    ''', (session['user_id'], friend_id, friend_id, session['user_id'])).fetchone()
    
    if existing:
        flash('Запрос на дружбу уже существует', 'info')
    else:
        conn.execute('''
            INSERT INTO friends (user_id, friend_id, status)
            VALUES (?, ?, ?)
        ''', (session['user_id'], friend_id, 'pending'))
        conn.commit()
        flash('Запрос на дружбу отправлен', 'success')
    
    conn.close()
    return redirect(url_for('profile', username=request.form['username']))

@app.route('/accept_friend/<int:friend_id>', methods=['POST'])
def accept_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('''
        UPDATE friends SET status = 'accepted'
        WHERE user_id = ? AND friend_id = ? AND status = 'pending'
    ''', (friend_id, session['user_id']))
    conn.commit()
    conn.close()
    
    flash('Вы приняли запрос на дружбу', 'success')
    return redirect(url_for('profile', username=request.form['username']))

@app.route('/remove_friend/<int:friend_id>', methods=['POST'])
def remove_friend(friend_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('''
        DELETE FROM friends
        WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)
    ''', (session['user_id'], friend_id, friend_id, session['user_id']))
    conn.commit()
    conn.close()
    
    flash('Пользователь удалён из друзей', 'info')
    return redirect(url_for('profile', username=request.form['username']))

@app.route('/messages')
def messages():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    dialogues = conn.execute('''
        SELECT u.id, u.username, u.avatar, MAX(m.sent_at) as last_time
        FROM users u
        JOIN messages m ON (m.sender_id = u.id OR m.receiver_id = u.id)
        WHERE (m.sender_id = ? OR m.receiver_id = ?) AND u.id != ?
        GROUP BY u.id
        ORDER BY last_time DESC
    ''', (session['user_id'], session['user_id'], session['user_id'])).fetchall()
    conn.close()
    
    return render_template('messages.html', dialogues=dialogues)

@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
def conversation(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Получаем информацию о собеседнике
    interlocutor = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if not interlocutor:
        conn.close()
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('messages'))
    
    # Отправка сообщения
    if request.method == 'POST':
        content = request.form['content']
        if content.strip():
            conn.execute('''
                INSERT INTO messages (sender_id, receiver_id, content)
                VALUES (?, ?, ?)
            ''', (session['user_id'], user_id, content))
            conn.commit()
    
    # Получаем переписку
    messages = conn.execute('''
        SELECT m.*, u.username as sender_username, u.avatar as sender_avatar
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
        ORDER BY sent_at
    ''', (session['user_id'], user_id, user_id, session['user_id'])).fetchall()
    
    # Помечаем сообщения как прочитанные
    conn.execute('''
        UPDATE messages SET is_read = TRUE
        WHERE receiver_id = ? AND sender_id = ? AND is_read = FALSE
    ''', (session['user_id'], user_id))
    conn.commit()
    
    conn.close()
    return render_template('conversation.html', 
                         interlocutor=interlocutor, 
                         messages=messages)

@app.route('/users')
def users_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    
    conn = get_db_connection()
    if search_query:
        users = conn.execute('''
            SELECT * FROM users 
            WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
            AND id != ?
            ORDER BY username
        ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', session['user_id'])).fetchall()
    else:
        users = conn.execute('''
            SELECT * FROM users WHERE id != ? ORDER BY username
        ''', (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template('users.html', users=users, search_query=search_query)

@app.route('/friends')
def friends_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Друзья
    friends = conn.execute('''
        SELECT u.id, u.username, u.avatar, u.first_name, u.last_name
        FROM friends f
        JOIN users u ON (u.id = CASE 
            WHEN f.user_id = ? THEN f.friend_id 
            ELSE f.user_id 
        END)
        WHERE (f.user_id = ? OR f.friend_id = ?) AND f.status = 'accepted' AND u.id != ?
        ORDER BY u.username
    ''', (session['user_id'], session['user_id'], session['user_id'], session['user_id'])).fetchall()
    
    # Входящие запросы
    pending_requests = conn.execute('''
        SELECT u.id, u.username, u.avatar, u.first_name, u.last_name
        FROM friends f
        JOIN users u ON f.user_id = u.id
        WHERE f.friend_id = ? AND f.status = 'pending'
        ORDER BY f.created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('friends.html',
                         friends=friends,
                         pending_requests=pending_requests,
                         friends_count=len(friends),
                         pending_requests_count=len(pending_requests))

if __name__ == '__main__':
    app.run(debug=True)