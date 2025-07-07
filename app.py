from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv
from uuid import uuid4
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

ALLOWED_EXTENSIONS = {'txt', 'docx'}

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
@login_required
def community():
    uploads = File.query.order_by(File.language, File.title).all()

    uploads_by_language = {}
    for upload in uploads:
        uploads_by_language.setdefault(upload.language, []).append(upload)

    return render_template(
        'community.html',
        uploads_by_language=uploads_by_language,
        allowed_languages=ALLOWED_LANGUAGES,
        allowed_extension=ALLOWED_EXTENSIONS,
    )

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files.get('file')
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    language = request.form.get('language', '').strip()
    uploader = current_user.username

    if not file or not allowed_file(file.filename):
        flash("Invalid file type. Only .txt, .docx allowed.")
        return redirect(url_for('community'))
    if not title or not author or language not in ALLOWED_LANGUAGES:
        flash("Please fill out all required fields.")
        return redirect(url_for('community'))

    try:
        if file.filename.lower().endswith('.txt'):
            content = file.read().decode('utf-8', errors='replace')
        elif file.filename.lower().endswith('.docx'):
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
    file = File.query.get_or_404(id)
    if not file:
        abort(404)

    meanings = Meaning.query.filter_by(user_id=current_user.id, language=file.language).all()
    word_meanings = {m.word.lower(): m.meaning for m in meanings}

    return render_template(
        'read.html',
        title=file.title,
        text=file.content,
        id=id,
        current_language=file.language,
        word_meanings=word_meanings
    )

@app.route('/delete_upload/<uuid:upload_id>', methods=['GET', 'POST'])
@admin_required
def delete_upload(upload_id):
    file_entry = File.query.get_or_404(upload_id)
    db.session.delete(file_entry)
    db.session.commit()
    flash(f"'{file_entry.title}' has been deleted.")
    return redirect(url_for('community'))

@app.route('/update_meaning', methods=['POST'])
@login_required
def update_meaning():
    word = request.form.get('word', '').strip().lower()
    meaning = request.form.get('meaning', '').strip()
    file_id = request.form.get('id')
    referrer = request.form.get('referrer')
    language = request.form.get('language', '').strip()

    if not word or not language:
        flash("Both word and language are required to save the meaning.", "danger")
        return redirect(request.referrer or url_for('index'))

    # Save or update meaning
    existing_meaning = Meaning.query.filter_by(user_id=current_user.id, word=word, language=language).first()
    if meaning:
        if existing_meaning:
            existing_meaning.meaning = meaning
        else:
            db.session.add(Meaning(word=word, meaning=meaning, language=language, user_id=current_user.id))
    elif existing_meaning:
        db.session.delete(existing_meaning)

    # Also mark word as known
    existing_known = KnownWord.query.filter_by(user_id=current_user.id, word=word, language=language).first()
    if not existing_known:
        db.session.add(KnownWord(word=word, language=language, user_id=current_user.id))

    db.session.commit()

    # Redirect with anchor to the edited word
    if referrer == 'read' and file_id:
        return redirect(url_for('read', id=file_id))
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
        word = m.word.strip().lower()

        words_by_language_unsorted[lang].append({'word': word, 'meaning': m.meaning})

        key = f"{word}:::{lang}"
        word_meanings[key] = m.meaning

    words_by_language = {
        lang: sorted(entries, key=lambda x: x['word'])
        for lang, entries in sorted(words_by_language_unsorted.items())
    }

    return render_template(
        'library.html',
        words_by_language=words_by_language,
        word_meanings=word_meanings
        )

@app.route('/remove_word/<word>', methods=['POST'])
@login_required
def remove_word(word):
    language = request.form.get('language', '').strip()

    if not language:
        flash("Language is required to remove a word.", "danger")
        return redirect(url_for('library'))
    
    word = word.strip().lower()

    meaning = Meaning.query.filter_by(user_id=current_user.id, word=word, language=language).first()
    if meaning:
        db.session.delete(meaning)

    known = KnownWord.query.filter_by(user_id=current_user.id, word=word, language=language).first()
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