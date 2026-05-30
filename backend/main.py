from fastapi import FastAPI
from fastapi_pagination import add_pagination

from media.routers import media_asset_router

app = FastAPI()

app.include_router(media_asset_router)

add_pagination(app)


@app.get("/")
async def get():
    return "Hello from videoaudionstreaming!"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
