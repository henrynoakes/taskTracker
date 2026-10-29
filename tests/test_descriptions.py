from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from tasktracker import database as db
from tasktracker import operations as ops
from tasktracker.models import Task
from tasktracker.schemas import TaskCreate, TaskResponse, TaskUpdate
from tasktracker.validation import validate_description

SOURCE = '  # Notes\n\n- **First** item\n- Second item  \n\n```python\nprint("done")\n```\n'


@pytest.mark.parametrize('description', [None, '', ' \t\r\n', SOURCE, 'x' * 20000])
def test_description_round_trip_and_normalization(connection, description):
    expected = description if description and description.strip() else None
    with connection:
        task_id = ops.add_task(connection, 'Task', 2, 3, description=description)
    task = ops.get_task(connection, task_id)
    assert task.description == expected
    assert connection.execute('SELECT description FROM tasks WHERE id = ?', (task_id,)).fetchone()[0] == expected
    assert db.task_to_params(task)['description'] == expected
    assert TaskResponse.model_validate(task).description == expected
    assert TaskResponse.model_validate(task).model_dump(mode='json')['created_at'] == task.created_at.isoformat()
    with connection:
        assert db.update_task(connection, replace(task, description='Replacement **text**'))
    assert ops.get_task(connection, task_id).description == 'Replacement **text**'
    for value in [SOURCE, '', None, ' \n ']:
        with connection:
            assert ops.edit_task(connection, task_id, 'description', value)
        assert ops.get_task(connection, task_id).description == (value if value and value.strip() else None)
    with connection:
        db.update_task(connection, replace(task, description='  '))
    assert ops.get_task(connection, task_id).description is None


@pytest.mark.parametrize('description', [42, False, [], {}])
def test_invalid_description_is_rejected_before_writing(connection, description):
    with pytest.raises(TypeError, match='Description must be a string or None'), connection:
        ops.add_task(connection, 'Invalid', 1, 1, description=description)
    with connection:
        task_id = ops.add_task(connection, 'Existing', 1, 1, description=SOURCE)
    before = ops.get_task(connection, task_id)
    with pytest.raises(TypeError), connection:
        ops.edit_task(connection, task_id, 'description', description)
    assert ops.list_tasks(connection) == [before]


def test_description_validation_and_patch_field_presence():
    for value in [None, '', SOURCE]:
        assert validate_description(value) is None
    assert Task(1, 'Task', 1, 1, datetime.now(UTC)).description is None
    assert TaskCreate(name='Task', priority=1, duration=1, description='  ').description is None
    assert TaskUpdate().model_dump(exclude_unset=True) == {}
    assert TaskUpdate(description=None).model_dump(exclude_unset=True) == {'description': None}
    assert TaskUpdate(description='').model_dump(exclude_unset=True) == {'description': None}
    assert TaskUpdate(description=SOURCE).description == SOURCE


def test_new_database_has_nullable_description(connection):
    columns = {row['name']: row for row in connection.execute('PRAGMA table_info(tasks)')}
    assert columns['description']['type'] == 'TEXT'
    assert columns['description']['notnull'] == 0


def test_migrate_existing_database_preserves_tasks_work_log_and_ids(tmp_path):
    path = tmp_path / 'legacy.db'
    connection = db.connect_database(path)
    try:
        with connection:
            connection.executescript('''
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, priority INTEGER NOT NULL,
                    duration INTEGER NOT NULL, due_date TEXT, created_at TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0, scheduled_date TEXT
                );
                CREATE TABLE work_log (
                    id INTEGER PRIMARY KEY, task_id INTEGER, task_name TEXT NOT NULL,
                    work_date TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    duration INTEGER NOT NULL CHECK (duration > 0),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );
                INSERT INTO tasks VALUES
                    (12, 'Completed', 1, 3, '2026-11-01', '2026-10-28T12:00:00+00:00', 1, '2026-10-28'),
                    (25, 'Pending', 2, 4, NULL, '2026-10-28T13:00:00+00:00', 0, '2026-10-29');
                INSERT INTO work_log VALUES
                    (7, 12, 'Historical name', '2026-10-28', '2026-10-28T12:00:00+00:00', 3);
            ''')
        before = [tuple(row) for row in connection.execute('SELECT * FROM tasks ORDER BY id')]
        history = ops.list_work_log(connection)
        with connection:
            db.initialize_database(connection)
            db.initialize_database(connection)
        after = connection.execute('SELECT * FROM tasks ORDER BY id').fetchall()
        assert [tuple(row)[:-1] for row in after] == before
        assert all(row['description'] is None for row in after)
        assert ops.list_work_log(connection) == history
        with connection:
            new_id = ops.add_task(connection, 'New', 1, 1, description=SOURCE)
        assert new_id > 25
    finally:
        connection.close()
    connection = db.connect_database(path)
    try:
        assert ops.get_task(connection, new_id).description == SOURCE
        assert ops.list_work_log(connection) == history
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        connection.close()


def test_description_filtering_and_sorting(connection):
    with connection:
        ids = [ops.add_task(connection, name, 1, 1, description=description)
               for name, description in [('B', 'Beta'), ('Empty', None), ('A', 'Alpha')]]
    assert [task.id for task in ops.list_tasks(connection, 'description', 'Beta')] == [ids[0]]
    assert [task.id for task in ops.list_tasks(connection, 'description', None)] == [ids[1]]
    assert [task.id for task in ops.list_tasks(connection, sort_by='description')] == [ids[2], ids[0], ids[1]]
    assert [task.id for task in ops.list_tasks(connection, sort_by='description', descending=True)] == [ids[0], ids[2], ids[1]]


def test_description_does_not_change_schedule_or_logged_work(connection, freeze_time):
    freeze_time(datetime(2026, 10, 29, 12, tzinfo=UTC))
    from tasktracker import scheduler

    with connection:
        task_id = ops.add_task(connection, 'Original', 1, 3)
        scheduler.schedule_tasks(connection)
    before = ops.get_task(connection, task_id)
    importance = scheduler.calculate_importance(before, date(2026, 10, 29))
    with connection:
        ops.edit_task(connection, task_id, 'description', SOURCE)
        scheduler.schedule_tasks(connection)
    after = ops.get_task(connection, task_id)
    assert after == replace(before, description=SOURCE)
    assert scheduler.calculate_importance(after, date(2026, 10, 29)) == importance
    with connection:
        ops.complete_task(connection, task_id)
        ops.complete_task(connection, task_id)
    history = ops.list_work_log(connection)
    assert len(history) == 1
    assert (history[0].task_name, history[0].duration) == ('Original', 3)
