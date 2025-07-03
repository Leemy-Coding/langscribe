from flask import Flask, render_template, request, session, redirect, url_for, flash, abort
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from functools import wraps
import os, re, uuid

from dotenv import load_dotenv
load_dotenv()

from models import db, User, Meaning, KnownWord, Upload

# --- App setup ---
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# --- Config ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Extensions ---
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Admin decorator ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- User loader ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # Instead of User.query.get

# --- Utility functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'txt'

def tokenize(text):
    return re.findall(r'\b[a-zA-ZþÞðÐæÆǣǢāĀēĒīĪōŌūŪȳȲ]+\b', text.lower())

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

from datetime import datetime

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
    uploads = Upload.query.all()

    ALLOWED_LANGUAGES = [

        # Germanic Languages
        'Dutch', 'English', 'German', 'Icelandic', 'Norwegian', 'Old English', 'Swedish',

        # Romance Languages
        'French', 'Italian', 'Latin', 'Portuguese', 'Romanian', 'Spanish',

        # Celtic Languages
        'Breton', 'Irish', 'Welsh',

        # Slavic Languages
        'Polish', 'Serbian', 'Slovenian',

        # Indo-Aryan Languages
        'Bengali', 'Hindi', 'Urdu',

        # Semitic Languages
        'Modern Standard Arabic',

        # Turkic Languages
        'Turkish',

        # Sino-Tibetan Languages
        'Mandarin',

        # Japonic Languages
        'Japanese',

        # Koreanic Languages
        'Korean',

        # Niger-Congo Languages
        'Hausa', 'Swahili', 'Xhosa',

        # Creoles / Pidgins
        'Naija', 'Nigerian',

        # Austronesian Languages
        'Indonesian',

        # Other / Unclassified
        'Armenian', 'Guarani'
    ]

    return render_template('community.html', uploads=uploads, allowed_languages=ALLOWED_LANGUAGES)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    # Grab form data
    file = request.files.get('file')
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    language = request.form.get('language', '').strip()
    uploader = current_user.username

    # Define allowed languages
    ALLOWED_LANGUAGES = [

        # Germanic Languages
        'Dutch', 'English', 'German', 'Icelandic', 'Norwegian', 'Old English', 'Swedish',

        # Romance Languages
        'French', 'Italian', 'Latin', 'Portuguese', 'Romanian', 'Spanish',

        # Celtic Languages
        'Breton', 'Irish', 'Welsh',

        # Slavic Languages
        'Polish', 'Serbian', 'Slovenian',

        # Indo-Aryan Languages
        'Bengali', 'Hindi', 'Urdu',

        # Semitic Languages
        'Modern Standard Arabic',

        # Turkic Languages
        'Turkish',

        # Sino-Tibetan Languages
        'Mandarin',

        # Japonic Languages
        'Japanese',

        # Koreanic Languages
        'Korean',

        # Niger-Congo Languages
        'Hausa', 'Swahili', 'Xhosa',

        # Creoles / Pidgins
        'Naija', 'Nigerian',

        # Austronesian Languages
        'Indonesian',

        # Other / Unclassified
        'Armenian', 'Guarani'
    ]

    # Validation checks
    if not file or not allowed_file(file.filename):
        flash("Invalid file type. Only .txt allowed.")
        return redirect(url_for('community'))

    if not title:
        flash("Title is required.")
        return redirect(url_for('community'))

    if not author:
        flash("Author field is required.")
        return redirect(url_for('community'))

    if language not in ALLOWED_LANGUAGES:
        flash("Please select a valid language.")
        return redirect(url_for('community'))

    # Secure filename and save
    original_filename = secure_filename(file.filename)
    filename = f"{uuid.uuid4().hex}_{original_filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Create and save upload record
    new_upload = Upload(
        filename=filename,
        title=title,
        author=author,
        uploader=uploader,
        language=language
    )
    db.session.add(new_upload)
    db.session.commit()

    flash(f"'{title}' by {author} ({language}) uploaded by {uploader}!")
    return redirect(url_for('community'))

@app.route('/read/<filename>')
@login_required
def read(filename):
    upload = Upload.query.filter_by(filename=filename).first()
    if not upload:
        return "File not found", 404

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return "File not found", 404

    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    words = tokenize(text)
    word_list = list(dict.fromkeys(words))

    known = {w.word for w in current_user.known_words}
    meanings = {m.word: m.meaning for m in current_user.meanings}

    return render_template('read.html',
        filename=filename,
        text=text,
        words=word_list,
        known_words=known,
        word_meanings=meanings,
        title=upload.title,
        current_language=upload.language
    )

@app.route('/delete_upload/<int:upload_id>', methods=['GET','POST'])
@admin_required
def delete_upload(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], upload.filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    db.session.delete(upload)
    db.session.commit()
    flash(f"'{upload.filename}' has been deleted.")
    return redirect(url_for('community'))

@app.route('/mark_known/<word>')
@login_required
def mark_known(word):
    word = word.lower()
    if not KnownWord.query.filter_by(user_id=current_user.id, word=word).first():
        db.session.add(KnownWord(word=word, user_id=current_user.id))
        db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/update_meaning', methods=['POST'])
@login_required
def update_meaning():
    word = request.form.get('word', '').strip().lower()
    meaning = request.form.get('meaning', '').strip()
    filename = request.form.get('filename')
    source = request.form.get('source')
    language = request.form.get('language', '').strip()

    if not word or not language:
        flash("Both word and language are required to save the meaning.", "danger")
        return redirect(request.referrer or url_for('index'))

    # Check for existing entry for this user, word, and language
    existing = Meaning.query.filter_by(user_id=current_user.id, word=word, language=language).first()

    if meaning:
        if existing:
            existing.meaning = meaning
        else:
            new_meaning = Meaning(
                word=word,
                meaning=meaning,
                language=language,
                user_id=current_user.id
            )
            db.session.add(new_meaning)
    elif existing:
        db.session.delete(existing)

    db.session.commit()

    # Redirect back to where user came from
    if filename:
        return redirect(url_for('read', filename=filename))
    elif source == 'library':
        return redirect(url_for('library'))
    return redirect(url_for('index'))

@app.route('/library')
@login_required
def library():
    from collections import defaultdict

    meanings = Meaning.query.filter_by(user_id=current_user.id).all()

    words_by_language_unsorted = defaultdict(list)
    word_meanings = {}

    for m in meanings:
        lang = m.language or "Unspecified"
        words_by_language_unsorted[lang].append({
            'word': m.word,
            'meaning': m.meaning
        })
        word_meanings[m.word] = m.meaning

    # Sort languages and words within each language
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
    uploads = Upload.query.all()
    return render_template('admin.html', uploads=uploads)

# --- Do NOT use db.create_all() when using Flask-Migrate ---
if __name__ == '__main__':
    app.run(debug=True)