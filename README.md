# Task tracker and scheduler

## How to handle scheduling
There should be an adapted priority, while from 1 - 5 is the default, a task close to it's deadline should increase it (even more if it's overdue) (maybe with some kind of inversely proportional function that increases exponentially as the time delta decreases including into negatives), along with a task which has existed for a long time.


```
python -m venv .venv
```

```
source .venv/bin/activate.fish
```

```
pip install "fastapi[standard]"
```
The standard installation includes Uvicorn, the ASGI server that will run your application.
```
pip install pytest httpx
```
