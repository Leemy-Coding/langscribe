# manage.py
from flask.cli import FlaskGroup
from app import app
from models import db
from flask_migrate import Migrate

migrate = Migrate(app, db)
cli = FlaskGroup(app)

if __name__ == "__main__":
    cli()