from bcrypt import checkpw, gensalt, hashpw
from flask import Flask, jsonify, g
from flask_httpauth import HTTPBasicAuth
from flask_marshmallow import Marshmallow
from flask_restful import Api, Resource, reqparse, abort
from flask_sqlalchemy import SQLAlchemy
from github import Github, GithubException, BadCredentialsException
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gitVersionTracker.db'
db = SQLAlchemy(app)
ma = Marshmallow(app)
api = Api(app)
# in a real application I would authenticate over HTTPS
auth = HTTPBasicAuth()

name_parser = reqparse.RequestParser()
name_parser.add_argument('name')

token_parser = reqparse.RequestParser()
token_parser.add_argument('token')

name_token_parser = reqparse.RequestParser()
name_token_parser.add_argument('name')
name_token_parser.add_argument('token')

user_password_parser = reqparse.RequestParser()
user_password_parser.add_argument('user')
user_password_parser.add_argument('password')

password_update_parser = reqparse.RequestParser()
password_update_parser.add_argument('user')
password_update_parser.add_argument('old_pw')
password_update_parser.add_argument('new_pw')

user_parser = reqparse.RequestParser()
user_parser.add_argument('user')


class Repo(db.Model):
    name = db.Column(db.String(128), primary_key=True)
    token_hash = db.Column(db.String(64), nullable=False)
    version_title = db.Column(db.String(64), nullable=False)
    published_at = db.Column(db.DateTime, nullable=False)
    seen = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        return '<Repo %r %r %r %r>' % (self.name, self.version_title, self.published_at, self.seen)


class RepoSchema(ma.Schema):
    class Meta:
        # token hash purposely not included
        fields = ("name", "version_title", "published_at", "seen")
        model = Repo


repo_schema = RepoSchema()


def _get_remote_repo(name, token):
    try:
        return Github(token).get_user().get_repo(name)
    except BadCredentialsException as b:
        abort(401, description="Invalid token provided. {}".format(b))
    except GithubException as e:
        abort(404, description="Cannot find repo with name '{}' using provided token. {}".format(name, e))


def _get_latest_release(repo):
    releases = repo.get_releases()

    if releases.totalCount == 0:
        abort(404, description="No releases associated with repo '{}'".format(repo.name))

    return releases[0]


def _make_repo(name, token_hash, title, pub_date, seen):
    return Repo(
        name=name,
        token_hash=token_hash,
        version_title=title,
        published_at=pub_date,
        seen=seen
    )


class RepoResource(Resource):
    @auth.login_required
    def get(self):
        name = name_parser.parse_args()['name']
        repo = Repo.query.filter_by(name=name).first()

        if repo is None:
            abort(404, description="Could not find repo '{}'. Make sure to POST before you try to GET.".format(name))

        # Seen is false for the first call to GET and true afterwards until the next update.
        dump = repo_schema.dump(repo)
        repo.seen = True
        db.session.commit()
        return dump

    @auth.login_required
    def post(self):
        args = name_token_parser.parse_args()
        name = args['name']
        token = args['token']

        latest_release = _get_latest_release(_get_remote_repo(name, token))
        token_hash = hashpw(token.encode('utf-8'), gensalt())
        new_repo = _make_repo(name, token_hash, latest_release.title, latest_release.published_at, False)

        db.session.add(new_repo)
        try:
            db.session.commit()
        except IntegrityError as i:
            abort(500, description=i.args)

        return repo_schema.dump(new_repo)

    # In a more robust version I would add a way to update tokens and
    # add better error handling for expired tokens during updates.
    @auth.login_required
    def patch(self):
        token = token_parser.parse_args()['token']
        repos = Repo.query.all()
        updated_repos = []
        for repo in repos:
            if not checkpw(token.encode('utf-8'), repo.token_hash):
                continue

            latest_release = _get_latest_release(_get_remote_repo(repo.name, token))
            if latest_release.published_at > repo.published_at:
                repo.published_at = latest_release.published_at
                repo.version_title = latest_release.title
                repo.seen = False
                updated_repos.append(repo)

        db.session.commit()
        return repo_schema.dump(updated_repos, many=True)

    @auth.login_required
    def delete(self):
        name = name_parser.parse_args()['name']
        repo = Repo.query.filter_by(name=name).first()

        if repo is None:
            abort(404, description="Could not find repo '{}' for deletion.".format(name))

        db.session.delete(repo)
        db.session.commit()
        return '', 204


api.add_resource(RepoResource, '/repo')


@auth.verify_password
def verify_password(username, password):
    user = User.query.filter_by(username=username).first()
    if not user or not checkpw(password.encode(), user.password_hash):
        return False
    g.user = user
    return True


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return '<User %r %r %r>' % (self.id, self.username, self.password_hash)


class UserSchema(ma.Schema):
    class Meta:
        # password hash purposely not included
        fields = ("id", "username")
        model = User


user_schema = UserSchema()


class UserResource(Resource):
    # no login required to allow creation of initial user
    def post(self):
        args = user_password_parser.parse_args()
        user = args['user']
        password = args['password']

        if user is None or password is None:
            abort(400, description="must supply username and password")
        if User.query.filter_by(username=user).first() is not None:
            abort(400, descriptoin="Username already exists")

        hashed_pw = hashpw(password.encode('utf-8'), gensalt())
        user = User(username=user, password_hash=hashed_pw)
        db.session.add(user)
        db.session.commit()
        return jsonify(201, {'username': user.username}, {'id': user.id})

    @auth.login_required
    def get(self):
        user = user_parser.parse_args()['user']
        existing_user = User.query.filter_by(username=user).first()
        if existing_user is None:
            abort(404, description="Could not find user '{}'. Make sure to POST before you try to GET.".format(user))
        return user_schema.dump(existing_user)

    @auth.login_required
    def patch(self):
        args = password_update_parser.parse_args()
        user = args['user']
        old_pw = args['old_pw']
        new_pw = args['new_pw']

        existing_user = User.query.filter_by(username=user).first()

        if existing_user is None:
            abort(404, description="Could not find user '{}'. Make sure to POST before you try to PATCH.".format(user))
        if not checkpw(old_pw.encode(), existing_user.password_hash):
            abort(401, description="Invalid old password given")

        existing_user.password_hash = hashpw(new_pw.encode('utf-8'), gensalt())
        db.session.commit()
        return user_schema.dump(existing_user)

    @auth.login_required
    def delete(self):
        args = user_password_parser.parse_args()
        user = args['user']
        password = args['password']

        user_to_delete = User.query.filter_by(username=user).first()

        if user_to_delete is None:
            abort(404, description="Could not find user '{}' to delete.".format(user))
        if not checkpw(password.encode(), user_to_delete.password_hash):
            abort(401, description="Invalid password given")

        db.session.delete(user_to_delete)
        db.session.commit()
        return '', 204


api.add_resource(UserResource, '/user')
