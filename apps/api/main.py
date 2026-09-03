from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="Verifiable Financial Agent System",
        version="0.1.0",
        description="Phase 1 evidence-gated financial research API",
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

