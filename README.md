# gitVersionTracker

gitVersionTracker is a simple application to keep track of git repository versions


## Installation

Once you have cloned the repo, cd into the root directory and create a python virtual environment.
```bash
python3 -m venv venv
```
Activate the environment
```bash
source venv/bin/activate
```
Make sure your pip installation is up to date
```bash
pip install --upgrade pip
```
Install the requirements
```bash
pip install -r requirements.txt
```
Create the database
```bash
python createDB.py
```
Start the application server
```bash
python main.py
```


## Usage

You will need to have a [git personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token) with permissions to public repositories for any repository you are trying to track with this tool.

Add a repo to the system.
```bash
curl http://localhost:5000/repo \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"name":"<REPOSITORY NAME>", "token":"<GITHUB ACCESS TOKEN>"}'
```

Get a repository from the system.
```bash
curl http://localhost:5000/repo \
    -X GET \
    -H "Content-Type: application/json" \
    -d '{"name":"<REPOSITORY NAME>"}'
```

Refresh latest version for all repositories in the system
```bash
curl http://localhost:5000/repo \
    -X PATCH \
    -H "Content-Type: application/json"
```

Delete a repository from the system
```bash
curl http://localhost:5000/repo \
    -X DELETE \
    -H "Content-Type: application/json" \
    -d '{"name":"<REPOSITORY NAME>"}'
```

## License
[MIT](https://choosealicense.com/licenses/mit/)
