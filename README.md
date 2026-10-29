# Task tracker and scheduler

## Current scheduler implementation

Currently the scheduler is very naive, I call it priority-ordered first-fit bin packing. It follows this sequence:

1. Gather all uncompleted tasks
2. Calculate for each task an importance, which is a function of days to deadline (or from), priority, age, and duration. Each duration block adds 0.05 importance points, giving longer tasks a slight preference.
3. Order tasks in order of decreasing importance.
4. Attempt to fit the first task into the first day, if it doesn't fit move onto the next until you reach a task that fits.
5. When a task is added to the day remove it from the list.
6. Start again at the top of the list (with any scheduled tasks removed), try and find a task that fits into the remainder of the duration of the day.
7. If a task was added repeat step (6) again. If no task was added (in other words no task was found that fits into the remainder of the first day) move onto the next day and repeat step (4) continuous.

## Improvements

Eventually I should change to a cost-minimisation algorithm. Where each task placement has a cost, then the algorithm tries to find a combination of legal task placements which gets the total sum of cost to be as low as possible.
This would give us much more control on what the final schedule should look like. For example we could add a cost to there being too many tasks on one day. Calculating cost is quite easy, the problem is trying to find the combination of placements with the lowest cost. We could do a brute force search of every possible combination, but this might be quite costly. It could be improved by removing illegal placements. If we were to do a search like this we should probably do it over a series of days such that one of the combinations could be one task on each day.

## How to handle scheduling

There should be an adapted priority, while from 1 - 5 is the default, a task close to it's deadline should increase it (even more if it's overdue) (maybe with some kind of inversely proportional function that increases exponentially as the time delta decreases including into negatives), along with a task which has existed for a long time.

```
python -m venv .venv
```

```
source .venv/bin/activate.fish
```

```
pip install -r requirements.txt
```

This installs the application and Python test dependencies. FastAPI's standard
extras include Uvicorn, the ASGI server that will run your application.
Task descriptions use Python-Markdown for server-side rendering and Bleach for
HTML sanitisation. Markdown source is stored in SQLite; rendered HTML is never
stored. Blank descriptions are treated as absent. New databases include a nullable
description column. Databases created before descriptions were added must be
recreated or updated manually; startup does not add this column to existing tables.

Run the application with:

```bash
uvicorn tasktracker.app:app --reload
```

## Fonts

The web UI serves **JetBrains Mono Nerd Font** from `tasktracker/static/fonts/`.
The stylesheet declares regular, bold, italic and bold italic WOFF2 files. Each is
approximately 1 MB; browsers download only the styles used on the page. Installed
copies are preferred, and `font-display: swap` lets system-font text appear while
downloads finish. No external font service is contacted.

Browsers can cache these files between visits. The static-file server provides
ETag and Last-Modified headers and supports `304 Not Modified` responses when a
cached file is unchanged. A cleared or disabled cache can require downloading
the fonts again.

Optionally install JetBrains Mono Nerd Font on your browsing device from the
[official Nerd Fonts releases](https://github.com/ryanoasis/nerd-fonts/releases/latest)
to avoid downloading matching font files from the website.
