from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv
from docx import Document

import os, re
from datetime import datetime
from collections import defaultdict

load_dotenv()

from models import db, User, Meaning, KnownWord, File

# --- App Setup ---
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI') or os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Extensions ---
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Constants ---
ALLOWED_LANGUAGES = [
    'Dutch', 'English', 'German', 'Icelandic', 'Norwegian', 'Old English', 'Swedish',
    'French', 'Italian', 'Latin', 'Portuguese', 'Romanian', 'Spanish',
    'Breton', 'Irish', 'Welsh',
    'Polish', 'Serbian', 'Slovenian',
    'Bengali', 'Hindi', 'Urdu',
    'Modern Standard Arabic',
    'Turkish',
    'Mandarin',
    'Japanese',
    'Korean',
    'Hausa', 'Swahili', 'Xhosa',
    'Naija', 'Nigerian',
    'Indonesian',
    'Armenian', 'Guarani'
]

ALLOWED_REFERRERS = {'library', 'read'}

# --- Admin Decorator ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- User Loader ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Utility Functions ---
ALLOWED_EXTENSIONS = {'txt', 'docx'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def tokenize(text):
    return re.findall(r'\b[a-zA-ZþÞðÐæÆǣǢāĀēĒīĪōŌūŪȳȲ]+\b', text.lower())

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.context_processor
def inject_now():
    return {'current_year': datetime.now().year}

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash("Username already taken")
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash("Email already registered")
            return redirect(url_for('register'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/community')
def community():
    uploads = File.query.all()
    return render_template('community.html', uploads=uploads, allowed_languages=ALLOWED_LANGUAGES)

from uuid import uuid4

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files.get('file')
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    language = request.form.get('language', '').strip()
    uploader = current_user.username
    allowed_extensions = ",".join(f".{ext}" for ext in ALLOWED_EXTENSIONS)

    if not file or not allowed_file(file.filename):
        flash("Invalid file type. Only .txt allowed.")
        return redirect(url_for('community'))
    if not title or not author or language not in ALLOWED_LANGUAGES:
        flash("Please fil out all required fields.")
        return redirect(url_for('community'))

    try:
        if file.filename.lower().endswith('.txt'):
            content = file.read().decode('utf-8', errors='replace')
        elif file.filename.lower().endswith('docx'):
            doc = Document(file)
            content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        else:
            flash("Unsupported file format.")
            return redirect(url_for('community'))
    except Exception as e:
        flash("There was a probem reading the file.")
        return redirect(url_for('community'))

    new_file = File(
        id=uuid4(),
        title=title,
        author=author,
        uploader=uploader,
        language=language,
        content=content,
        user_id=current_user.id
    )
    db.session.add(new_file)
    db.session.commit()

    flash(f"'{title}' by {author} in ({language}) uploaded by {uploader}!")
    return redirect(url_for('community'))

@app.route('/read/file/<uuid:id>')
@login_required
def read(id):
    file_entry = File.query.get_or_404(id)

    text = file_entry.content
    words = tokenize(text)
    word_list = list(dict.fromkeys(words))

    known_words = {w.word for w in current_user.known_words}
    word_meanings = {m.word: m.meaning for m in current_user.meanings}

    return render_template(
        'read.html',
        id=id,
        text=text,
        words=word_list,
        known_words=known_words,
        word_meanings=word_meanings,
        title=file_entry.title,
        current_language=file_entry.language
    )

@app.route('/delete_upload/<uuid:upload_id>', methods=['GET', 'POST'])
@admin_required
def delete_upload(upload_id):
    file_entry = File.query.get_or_404(upload_id)
    db.session.delete(file_entry)
    db.session.commit()
    flash(f"'{file_entry.title}' has been deleted.")
    return redirect(url_for('community'))

@app.route('/mark_known/<word>')
@login_required
def mark_known(word):
    word = word.lower()
    referrer = request.args.get('referrer')
    if not KnownWord.query.filter_by(user_id=current_user.id, word=word).first():
        db.session.add(KnownWord(word=word, user_id=current_user.id))
        db.session.commit()

    if referrer in ALLOWED_REFERRERS:
        return redirect(url_for(referrer))
    return redirect(url_for('index'))

@app.route('/update_meaning', methods=['POST'])
@login_required
def update_meaning():
    word = request.form.get('word', '').strip().lower()
    meaning = request.form.get('meaning', '').strip()
    id = request.form.get('id')
    referrer = request.form.get('referrer')
    language = request.form.get('language', '').strip()

    if not word or not language:
        flash("Both word and language are required to save the meaning.", "danger")
        return redirect(request.referrer or url_for('index'))

    existing = Meaning.query.filter_by(user_id=current_user.id, word=word, language=language).first()

    if meaning:
        if existing:
            existing.meaning = meaning
        else:
            db.session.add(Meaning(word=word, meaning=meaning, language=language, user_id=current_user.id))
    elif existing:
        db.session.delete(existing)

    db.session.commit()

    if referrer == 'read' and id:
        return redirect(url_for('read', id=id))
    elif referrer == 'library':
        return redirect(url_for('library'))

    return redirect(url_for('index'))

@app.route('/library')
@login_required
def library():
    meanings = Meaning.query.filter_by(user_id=current_user.id).all()
    words_by_language_unsorted = defaultdict(list)
    word_meanings = {}

    for m in meanings:
        lang = m.language or "Unspecified"
        words_by_language_unsorted[lang].append({'word': m.word, 'meaning': m.meaning})
        word_meanings[m.word] = m.meaning

    words_by_language = {
        lang: sorted(entries, key=lambda x: x['word'])
        for lang, entries in sorted(words_by_language_unsorted.items())
    }

    return render_template('library.html',
                           words_by_language=words_by_language,
                           word_meanings=word_meanings)

@app.route('/remove_word/<word>', methods=['POST'])
@login_required
def remove_word(word):
    meaning = Meaning.query.filter_by(user_id=current_user.id, word=word).first()
    if meaning:
        db.session.delete(meaning)
    known = KnownWord.query.filter_by(user_id=current_user.id, word=word).first()
    if known:
        db.session.delete(known)
    db.session.commit()
    return redirect(url_for('library'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html',
                           known_words_count=len(current_user.known_words),
                           meanings_count=len(current_user.meanings))

@app.route('/admin')
@admin_required
def admin_panel():
    uploads = File.query.all()
    return render_template('admin.html', uploads=uploads)

if __name__ == '__main__':
    app.run(debug=True)