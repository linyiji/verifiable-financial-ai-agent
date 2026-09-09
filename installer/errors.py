"""Owned, secret-free errors with a single next action."""

MESSAGES = {
    "DIRECT_CREDENTIAL_NOT_FOUND": (
        "Direct credential bundle not found. Expected credentials/active.vfacred."
    ),
    "DIRECT_CREDENTIAL_UNLOCK_FAILED": "Credential bundle unlock failed. Use hidden input.",
    "DIRECT_CREDENTIAL_AUTHENTICATION_FAILED": (
        "Credential bundle authentication failed. Check the passphrase and file."
    ),
    "DIRECT_CREDENTIAL_FORMAT_UNSUPPORTED": "Unsupported credential bundle format.",
    "CREDENTIAL_MODE_CONFLICT": (
        "Conflicting credential modes. Remove the override or the fixed direct bundle."
    ),
    "DOCKER_NOT_INSTALLED": "Install Docker Desktop when prompted, then run the installer again.",
    "DOCKER_NOT_RUNNING": "Start Docker Desktop, then run vfa start.",
    "REBOOT_REQUIRED": "Restart Windows once, then run the same install command again.",
    "PUBLICATION_REQUIRED": "No installer release yet. Use the documented source install command.",
    "DOWNLOAD_FAILED": "Check your connection to GitHub, then run vfa update.",
    "INTEGRITY_FAILED": "Package verification failed. Do not run it; contact the Owner.",
    "PORT_4173_IN_USE": "Close the other application on port 4173, then run vfa start.",
    "PORT_8010_IN_USE": "Close the other application on port 8010, then run vfa start.",
    "DATABASE_START_FAILED": "Check Docker Desktop storage and run vfa doctor.",
    "MIGRATION_FAILED": "Database update failed; data retained. Run vfa doctor; contact the Owner.",
    "NO_EVALUATOR_CREDENTIAL": "Put the Owner-issued .vfaeval in Downloads, then run vfa start.",
    "INVALID_EVALUATOR_CREDENTIAL": "Check the bundle and passphrase, then run vfa start.",
    "GATEWAY_NOT_DEPLOYED": "Ask Owner for a deployed gateway and bundle, then run vfa start.",
    "GATEWAY_UNREACHABLE": "Check connection and gateway availability, then run vfa start.",
    "CREDENTIAL_EXPIRED": "Ask the Owner for a new credential, then run vfa start.",
    "CREDENTIAL_REVOKED": "Ask the Owner to resolve authorization, then run vfa start.",
    "QUOTA_EXHAUSTED": "Ask the Owner to resolve evaluation limits, then run vfa start.",
    "HEALTH_TIMEOUT": "Services did not become ready. Run vfa doctor.",
    "PROOF_RUNTIME_NOT_READY": "Packaged Proof Runtime is not ready.",
    "SANDBOX_RUNTIME_NOT_READY": "Governed Sandbox Runtime is not ready.",
    "INSTALLATION_FAILED": "Installation paused; data retained. Retry or run vfa doctor.",
}


class InstallError(RuntimeError):
    def __init__(self, code):
        self.code = code if code in MESSAGES else "INSTALLATION_FAILED"
        super().__init__(f"{self.code}: {MESSAGES[self.code]}")
