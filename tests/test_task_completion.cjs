const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const {runInNewContext} = require('node:vm');

const template = readFileSync(join(__dirname, '../tasktracker/templates/_task_completion.html'), 'utf8');
const script = template.match(/<script>([\s\S]*?)<\/script>/)[1];

function setup(count = 1, send = async () => ({ok: true}), durations = null) {
    const requests = [];
    const timers = new Map();
    const empty = {hidden: true};
    let now = 0;
    let nextTimer = 0;
    let group = null;
    const forms = Array.from({length: count}, (_, i) => {
        const classes = new Set();
        const checkbox = {
            checked: false,
            disabled: false,
            addEventListener(event, callback) { this[event] = callback; },
        };
        const status = {textContent: ''};
        const button = {hidden: false};
        const label = {hidden: true};
        const task = {
            removed: false,
            dataset: {duration: durations ? durations[i] : 1},
            classList: {
                toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
                remove(name) { classes.delete(name); },
            },
            querySelector() { return status; },
            closest() { return group; },
            remove() { this.removed = true; },
        };
        return {
            checkbox, status, button, label, task, classes,
            dataset: {completeUrl: `/tasks/${i + 1}/complete`},
            closest() { return task; },
            querySelector(selector) { return {input: checkbox, button, label}[selector]; },
            addEventListener(event, callback) { this[event] = callback; },
            toggle(checked) { checkbox.checked = checked; checkbox.change(); },
        };
    });
    if (durations) {
        group = {
            removed: false,
            total: {textContent: 'Original total'},
            querySelectorAll() { return forms.filter(form => !form.task.removed).map(form => form.task); },
            querySelector() { return this.total; },
            remove() { this.removed = true; },
        };
    }
    runInNewContext(script, {
        document: {
            querySelectorAll() { return forms; },
            querySelector() { return forms.find(form => !form.task.removed)?.task ?? null; },
            getElementById() { return empty; },
        },
        setTimeout(callback, delay) {
            const id = ++nextTimer;
            timers.set(id, {callback, due: now + delay});
            return id;
        },
        clearTimeout(id) { timers.delete(id); },
        fetch(url, options) { requests.push({url, method: options.method}); return send(); },
    });
    return {
        forms, requests, empty, group,
        async advance(ms) {
            now += ms;
            const ready = [...timers].filter(([, timer]) => timer.due <= now);
            for (const [id, timer] of ready) {
                timers.delete(id);
                await timer.callback();
            }
        },
    };
}

test('checking waits 2.5 seconds before sending completion and removing the row', async () => {
    const ui = setup();
    const form = ui.forms[0];
    assert.equal(form.button.hidden, true);
    assert.equal(form.label.hidden, false);
    form.toggle(true);
    assert.equal(form.checkbox.checked, true);
    assert.equal(form.classes.has('task-pending'), true);
    await ui.advance(2499);
    assert.equal(ui.requests.length, 0);
    assert.equal(form.task.removed, false);
    await ui.advance(1);
    assert.deepEqual(ui.requests, [{url: '/tasks/1/complete', method: 'POST'}]);
    assert.equal(form.task.removed, true);
    assert.equal(ui.empty.hidden, false);
});

test('unchecking cancels completion; checking again starts a fresh delay', async () => {
    const ui = setup();
    const form = ui.forms[0];
    form.toggle(true);
    await ui.advance(2000);
    form.toggle(false);
    await ui.advance(1000);
    assert.equal(ui.requests.length, 0);
    assert.equal(form.task.removed, false);
    assert.equal(form.classes.has('task-pending'), false);
    assert.equal(form.status.textContent, '');
    form.toggle(true);
    await ui.advance(2499);
    assert.equal(ui.requests.length, 0);
    await ui.advance(1);
    assert.equal(ui.requests.length, 1);
});

test('task timers are independent', async () => {
    const ui = setup(2);
    ui.forms[0].toggle(true);
    ui.forms[1].toggle(true);
    ui.forms[0].toggle(false);
    await ui.advance(2500);
    assert.deepEqual(ui.requests, [{url: '/tasks/2/complete', method: 'POST'}]);
    assert.equal(ui.forms[0].task.removed, false);
    assert.equal(ui.forms[1].task.removed, true);
    assert.equal(ui.empty.hidden, true);
});

for (const [failure, send] of [
    ['HTTP error', async () => ({ok: false})],
    ['network error', async () => { throw new Error('Offline'); }],
]) {
    test(`${failure} restores the checkbox and keeps the task visible`, async () => {
        const ui = setup(1, send);
        const form = ui.forms[0];
        form.toggle(true);
        await ui.advance(2500);
        assert.equal(form.task.removed, false);
        assert.equal(form.checkbox.checked, false);
        assert.equal(form.checkbox.disabled, false);
        assert.equal(form.classes.has('task-pending'), false);
        assert.match(form.status.textContent, /try again/);
    });
}


test('schedule completion updates the workload and removes an empty date group', async () => {
    const ui = setup(3, undefined, [1, 2, 3]);
    ui.forms[0].toggle(true);
    await ui.advance(2500);
    assert.equal(ui.group.total.textContent, '2 h 30 min');
    assert.equal(ui.group.removed, false);
    ui.forms[1].toggle(true);
    await ui.advance(2500);
    assert.equal(ui.group.total.textContent, '1 h 30 min');
    ui.forms[2].toggle(true);
    await ui.advance(2500);
    assert.equal(ui.group.removed, true);
    assert.equal(ui.empty.hidden, false);
});

for (const [duration, expected] of [[1, '30 min'], [2, '1 h']]) {
    test(`schedule totals format a remaining duration of ${duration} increments`, async () => {
        const ui = setup(2, undefined, [1, duration]);
        ui.forms[0].toggle(true);
        await ui.advance(2500);
        assert.equal(ui.group.total.textContent, expected);
    });
}

test('cancelled or failed schedule completion leaves the group and total intact', async () => {
    const ui = setup(1, async () => ({ok: false}), [3]);
    ui.forms[0].toggle(true);
    ui.forms[0].toggle(false);
    await ui.advance(2500);
    assert.equal(ui.requests.length, 0);
    ui.forms[0].toggle(true);
    await ui.advance(2500);
    assert.equal(ui.group.removed, false);
    assert.equal(ui.group.total.textContent, 'Original total');
    assert.equal(ui.forms[0].task.removed, false);
});
