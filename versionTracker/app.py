from flask import Flask
from flask_marshmallow import Marshmallow
from flask_restful import Api, Resource, reqparse, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from github import Github, GithubException, BadCredentialsException


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
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
    version_title = db.Column(db.String(64), unique=True, nullable=False)
    published_at = db.Column(db.DateTime, unique=True, nullable=False)

    def __repr__(self):
        return '<Repo %r %r %r>' % (self.name, self.version_title, self.published_at)


class RepoSchema(ma.Schema):
    class Meta:
        fields = ("name", "version_title", "published_at")
        model = Repo


repo_schema = RepoSchema()


class RepoResource(Resource):
    def get(self):
        args = name_parser.parse_args()
        repo = Repo.query.filter_by(name=args['name']).first_or_404()
        return repo_schema.dump(repo)

    def post(self):
        args = name_token_parser.parse_args()
        name = args['name']
        github_repo = None

        try:
            github_repo = Github(args['token']).get_user().get_repo(name)
        except BadCredentialsException as b:
            abort(401, description="Invalid token provided. {}".format(b))
        except GithubException as g:
            abort(404, description="Cannot find repo with name '{}' using provided token. {}".format(name, g))

        releases = github_repo.get_releases()

        if releases.totalCount == 0:
            abort(404, description="No releases associated with repo '{}'".format(name))

        latest_release = releases[0]

        new_repo = Repo(
            name=name,
            version_title=latest_release.title,
            published_at=latest_release.published_at
        )
        try:
            db.session.add(new_repo)
        except SQLAlchemyError as s:
            abort(500, description=s)
        db.session.commit()
        return repo_schema.dump(new_repo)


api.add_resource(RepoResource, '/repo')
