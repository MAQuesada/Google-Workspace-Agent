from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from api.depends import check_access
from agents.orchestrator.core import get_agent
from utils.config import get_config, Config
from utils.logger import get_logger

logger = get_logger("api.core")
load_dotenv()


def factory_app() -> FastAPI:
    from api.chat_router import router as chat_router
    from api.user_router import router as user_router

    # if the agent can't be built, it will raise an exception
    get_agent()
    app = FastAPI(
        title="Google Workspace Agent - API",
        description=(
            "This API provides endpoints to interact with the Google Workspace Agent."
        ),
        version="1.0.0",
    )

    @app.get("/health_check/", dependencies=[Depends(check_access)])
    async def health_check(
        config: Config = Depends(get_config),
    ):
        logger.info(
            "Health check passed!",
            extra={"status": 200, "LOG_LEVEL": config.LOG_LEVEL},
        )
        return {"message": "System running!"}

    app.include_router(
        chat_router,
        dependencies=[Depends(check_access)],
    )
    app.include_router(
        user_router,
        dependencies=[Depends(check_access)],
    )
    return app
