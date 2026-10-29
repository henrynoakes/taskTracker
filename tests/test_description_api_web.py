from html.parser import HTMLParser

import pytest

from tasktracker import db_connection
from tasktracker import database as db
from tasktracker import operations as ops

SOURCE = '# Requirements\n\nComplete **exercises 1–5**.\n\n- Review notes\n- [Check answers](https://example.com)\n\n' + 'Additional notes. ' * 100


def create(client, description=SOURCE):
    response = client.post('/tasks', json={
        'name': 'Mathematics', 'priority': 2, 'duration': 3, 'due_date': '2026-11-01',
        'description': description,
    })
    assert response.status_code == 201
    return response.json()


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.links = []
        self.link = None
        self.textarea = None
        self.textarea_text = ''
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == 'a':
            assert self.link is None, 'Interactive links must not be nested'
            self.link = [attrs.get('href'), '']
        if tag in {'button', 'input'}:
            assert self.link is None, 'Controls must not be nested inside links'
        if tag == 'textarea':
            self.textarea = attrs

    def handle_endtag(self, tag):
        if tag == 'a':
            self.links.append(self.link)
            self.link = None
        if tag == 'textarea':
            self.textarea = None

    def handle_data(self, text):
        if self.link is not None:
            self.link[1] += text
        if self.textarea is not None:
            self.textarea_text += text


@pytest.mark.parametrize('description', [None, '', ' \n\t ', SOURCE, 'a' * 20000])
def test_api_create_read_and_list_description(client, description):
    task = create(client, description)
    expected = description if description and description.strip() else None
    assert task['description'] == expected
    assert client.get(f"/tasks/{task['id']}").json() == task
    assert client.get('/tasks').json() == [task]


def test_api_patch_description_preserves_omitted_field_and_can_clear(client):
    task = create(client)
    url = f"/tasks/{task['id']}"
    assert client.patch(url, json={'name': 'Renamed'}).json()['description'] == SOURCE
    for description in ['Replacement *description*', None, SOURCE, '', SOURCE, ' \n ']:
        response = client.patch(url, json={'description': description})
        assert response.status_code == 200
        expected = description if description and description.strip() else None
        assert response.json()['description'] == expected
        assert client.get(url).json()['description'] == expected


@pytest.mark.parametrize('description', [12, True, [], {}])
def test_api_rejects_non_string_description(client, description):
    task = create(client)
    assert client.post('/tasks', json={
        'name': 'Invalid', 'priority': 1, 'duration': 1, 'description': description,
    }).status_code == 422
    assert client.patch(f"/tasks/{task['id']}", json={'description': description}).status_code == 422
    assert client.get('/tasks').json() == [task]


def test_api_description_filter_sort_and_null_handling(client):
    first = create(client, 'Beta')
    missing = create(client, None)
    last = create(client, 'Alpha')
    assert client.get('/tasks', params={'field': 'description', 'value': 'Beta'}).json() == [first]
    assert client.get('/tasks', params={'field': 'description', 'value': 'null'}).json() == [missing]
    # Fetch current objects because creating tasks also recalculates scheduled dates.
    by_id = {task['id']: task for task in client.get('/tasks').json()}
    assert client.get('/tasks?sort_by=description').json() == [by_id[last['id']], by_id[first['id']], by_id[missing['id']]]
    assert client.get('/tasks?sort_by=description&descending=true').json() == [by_id[first['id']], by_id[last['id']], by_id[missing['id']]]


def test_web_create_edit_and_clear_description(client):
    page = client.get('/web/tasks/new')
    assert page.status_code == 200
    assert 'Description (Markdown supported)' in page.text
    assert Page(page.text).textarea_text == '\n'
    response = client.post('/web/tasks/new', data={
        'name': 'Web task', 'priority': 1, 'duration': 2, 'description': SOURCE,
    }, follow_redirects=False)
    assert response.status_code == 303
    task = client.get('/tasks').json()[0]
    assert task['description'] == SOURCE
    url = f"/web/tasks/{task['id']}/edit"
    assert Page(client.get(url).text).textarea_text == '\n' + SOURCE
    for description in ['\n  Exact **Markdown**  \n', '', '  ']:
        response = client.post(url, data={
            'name': 'Web task', 'priority': 1, 'duration': 2, 'description': description,
        }, follow_redirects=False)
        assert response.status_code == 303
        expected = description if description.strip() else None
        assert client.get(f"/tasks/{task['id']}").json()['description'] == expected
        assert Page(client.get(url).text).textarea_text == '\n' + (expected or '')


def test_edit_form_escapes_markdown_source(client):
    source = '</textarea><script>alert(1)</script>\n**Markdown** & <tag>'
    task = create(client, source)
    page = Page(client.get(f"/web/tasks/{task['id']}/edit").text)
    assert page.textarea_text == '\n' + source
    assert all(tag != 'script' for tag, _ in page.elements)


def test_list_preview_formatted_and_task_name_links_to_details(client):
    task = create(client)
    response = client.get('/web/')
    assert response.status_code == 200
    page = Page(response.text)
    assert any(href == f"/web/tasks/{task['id']}" and text.strip() == 'Mathematics' for href, text in page.links)
    assert any(href == 'https://example.com' for href, _ in page.links)
    assert any(attrs.get('class') == 'task-description-preview' for _, attrs in page.elements)
    assert '<strong>exercises 1–5</strong>' in response.text
    assert '<h1>Requirements</h1>' not in response.text
    assert '<ul>' not in response.text
    assert '<pre>' not in response.text


def test_task_details_full_description_and_existing_actions(client):
    task = create(client)
    response = client.get(f"/web/tasks/{task['id']}")
    assert response.status_code == 200
    page = Page(response.text)
    assert '<h1>Requirements</h1>' in response.text
    assert '<strong>exercises 1–5</strong>' in response.text
    assert '<ul>' in response.text
    assert 'Additional notes. ' * 100 in response.text
    assert '90 minutes' in response.text
    assert '1 November 2026' in response.text
    assert 'Incomplete' in response.text
    assert 'datetime="' + task['scheduled_date'] + '"' in response.text
    assert any(href == f"/web/tasks/{task['id']}/edit" and text == 'Edit task' for href, text in page.links)
    assert any(tag == 'form' and attrs.get('action') == f"/web/tasks/{task['id']}/complete" and attrs.get('method') == 'post'
               for tag, attrs in page.elements)
    assert all(tag != 'script' for tag, _ in page.elements)
    for _ in range(2):
        assert client.post(f"/web/tasks/{task['id']}/complete", follow_redirects=False).status_code == 303
    completed = client.get(f"/web/tasks/{task['id']}")
    assert completed.status_code == 200
    completed_page = Page(completed.text)
    assert 'class="task-completed">Completed</span>' in completed.text
    assert not any(tag == 'form' for tag, _ in completed_page.elements)
    assert any(href == f"/web/tasks/{task['id']}/edit" for href, _ in completed_page.links)
    history = client.get('/work-log').json()
    assert len(history) == 1
    assert history[0]['duration'] == 3
    assert history[0]['task_name'] == 'Mathematics'
    assert client.get('/tasks?field=completed&value=false').json() == []


def test_no_description_and_missing_details(client):
    task = create(client, None)
    response = client.get(f"/web/tasks/{task['id']}")
    assert response.status_code == 200
    assert 'description-heading' not in response.text
    assert 'task-description-preview' not in client.get('/web/').text
    response = client.get('/web/tasks/999')
    assert response.status_code == 404
    assert response.json() == {'detail': 'Task 999 not found'}
    assert client.get('/web/tasks/new').status_code == 200


def test_web_markdown_cannot_inject_executable_html(client):
    task = create(client, '<script>alert(1)</script>\n\n<a href="javascript:alert(1)" onclick="alert(2)">Click</a>')
    detail = client.get(f"/web/tasks/{task['id']}")
    assert all(tag != 'script' for tag, _ in Page(detail.text).elements)
    for url in ['/web/', f"/web/tasks/{task['id']}"]:
        for tag, attrs in Page(client.get(url).text).elements:
            assert not any(key.startswith('on') for key in attrs)
            if tag == 'a':
                assert not attrs.get('href', '').startswith('javascript:')


def test_failed_description_update_rolls_back(client):
    task = create(client)
    response = client.patch(f"/tasks/{task['id']}", json={'description': 'Temporary', 'duration': None})
    assert response.status_code == 422
    assert client.get(f"/tasks/{task['id']}").json() == task


def test_startup_migration_commits_description_column(client):
    # Each HTTP request uses a fresh connection, so these checks also verify commit.
    connection = db.connect_database(db_connection.database_path)
    try:
        assert 'description' in {row['name'] for row in connection.execute('PRAGMA table_info(tasks)')}
        assert ops.list_tasks(connection) == []
    finally:
        connection.close()
