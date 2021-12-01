from flask import Flask
from flask_marshmallow import Marshmallow
from flask_restful import Api, Resource, reqparse, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from github import Github, GithubException, BadCredentialsException


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gitVersionTracker.db'
db = SQLAlchemy(app)
ma = Marshmallow(app)
api = Api(app)

name_parser = reqparse.RequestParser()
name_parser.add_argument('name')

name_token_parser = reqparse.RequestParser()
name_token_parser.add_argument('name')
name_token_parser.add_argument('token')


class Repo(db.Model):
    name = db.Column(db.String(128), primary_key=True)
    token = db.Column(db.String(64), nullable=False)
    version_title = db.Column(db.String(64), nullable=False)
    published_at = db.Column(db.DateTime, nullable=False)
    seen = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        return '<Repo %r %r %r>' % (self.name, self.version_title, self.published_at)


class RepoSchema(ma.Schema):
    class Meta:
        # token not included in order to obfuscate sensitive data
        fields = ("name", "version_title", "published_at", "seen")
        model = Repo


repo_schema = RepoSchema()


def _get_remote_repo(name, token):
    try:
        return Github(token).get_user().get_repo(name)
    except BadCredentialsException as b:
        abort(401, description="Invalid token provided. {}".format(b))
    except GithubException as g:
        abort(404, description="Cannot find repo with name '{}' using provided token. {}".format(name, g))


def _get_latest_release(repo):
    releases = repo.get_releases()

    if releases.totalCount == 0:
        abort(404, description="No releases associated with repo '{}'".format(repo.name))

    return releases[0]


def _make_repo(name, token, title, pub_date, seen):
    return Repo(
        name=name,
        token=token,
        version_title=title,
        published_at=pub_date,
        seen=seen
    )


def _add_repo_to_db(new_repo):
    db.session.add(new_repo)
    try:
        db.session.commit()
    except IntegrityError as i:
        abort(500, description=i.args)


class RepoResource(Resource):
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

    def post(self):
        args = name_token_parser.parse_args()
        name = args['name']
        token = args['token']

        latest_release = _get_latest_release(_get_remote_repo(name, token))
        new_repo = _make_repo(name, token, latest_release.title, latest_release.published_at, False)
        _add_repo_to_db(new_repo)

        return repo_schema.dump(new_repo)

    # In a more robust version I would add a way to update tokens and
    # add better error handling for expired tokens during updates.
    def patch(self):
        repos = Repo.query.all()

        for repo in repos:
            latest_release = _get_latest_release(_get_remote_repo(repo.name, repo.token))
            if latest_release.published_at > repo.published_at:
                repo.published_at = latest_release.published_at
                repo.version_title = latest_release.title
                repo.seen = False

        db.session.commit()
        return repo_schema.dump(repos, many=True)

    def delete(self):
        name = name_parser.parse_args()['name']
        repo = Repo.query.filter_by(name=name).first()
        if repo is None:
            abort(404, description="Could not find repo '{}' for deletion.".format(name))
        db.session.delete(repo)
        db.session.commit()
        return '', 204


api.add_resource(RepoResource, '/repo')
