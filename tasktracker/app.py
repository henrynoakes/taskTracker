from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import database as db
from . import db_connection
from .api import router as api_router
from .web import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection = db.connect_database(db_connection.database_path)

    try:
        db.initialize_database(connection)
        connection.commit()
    finally:
        connection.close()

    yield


app = FastAPI(lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)

app.include_router(api_router)
app.include_router(web_router)
