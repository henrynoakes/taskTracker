const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const {runInNewContext} = require('node:vm');

const template = readFileSync(join(__dirname, '../tasktracker/templates/tasks.html'), 'utf8');
const script = template.match(/<script>([\s\S]*?)<\/script>/)[1];

function setup(count = 1, send = async () => ({ok: true})) {
    const requests = [];
    const timers = new Map();
    const empty = {hidden: true};
    let now = 0;
    let nextTimer = 0;
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
            classList: {
                toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
                remove(name) { classes.delete(name); },
            },
            querySelector() { return status; },
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
        forms, requests, empty,
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
