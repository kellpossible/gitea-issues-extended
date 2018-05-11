from flask import Flask, request
from flask import render_template
from flask import url_for, redirect
from flask_restful import Resource, Api, reqparse, abort
import flask.ext.login as flask_login
from urllib.request import urlopen
from urllib.error import HTTPError
import json
import hashlib
import re
import datetime
import dateutil.parser
import os.path
import sys
import webcolors

app = Flask(__name__)
app.secret_key = ""
api = Api(app)

login_manager = flask_login.LoginManager()
login_manager.init_app(app)

USERS = {"": {'pw': ""}}

ACCESS_TOKEN = ""
SERVER_ADDRESS = ""
SERVER_PORT = ""
REPO_USER = ""
REPO_NAME = ""


def hash_md5_int(string):
    m = hashlib.md5()
    m.update(string.encode("utf-8"))
    digest = m.hexdigest()
    return int(digest, 16)


def get_or_none(dic, key):
    if key in dic:
        return dic[key]
    else:
        return None


def date_to_integer(dt_time):
    return 10000 * dt_time.year + 1000 * dt_time.month + dt_time.day


def assign_handle_none(json_structure, field_name, item):
    if item is not None:
        json_structure[field_name] = item.item_id
    else:
        json_structure[field_name] = None


def json_to_html(json_structure):
    return json.dumps(json_structure, indent=4, sort_keys=True).replace(
        "\n", "<br>\n").replace(
        " ", "&nbsp;")


def parse_gogs_datetime(string):
    # todo: timezone info
    if string is None:
        return None

    date_re = re.compile("(\d+)[-](\d+)[-](\d+)[T](\d+)[:](\d+)[:](\d+)[-].*")
    result = date_re.match(string)
    year = int(result.group(1))
    month = int(result.group(2))
    day = int(result.group(3))
    hour = int(result.group(4))
    minute = int(result.group(5))
    second = int(result.group(6))

    return datetime.datetime(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second)


def parse_gantt_datetime(string):
    # todo: timezone info
    if string is None:
        return None

    date_re = re.compile("(\d+)[-](\d+)[-](\d+)[ ](\d+)[:](\d+)[:](\d+)")
    result = date_re.match(string)
    year = int(result.group(1))
    month = int(result.group(2))
    day = int(result.group(3))
    hour = int(result.group(4))
    minute = int(result.group(5))
    second = int(result.group(6))

    return datetime.datetime(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second)


def parse_iso_datetime(string):
    if string is None:
        return None

    return datetime.datetime.strptime(string, "%Y-%m-%dT%H:%M:%S")


class LoginUser(flask_login.UserMixin):
    pass


@login_manager.user_loader
def user_loader(email):
    if email not in USERS:
        return

    user = LoginUser()
    user.id = email
    return user


@login_manager.request_loader
def request_loader(request):
    email = request.form.get('email')
    if email not in USERS:
        return

    user = LoginUser()
    user.id = email

    # DO NOT ever store passwords in plaintext and always compare password
    # hashes using constant-time comparison!

    user.is_authenticated = request.form['pw'] == USERS[email]['pw']

    return user


@login_manager.unauthorized_handler
def unauthorized_handler():
    return redirect(url_for('login'))


class DatabaseItem:

    def __init__(self, db):
        self.db = db
        self.item_id = None

    def add_to_db(self):
        pass

    def get_from_db(self):
        pass


class User(DatabaseItem):

    def __init__(self, db):
        super().__init__(db)
        self.email = ""
        self.avatar_url = ""
        self.full_name = ""
        self.username = ""

    def get_from_db(self):
        return get_or_none(self.db.users, self.item_id)

    def add_to_db(self):
        if self.get_from_db() is None:
            self.db.users[self.item_id] = self

    def get_avatar_url(self):
        if "https" not in self.avatar_url:
            return "http://{0}:{1}{2}".format(
                SERVER_ADDRESS,
                SERVER_PORT,
                self.avatar_url)

        return self.avatar_url

    def get_url(self):
        return "http://{0}:{1}/{2}".format(
            SERVER_ADDRESS,
            SERVER_PORT,
            self.username
            )

    def load_from_db_json(self, json_structure):
        self.item_id = json_structure["id"]
        self.avatar_url = json_structure["avatar_url"]
        self.full_name = json_structure["full_name"]
        self.username = json_structure["username"]
        self.email = json_structure["email"]

    def load_from_api_json(self, json_structure):
        self.email = json_structure["email"]
        self.avatar_url = json_structure["avatar_url"]
        self.full_name = json_structure["full_name"]
        self.item_id = int(json_structure["id"])
        self.username = json_structure["username"]
        self.add_to_db()

        return self.get_from_db()

    def to_json(self):
        json_structure = {
            "id": int(self.item_id),
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "avatar_url": self.avatar_url
        }

        return json_structure


class Label(DatabaseItem):
    issues_ids = {
      "Admin Task": 1,
      "Documentation": 2,
      "Research": 3,
      "URGENT": 4,
      "Design": 5,
      "Programming": 10,
      "Sprint/Review": 11,
      "Sprint/Backlog": 12,
      "Sprint/Done": 13,
      "Sprint/Doing": 14,
      "Optimization": 15,
      "Bug": 16}

    def __init__(self, db):
        super().__init__(db)
        self.color = ""
        self.name = ""

    def get_from_db(self):
        return get_or_none(self.db.labels, self.item_id)

    def add_to_db(self):
        if self.get_from_db() is None:
            self.db.labels[self.item_id] = self

    def get_url(self):
        return "http://{0}:{1}/{2}/{3}/issues?labels={4}".format(
            SERVER_ADDRESS,
            SERVER_PORT,
            REPO_USER,
            REPO_NAME,
            self.item_id
            )


    def load_from_db_json(self, json_structure):
        self.item_id = json_structure["id"]
        self.color = json_structure["color"]
        self.name = json_structure["name"]

    def load_from_api_json(self, json_structure):
        self.color = json_structure["color"]
        self.name = json_structure["name"]
        #print(json_structure)
        #self.item_id = hash_md5_int(self.name)
        self.item_id = self.issues_ids[self.name]
        self.add_to_db()

        return self.get_from_db()

    def get_title_color(self):
        rgb = webcolors.hex_to_rgb(self.color)
        value = (float(rgb[0])/255.0 +
                 float(rgb[0])/255.0 +
                 float(rgb[0])/255.0)/3.0
        if value > 0.5:
            return "black"
        else:
            return "white"

    def to_json(self):
        json_structure = {
            "id": int(self.item_id),
            "name": self.name,
            "color": self.color
        }

        return json_structure


class Milestone(DatabaseItem):

    def __init__(self, db):
        super().__init__(db)
        self.closed_at = None
        self.closed_issues = 0
        self.description = ""
        self.open_issues = 0
        self.state = "open"
        self.title = ""
        self.due_on = None

    def get_from_db(self):
        return get_or_none(self.db.milestones, self.item_id)

    def add_to_db(self):
        if self.get_from_db() is None:
            self.db.milestones[self.item_id] = self

    def load_from_db_json(self, json_structure):
        self.item_id = json_structure["id"]
        self.title = json_structure["title"]
        self.closed_at = parse_iso_datetime(
            json_structure["closed_at"])
        self.due_on = parse_iso_datetime(
            json_structure["due_on"])
        self.state = json_structure["state"]
        self.open_issues = json_structure["open_issues"]
        self.closed_issues = json_structure["closed_issues"]

    def load_from_api_json(self, json_structure):

        if json_structure["closed_at"] is not None:
            self.closed_at = parse_gogs_datetime(json_structure["closed_at"])

        self.due_on = parse_gogs_datetime(json_structure["due_on"])
        self.closed_issues = json_structure["closed_issues"]
        self.open_issues = json_structure["open_issues"]
        self.description = json_structure["description"]
        self.item_id = json_structure["id"]
        self.state = json_structure["state"]
        self.title = json_structure["title"]
        self.add_to_db()

        return self.get_from_db()

    def to_json(self):
        json_structure = {
            "id": self.item_id,
            "state": self.state,
            "title": self.title,
            "description": self.description,
            "open_issues": self.open_issues,
            "closed_issues": self.closed_issues,
            "due_on": self.due_on.isoformat()
        }

        if self.closed_at is not None:
            json_structure["closed_at"] = self.closed_at.isoformat()
        else:
            json_structure["closed_at"] = None

        return json_structure


class Issue(DatabaseItem):

    def __init__(self, db):
        super().__init__(db)
        self.assignee = None
        self.body = ""
        self.comments = None
        self.labels = []
        self.user = None
        self.number = None
        self.state = "open"
        self.milestone = None
        self.title = ""
        self.pull_request = None
        self.updated_at = None
        self.created_at = None
        self.user = None

        # gantt-chart
        self.task_duration = 1
        self.task_parent = None
        self.task_start_date = None
        self.task_end_date = None
        self.task_progress = 0.0

    def get_from_db(self):
        return get_or_none(self.db.issues, self.item_id)

    def add_to_db(self):
        if self.get_from_db() is None:
            self.db.issues[self.item_id] = self

    def get_server_url(self):
        return "http://{0}:{1}/{2}/{3}/issues/{4}".format(
            SERVER_ADDRESS,
            SERVER_PORT,
            REPO_USER,
            REPO_NAME,
            self.number)

    def load_from_db_json(self, json_structure):
        self.item_id = int(json_structure["id"])
        self.title = json_structure["title"]
        self.state = json_structure["state"]
        self.description = get_or_none(json_structure, "description")
        self.number = json_structure["number"]

        self.task_start_date = parse_iso_datetime(
            json_structure["task_start_date"])

        self.task_end_date = parse_iso_datetime(
            json_structure["task_end_date"])

        self.created_at = parse_iso_datetime(
            json_structure["created_at"])

        self.updated_at = parse_iso_datetime(
            json_structure["updated_at"])

        self.comments = json_structure["comments"]
        self.body = json_structure["body"]

        self.task_parent = json_structure["task_parent"]
        self.task_duration = json_structure["task_duration"]
        self.task_progress = json_structure["task_progress"]

        if json_structure["milestone"] is not None:
            self.milestone = self.db.get_milestone(json_structure["milestone"])

        if json_structure["user"] is not None:
            self.user = self.db.get_user(json_structure["user"])

        if json_structure["assignee"] is not None:
            self.assignee = self.db.get_user(json_structure["assignee"])

        if json_structure["labels"] is not None:
            self.labels = []
            for label_id in json_structure["labels"]:
                self.labels.append(self.db.get_label(label_id))

    def load_from_api_json(self, json_structure):
        self.item_id = int(json_structure["id"])
        self.title = json_structure["title"]
        self.state = get_or_none(json_structure, "state")
        self.description = get_or_none(json_structure, "description")
        self.number = json_structure["number"]

        self.updated_at = parse_gogs_datetime(json_structure["updated_at"])
        self.created_at = parse_gogs_datetime(json_structure["created_at"])

        if json_structure["assignee"] is not None:
            assignee_user = User(self.db)
            assignee_user.load_from_api_json(json_structure["assignee"])
            self.assignee = assignee_user.get_from_db()

        if json_structure["user"] is not None:
            user = User(self.db)
            self.user = user.load_from_api_json(json_structure["user"])

        if json_structure["labels"] is not None:
            for label_structure in json_structure["labels"]:
                label = Label(self.db)
                self.labels.append(label.load_from_api_json(label_structure))

        if json_structure["milestone"] is not None:
            milestone = Milestone(self.db)
            milestone.load_from_api_json(json_structure["milestone"])
            self.milestone = milestone.get_from_db()

        self.add_to_db()

        return self.get_from_db()

    def to_json(self):
        json_structure = {
            "id": self.item_id,
            "number": self.number,
            "state": self.state,
            "title": self.title,
            "body": self.body,
            "labels": [],
            "comments": self.comments,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "task_duration": self.task_duration,
            "task_parent": self.task_parent,
            "task_progress": self.task_progress

        }

        assign_handle_none(json_structure, "user", self.user)
        assign_handle_none(json_structure, "assignee", self.assignee)
        assign_handle_none(json_structure, "milestone", self.milestone)

        if self.task_end_date is not None:
            json_structure["task_end_date"] = self.task_end_date.isoformat()
        else:
            json_structure["task_end_date"] = None

        if self.task_start_date is not None:
            json_structure[
                "task_start_date"] = self.task_start_date.isoformat()
        else:
            json_structure["task_start_date"] = None

        for label in self.labels:
            json_structure["labels"].append(label.item_id)

        return json_structure


class IssuesDatabase:

    def __init__(self, api, local_db_path):
        self.local_db_path = local_db_path  # a json database file
        self.api = api
        self.milestones = {}
        self.issues = {}
        self.users = {}
        self.labels = {}

    def get_user(self, user_id):
        return self.users[user_id]

    def get_milestone(self, milestone_id):
        return self.milestones[milestone_id]

    def get_label(self, label_id):
        return self.labels[label_id]

    def get_issue(self, issue_id):
        return self.issues[issue_id]

    def pull_from_api(self):
        self.milestones = {}
        self.issues = {}
        self.users = {}
        self.labels = {}

        json_structure = []
        page_i = 1
        while(page_i < 1000):
            print("getting page: " + str(page_i))
            try:
                new_structure = self.api.access(
                    "/repos/FYRP/Aircraft_Direction_Predition_FYRP/issues/{0}"
                    .format(page_i), [])
            except HTTPError:
                break

            json_structure.append(new_structure)

            page_i += 1

        # print(json.dumps(json_structure))
        for issue_structure in json_structure:
            i = Issue(self)
            i.load_from_api_json(issue_structure)

        self.pull_issue_tasks_from_local_db()
        self.push_to_local_db()

    def get_milestone_date_bounds(self, milestone_id):
        start_date = None
        end_date = None
        start_date_int = sys.maxsize
        end_date_int = 0
        for issue in self.issues.values():
            if issue.milestone is not None:
                if issue.milestone.item_id == milestone_id:

                    if date_to_integer(issue.task_start_date) < start_date_int:
                        start_date = issue.task_start_date
                        start_date_int = date_to_integer(issue.task_start_date)

                    if date_to_integer(issue.task_end_date) > end_date_int:
                        end_date = issue.task_end_date
                        end_date_int = date_to_integer(issue.task_end_date)

        bounds = [start_date, end_date]
        return bounds

    def get_milestone_progress(self, milestone_id):
        n_issues = 0.0
        progress_total = 0.0

        for issue in self.issues.values():
            if issue.milestone is not None:
                if issue.milestone.item_id == milestone_id:
                    n_issues += 1.0
                    progress_total += issue.task_progress

        if n_issues == 0.0:
            return 0.0

        return progress_total / n_issues

    def get_project_date_bounds(self):
        start_date = None
        end_date = None
        start_date_int = sys.maxsize
        end_date_int = 0
        for issue in self.issues.values():
            if issue.task_start_date is not None:
                if date_to_integer(issue.task_start_date) < start_date_int:
                    start_date = issue.task_start_date
                    start_date_int = date_to_integer(issue.task_start_date)

            if issue.task_end_date is not None:
                if date_to_integer(issue.task_end_date) > end_date_int:
                    end_date = issue.task_end_date
                    end_date_int = date_to_integer(issue.task_end_date)

        bounds = [start_date, end_date]
        return bounds

    def get_highest_issue_id(self):
        highest_id = 0
        for issue in self.issues.values():
            if issue.item_id > highest_id:
                highest_id = issue.item_id

        return highest_id

    def pull_issue_tasks_from_local_db(self):
        if not os.path.isfile(self.local_db_path):
            json_structure = {
                "issues": [],
                "users": [],
                "labels": [],
                "milestones": []}
            json_string = json.dumps(json_structure, indent=4)
            db_file = open(self.local_db_path, 'w')
            db_file.write(json_string)
            db_file.close()

        db_file = open(self.local_db_path, 'r')
        json_structure = json.loads(db_file.read())
        db_file.close()

        json_issues = json_structure["issues"]
        for issue in self.issues.values():
            issue_not_in_local_db = True
            for json_issue in json_issues:
                if int(issue.item_id) == int(json_issue["id"]):
                    issue_not_in_local_db = False

                    issue.task_duration = int(json_issue["task_duration"])
                    issue.task_parent = json_issue["task_parent"]
                    issue.task_end_date = parse_iso_datetime(
                        json_issue["task_end_date"])
                    issue.task_progress = float(json_issue["task_progress"])
                    issue.task_start_date = parse_iso_datetime(
                        json_issue["task_start_date"])

            if issue_not_in_local_db:
                # set up default task values for the issue
                if issue.milestone is not None:
                    if issue.milestone.due_on is not None and \
                            issue.created_at is not None:
                        issue.task_duration = max(
                            1,
                            int((issue.milestone.due_on -
                                 issue.created_at).days)
                            )

                issue.task_parent = "0"

                if issue.created_at is not None:
                    issue.task_start_date = issue.created_at

                if issue.milestone is not None:
                    if issue.milestone.due_on is not None:
                        issue.task_end_date = issue.milestone.due_on

                # if the issue is closed
                if issue.state != "open":
                    issue.task_progress = 1.0

    def pull_from_local_db(self):
        self.milestones = {}
        self.issues = {}
        self.users = {}
        self.labels = {}

        db_file = open(self.local_db_path, 'r')
        json_structure = json.loads(db_file.read())
        db_file.close()

        for user_json in json_structure["users"]:
            user = User(self)
            user.load_from_db_json(user_json)
            self.users[user.item_id] = user

        for label_json in json_structure["labels"]:
            label = Label(self)
            label.load_from_db_json(label_json)
            self.labels[label.item_id] = label

        for milestone_json in json_structure["milestones"]:
            milestone = Milestone(self)
            milestone.load_from_db_json(milestone_json)
            self.milestones[milestone.item_id] = milestone

        for issue_json in json_structure["issues"]:
            issue = Issue(self)
            issue.load_from_db_json(issue_json)
            self.issues[issue.item_id] = issue

    def push_to_local_db(self):
        json_structure = {}
        json_structure["issues"] = []
        json_structure["users"] = []
        json_structure["labels"] = []
        json_structure["milestones"] = []

        for issue in self.issues.values():
            json_structure["issues"].append(issue.to_json())

        for user in self.users.values():
            json_structure["users"].append(user.to_json())

        for label in self.labels.values():
            json_structure["labels"].append(label.to_json())

        for milestone in self.milestones.values():
            json_structure["milestones"].append(milestone.to_json())

        json_string = json.dumps(json_structure, indent=4)
        db_file = open(self.local_db_path, 'w')
        db_file.write(json_string)
        db_file.close()

    def get_gantt_json(self):
        date_format = "{0}-{1:02d}-{2:02d} 00:00:00"
        json_structure = {}
        data = []
        milestones_map = {}

        # milestones
        for milestone in self.milestones.values():
            adjusted_id = DB.get_highest_issue_id() + milestone.item_id
            milestones_map[milestone.item_id] = adjusted_id
            bounds = DB.get_milestone_date_bounds(milestone.item_id)
            if bounds[0] is None or bounds[1] is None:
                bounds = DB.get_project_date_bounds()

            task_structure = {
                "id": adjusted_id,
                "text": milestone.title,
                "progress": DB.get_milestone_progress(milestone.item_id),
                "parent": 0,
                "is_milestone": 1
            }

            if bounds[0] is not None and bounds[1] is not None:
                duration = max(1, int((bounds[1] - bounds[0]).days))
                d = bounds[0]
                date_string = date_format.format(
                    d.year,
                    d.month,
                    d.day
                )
                task_structure["start_date"] = date_string
                task_structure["duration"] = duration
            else:
                task_structure["start_date"] = date_format.format(0, 0, 0)
                task_structure["duration"] = 0

            if milestone.state == "open":
                task_structure["open"] = 1
            else:
                task_structure["open"] = 0

            data.append(task_structure)

        # issues
        for issue in self.issues.values():
            d = issue.task_start_date
            date_string = date_format.format(
                d.year,
                d.month,
                d.day
            )
            task_structure = {
                "id": issue.item_id,
                "start_date": date_string,
                "duration": issue.task_duration,
                "text": "#{0} {1}".format(issue.number, issue.title),
                "progress": issue.task_progress,
                "is_milestone": 0,
                "parent": 0
            }

            if issue.state == "open":
                task_structure["open"] = 1
            else:
                task_structure["open"] = 0

            if issue.assignee is not None:
                # username = issue.assignee.full_name
                # if username == "":
                # 	username = issue.assignee.username
                username = issue.assignee.username
                task_structure["users"] = [username]
            else:
                task_structure["users"] = None

            if issue.milestone is not None:
                task_structure["parent"] = milestones_map[
                    issue.milestone.item_id]

            data.append(task_structure)

        json_structure["data"] = data

        json_structure["collections"] = {
            "links": []
        }

        return json_structure


class GogsApi:

    def __init__(self, address, port, token):
        self.address = address
        self.port = port
        self.token = token

    def access(self, path, args=[]):
        uri = "http://{0}:{1}/api/v1{2}?token={3}".format(
            self.address,
            self.port,
            path,
            self.token
        )

        for e in args:
            uri += "&" + e

        # print(uri)

        return json.loads(urlopen(uri).read().decode())


def get_DB():
    API = GogsApi(SERVER_ADDRESS, SERVER_PORT, ACCESS_TOKEN)
    DB = IssuesDatabase(API, "issues_database.json")
    return DB


class GanttData(Resource):

    def get(self):
        """ Push REST json data for tasks to javascript in browser """
        DB = get_DB()
        DB.pull_from_api()
        json_structure = DB.get_gantt_json()
        return json_structure


class GanttLinks(Resource):

    def post(self):
        return


class GanttTask(Resource):

    def put(self, task_id):
        """Accept REST json for a GanttTask from javascript in browser"""
        DB = get_DB()
        DB.pull_from_api()
        for issue in DB.issues.values():
            if issue.item_id == task_id:
                issue.task_duration = int(request.form["duration"])
                issue.task_parent = request.form["parent"]
                issue.task_end_date = parse_gantt_datetime(
                    request.form["end_date"])
                issue.task_progress = float(request.form["progress"])
                issue.task_start_date = parse_gantt_datetime(
                    request.form["start_date"])

                DB.push_to_local_db()


api.add_resource(GanttData, '/gantt-chart-REST')
api.add_resource(GanttLinks, '/gantt-chart-REST/link')
api.add_resource(GanttTask, '/gantt-chart-REST/task/<int:task_id>')


"""
Ideas:
Use NVD3 http://nvd3.org/index.html and d3.js for creating charts
"""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/gantt-chart/")
@flask_login.login_required
def gantt_chart():
    return render_template("gantt-chart.html")


@app.route("/kanban-board/")
# @flask_login.login_required
def kanban_board():
    """
    A kanban board for organising scrum-like developement.
    Assign issues labels to put them in the board's columns.

    Following Labels/Columns are relavent:
     - Sprint/Backlog
     - Sprint/Doing
     - Sprint/Review
     - Sprint/Done
    """
    DB = get_DB()
    DB.pull_from_api()
    # DB.pull_from_local_db()

    backlog_label = None
    doing_label = None
    review_label = None
    done_label = None

    backlog_issues = []
    doing_issues = []
    review_issues = []
    done_issues = []

    for label in DB.labels.values():
        if label.name == "Sprint/Backlog":
            backlog_label = label
        if label.name == "Sprint/Doing":
            doing_label = label
        if label.name == "Sprint/Review":
            review_label = label
        if label.name == "Sprint/Done":
            done_label = label

    sprint_labels = [
        backlog_label,
        doing_label,
        review_label,
        done_label
        ]

    for issue in DB.issues.values():
        if issue.labels is not None:
            for issue_label in issue.labels:
                if issue_label == backlog_label:
                    backlog_issues.append(issue)
                if issue_label == doing_label:
                    doing_issues.append(issue)
                if issue_label == review_label:
                    review_issues.append(issue)
                if issue_label == done_label:
                    done_issues.append(issue)

    columns = []
    backlog_column = {
        "issues": backlog_issues,
        "title": "Backlog",
        "color": "#fef2c0"
        }
    columns.append(backlog_column)

    doing_column = {
        "issues": doing_issues,
        "title": "Doing",
        "color": "#fad8c7"
        }
    columns.append(doing_column)

    review_column = {
        "issues": review_issues,
        "title": "Review",
        "color": "#d4c5f9"
        }
    columns.append(review_column)

    done_column = {
        "issues": done_issues,
        "title": "Done",
        "color": "#bfe5bf"
        }
    columns.append(done_column)

    return render_template(
        "kanban-board.html",
        columns=columns,
        sprint_labels=sprint_labels)


def download_issues_json():
    """Export the issues for this repo to json \
    format and make available for download"""
    pass


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return '''
<form action='login' method='POST'>
<input type='text' name='email' id='email' placeholder='email'></input>
<input type='password' name='pw' id='pw' placeholder='password'></input>
<input type='submit' name='submit'></input>
</form>
'''

    email = request.form['email']
    if request.form['pw'] == USERS[email]['pw']:
        user = LoginUser()
        user.id = email
        flask_login.login_user(user)
        return redirect(url_for('gantt_chart'))

    return 'Bad login'


@app.route('/logout')
def logout():
    flask_login.logout_user()
    return 'Logged out'


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, threaded=True)
