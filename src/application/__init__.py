"""Application orchestration and persistence boundaries."""

__all__ = ["ResearchApplicationService"]


def __getattr__(name):
    """Load the original service class only when explicitly requested."""
    if name == "ResearchApplicationService":
        from src.application.service import ResearchApplicationService

        globals()[name] = ResearchApplicationService
        return ResearchApplicationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
