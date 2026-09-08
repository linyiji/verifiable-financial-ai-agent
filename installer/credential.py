import asyncio
from pathlib import Path

from installer.errors import InstallError
from src.evaluator.bundle import secure_prompt
from src.evaluator.contracts import EvaluationAuthorizationError
from src.evaluator.launcher import prepare_session


def discover(locations, explicit=None, ask=input):
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file() and path.suffix == ".vfaeval":
            return path
        raise InstallError("NO_EVALUATOR_CREDENTIAL")
    candidates = sorted(
        {
            p
            for directory in locations
            for p in Path(directory).glob("*.vfaeval")
            if p.is_file() and not p.is_symlink()
        }
    )
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        for number, path in enumerate(candidates, 1):
            print(f"{number}. {path.name}")
        try:
            choice = int(ask("Choose credential number: "))
            if not 1 <= choice <= len(candidates):
                raise ValueError()
            return candidates[choice - 1]
        except (ValueError, EOFError):
            raise InstallError("NO_EVALUATOR_CREDENTIAL") from None
    try:
        value = ask(
            "No evaluator credential found. Put it in Downloads and press Enter, "
            "or enter its path: "
        )
    except EOFError:
        raise InstallError("NO_EVALUATOR_CREDENTIAL") from None
    if value:
        return discover(locations, value, ask)
    candidates = [
        p
        for d in locations
        for p in Path(d).glob("*.vfaeval")
        if p.is_file() and not p.is_symlink()
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise InstallError("NO_EVALUATOR_CREDENTIAL")


def unlock(path, prompt=secure_prompt):
    try:
        password = prompt("Evaluation passphrase: ")
        session = asyncio.run(prepare_session(path, password))
        del password
        metadata = session.metadata
        if metadata["llm_remaining"] <= 0 or metadata["data_remaining"] <= 0:
            raise InstallError("QUOTA_EXHAUSTED")
        return session
    except EvaluationAuthorizationError as exc:
        code = {
            "EVALUATION_CREDENTIAL_INVALID": "INVALID_EVALUATOR_CREDENTIAL",
            "EVALUATION_CREDENTIAL_EXPIRED": "CREDENTIAL_EXPIRED",
            "EVALUATION_CREDENTIAL_REVOKED": "CREDENTIAL_REVOKED",
            "EVALUATION_BUDGET_EXHAUSTED": "QUOTA_EXHAUSTED",
        }.get(exc.code, "GATEWAY_UNREACHABLE")
        raise InstallError(code) from None
