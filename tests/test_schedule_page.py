from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tasktracker import db_connection, scheduler
from tasktracker import database as db
from tasktracker import operations as ops
from tasktracker.web_formatting import format_duration, format_schedule_date

TODAY = date(2026, 10, 29)


@pytest.mark.parametrize(
    'offset, expected',
    [
        (0, 'Today'), (1, 'Tomorrow'), (2, 'Saturday'), (3, 'Sunday'),
        (4, 'Monday'), (5, 'Tuesday'), (6, 'Wednesday'),
        (7, 'Thursday, 5 November'), (11, 'Monday, 9 November'),
        (-1, 'Overdue — Wednesday, 28 October'),
        (-8, 'Overdue — Wednesday, 21 October'),
    ],
)
def test_schedule_date_headings(offset, expected):
    assert format_schedule_date(TODAY + timedelta(days=offset), TODAY) == expected


@pytest.mark.parametrize(
    'today, scheduled, expected',
    [
        (date(2026, 12, 25), date(2027, 1, 1), 'Friday, 1 January 2027'),
        (date(2027, 1, 2), date(2026, 12, 31), 'Overdue — Thursday, 31 December 2026'),
        (date(2026, 12, 31), date(2027, 1, 1), 'Tomorrow'),
        (date(2026, 12, 31), date(2027, 1, 2), 'Saturday'),
    ],
)
def test_schedule_headings_across_years(today, scheduled, expected):
    assert format_schedule_date(scheduled, today) == expected


@pytest.mark.parametrize(
    'increments, expected',
    [(0, '0 min'), (1, '30 min'), (2, '1 h'), (3, '1 h 30 min'),
     (5, '2 h 30 min'), (6, '3 h'), (12, '6 h')],
)
def test_workload_duration(increments, expected):
    assert format_duration(increments) == expected


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.links = []
        self.link = None
        self.task_details = []
        self.details = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == 'span' and attrs.get('class') == 'task-details':
            self.details = ''
        if tag == 'a':
            assert self.link is None
            self.link = [attrs.get('href'), '']
        if tag in {'input', 'button'}:
            assert self.link is None

    def handle_endtag(self, tag):
        if tag == 'span' and self.details is not None:
            self.task_details.append(' '.join(self.details.split()))
            self.details = None
        if tag == 'a':
            self.links.append(self.link)
            self.link = None

    def handle_data(self, value):
        if self.details is not None:
            self.details += value
        if self.link is not None:
            self.link[1] += value


@pytest.fixture(autouse=True)
def fixed_today(freeze_time):
    freeze_time(datetime(2026, 10, 29, 12, tzinfo=UTC))


def insert_tasks(rows):
    connection = db.connect_database(db_connection.database_path)
    try:
        with connection:
            ids = []
            for name, scheduled_date, duration in rows:
                ids.append(ops.add_task(
                    connection, name, 2, duration,
                    due_date=TODAY + timedelta(days=20), scheduled_date=scheduled_date,
                ))
        return ids
    finally:
        connection.close()


def test_schedule_empty_and_navigation(client):
    response = client.get('/web/schedule')
    assert response.status_code == 200
    assert '<title>Schedule</title>' in response.text
    assert '<h2>Schedule</h2>' in response.text
    assert 'No incomplete tasks.' in response.text
    assert 'class="schedule-day' not in response.text
    assert response.context['groups'] == []
    for path in ['/web/', '/web/schedule']:
        page = Page(client.get(path).text)
        assert ['/web/', 'Tasks'] in page.links
        assert ['/web/schedule', 'Schedule'] in page.links


def test_schedule_groups_order_actions_and_workloads(client):
    ids = insert_tasks([
        ('Tomorrow task', TODAY + timedelta(days=1), 1),
        ('Oldest overdue', TODAY - timedelta(days=3), 1),
        ('Unscheduled task', None, 6),
        ('Today first', TODAY, 2),
        ('Today second', TODAY, 3),
        ('Far future', TODAY + timedelta(days=7), 4),
        ('Completed task', TODAY, 10),
        ('Recent overdue', TODAY - timedelta(days=1), 2),
    ])
    connection = db.connect_database(db_connection.database_path)
    try:
        with connection:
            ops.edit_task(connection, ids[3], 'priority', 5)
            ops.edit_task(connection, ids[4], 'priority', 1)
            ops.complete_task(connection, ids[6])
        assert ops.get_work_duration(connection, TODAY) == 10
    finally:
        connection.close()
    response = client.get('/web/schedule')
    assert response.status_code == 200
    groups = response.context['groups']
    assert [(group['heading'], [task.name for task in group['tasks']], group['duration']) for group in groups] == [
        ('Overdue — Monday, 26 October', ['Oldest overdue'], '30 min'),
        ('Overdue — Wednesday, 28 October', ['Recent overdue'], '1 h'),
        ('Today', ['Today first', 'Today second'], '2 h 30 min'),
        ('Tomorrow', ['Tomorrow task'], '30 min'),
        ('Thursday, 5 November', ['Far future'], '2 h'),
        ('Unscheduled', ['Unscheduled task'], '3 h'),
    ]
    positions = [response.text.index('>' + group['heading'] + '</h3>') for group in groups]
    assert positions == sorted(positions)
    assert response.text.count('schedule-overdue') == 2
    assert 'Completed task' not in response.text
    assert '<p id="empty-tasks" hidden>' in response.text
    page = Page(response.text)
    assert any(href == f'/web/tasks/{ids[3]}' and text.strip() == 'Today first' for href, text in page.links)
    assert any(tag == 'form' and attrs.get('action') == f'/web/tasks/{ids[3]}/complete'
               and attrs.get('method') == 'post' for tag, attrs in page.elements)
    assert sum(tag == 'script' for tag, _ in page.elements) == 1
    assert not any(key.startswith('on') for _, attrs in page.elements for key in attrs)


def test_only_unscheduled_tasks(client):
    insert_tasks([('Too large', None, 6), ('Waiting', None, 2)])
    response = client.get('/web/schedule')
    assert [(group['heading'], group['duration']) for group in response.context['groups']] == [('Unscheduled', '4 h')]
    assert '<p id="empty-tasks" hidden>' in response.text


def test_only_completed_tasks_show_empty_state(client):
    ids = insert_tasks([('Done', TODAY, 2)])
    connection = db.connect_database(db_connection.database_path)
    try:
        with connection:
            ops.complete_task(connection, ids[0])
    finally:
        connection.close()
    response = client.get('/web/schedule')
    assert response.context['groups'] == []
    assert 'No incomplete tasks.' in response.text
    assert 'Done' not in response.text


@pytest.mark.parametrize(
    'instant, expected',
    [(datetime(2026, 7, 1, 23, 30, tzinfo=UTC), 'Today'),
     (datetime(2026, 1, 1, 23, 30, tzinfo=UTC), 'Tomorrow')],
)
def test_schedule_uses_uk_local_date(client, freeze_time, instant, expected):
    freeze_time(instant)
    scheduled = instant.date() + timedelta(days=1)
    insert_tasks([('Near midnight', scheduled, 1)])
    assert client.get('/web/schedule').context['groups'][0]['heading'] == expected


def test_schedule_previews_reuse_markdown_and_row_styling(client):
    ids = insert_tasks([('With description', TODAY, 2), ('Without description', TODAY, 1)])
    source = '**Bold** and *italic* [notes](https://example.com)\n\n' + 'More notes ' * 100
    source += '\n\n<script>alert(1)</script><a href="javascript:alert(1)" onclick="alert(2)">Bad</a>'
    connection = db.connect_database(db_connection.database_path)
    try:
        with connection:
            ops.edit_task(connection, ids[0], 'description', source)
    finally:
        connection.close()
    for path in ['/web/', '/web/schedule']:
        response = client.get(path)
        page = Page(response.text)
        assert response.text.count('class="task-description-preview"') == 1
        assert '<strong>Bold</strong>' in response.text
        assert '<em>italic</em>' in response.text
        assert ['https://example.com', 'notes'] in page.links
        assert any(href == f'/web/tasks/{ids[0]}' for href, _ in page.links)
        assert sum(tag == 'li' and attrs.get('class') == 'task' for tag, attrs in page.elements) == 2
        assert not any(attrs.get('href', '').startswith('javascript:') for _, attrs in page.elements)
        assert not any('onclick' in attrs for _, attrs in page.elements)
    script = (Path(__file__).resolve().parent.parent / 'tasktracker/templates/_task_completion.html').read_text().strip()
    response = client.get('/web/schedule')
    assert script in response.text
    assert response.text.count('<script>') == 1
    assert client.get(f'/web/tasks/{ids[0]}').status_code == 200


def test_schedule_is_read_only_and_uses_one_task_query(client, monkeypatch):
    insert_tasks([('Overdue', TODAY - timedelta(days=1), 3), ('Unscheduled', None, 6)])
    before_tasks = client.get('/tasks').json()
    before_history = client.get('/work-log').json()
    queries = []
    original_connect = db.connect_database

    def connect(path):
        connection = original_connect(path)
        connection.set_trace_callback(queries.append)
        return connection

    def unexpected_schedule(connection):
        pytest.fail('GET /web/schedule must not regenerate the schedule')

    monkeypatch.setattr(db, 'connect_database', connect)
    monkeypatch.setattr(scheduler, 'schedule_tasks', unexpected_schedule)
    assert client.get('/web/schedule').status_code == 200
    assert len(queries) == 1
    assert queries[0].startswith('SELECT * FROM tasks')
    assert client.get('/tasks').json() == before_tasks
    assert client.get('/work-log').json() == before_history


def test_schedule_shares_checkboxes_actions_and_omits_row_dates(client):
    insert_tasks([('Scheduled task', TODAY, 2), ('Waiting task', None, 3)])
    schedule_response = client.get('/web/schedule')
    tasks_response = client.get('/web/')
    schedule_page = Page(schedule_response.text)
    tasks_page = Page(tasks_response.text)
    assert schedule_page.task_details == ['P2 · 60 min', 'P2 · 90 min']
    assert tasks_page.task_details == ['P2 · 60 min · 2026-10-29', 'P2 · 90 min · Unscheduled']
    template_dir = Path(__file__).resolve().parent.parent / 'tasktracker/templates'
    script = (template_dir / '_task_completion.html').read_text().strip()
    actions = (template_dir / '_task_list_actions.html').read_text().strip()
    for response, page in [(schedule_response, schedule_page), (tasks_response, tasks_page)]:
        assert '<div class="page-heading">' in response.text
        assert script in response.text
        assert actions in response.text
        assert sum(tag == 'input' and attrs.get('type') == 'checkbox' for tag, attrs in page.elements) == 2
        assert '}, 2500)' in response.text
        assert ['/web/tasks/new', '+ Add task'] in page.links
        assert any(tag == 'form' and attrs.get('action') == '/web/schedule' and attrs.get('method') == 'post'
                   for tag, attrs in page.elements)
