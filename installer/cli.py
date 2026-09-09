"""Common resumable installer. Thin host launchers supply Docker and browser integration."""

import argparse
import os

from installer import credential, release
from installer.errors import InstallError
from installer.services import DockerServices
from installer.state import State, private_write
from src.evaluator.direct_registry import DirectRegistrySession


class Installer:
    def __init__(
        self,
        state,
        services,
        *,
        locations=(),
        discover=credential.discover,
        unlock=credential.unlock,
        resolve=release.resolve,
        unpack=release.unpack,
        direct_path=None,
        expected_revision=None,
        expected_digest=None,
    ):
        self.state, self.services = state, services
        self.locations, self.discover, self.unlock = locations, discover, unlock
        self.resolve, self.unpack = resolve, unpack
        self.direct_path = direct_path
        self.expected_revision = expected_revision
        self.expected_digest = expected_digest

    def image_identity(self, *, running=False):
        result = self.services.verify_image_identity(
            self.expected_revision, self.expected_digest, running=running
        )
        print("IMAGE_SOURCE_IDENTITY = PASS")
        if running:
            print("RUNNING_API_REVISION =", result["api_revision"])
            print("RUNNING_API_DIGEST =", result["api_digest"])
            print("RUNNING_BROKER_REVISION =", result["sandbox-broker_revision"])
            print("RUNNING_BROKER_DIGEST =", result["sandbox-broker_digest"])
        return result

    def discover_credential(self, bundle=None):
        if self.direct_path is None:
            return self.discover(self.locations, bundle)
        return self.discover(self.locations, bundle, direct_path=self.direct_path)

    def readiness(self, session, *, record_stage=True):
        if isinstance(session, DirectRegistrySession):
            if record_stage:
                self.state.stage("DIRECT_REGISTRY_READINESS")
            for name, value in session.metadata.items():
                print(f"{name}: {value}")
            print("Direct registry CONFIGURED; provider calls 0; not live-provider verified.")
        else:
            if record_stage:
                self.state.stage("GATEWAY_READINESS")
            print("Credential PASS · Gateway ALLOWED · Paid upstream calls 0")
            for route in session.metadata["routes"]:
                print(f"{route}: ALLOWED")

    def preflight(self):
        s = self.state
        s.stage("SYSTEM_CHECK")
        s.stage("RUNTIME_CHECK")
        self.services.check()
        s.stage("RUNTIME_INSTALL_OR_GUIDE")
        self.services.ports()

    def start(self, *, bundle=None, no_open=False, full_proof=False, checked=False):
        s = self.state
        if not checked:
            self.preflight()
        self.image_identity()
        del full_proof  # The packaged runtime always preserves the same strict Proof policy.
        s.stage("LOCAL_STORAGE_INIT")
        self.services.storage()
        s.stage("RUNTIME_DEPENDENCY_CHECK")
        self.services.runtime_dependencies()
        s.stage("DATABASE_INIT")
        self.services.database()
        s.stage("MIGRATION")
        self.services.migrate()
        s.stage("CREDENTIAL_DISCOVERY")
        path = self.discover_credential(bundle)
        s.save(credential_name=path.name)
        s.stage("CREDENTIAL_UNLOCK")
        session = self.unlock(path)
        self.readiness(session)
        s.stage("SERVICE_START")
        self.services.start(session)
        del session
        s.stage("HEALTH_CHECK")
        self.services.health()
        self.image_identity(running=True)
        print("Database ............. READY")
        print("Backend .............. READY")
        print("Frontend ............. READY")
        print("Proof Runtime ........ READY / RISC Zero 3.0.6")
        print("Sandbox Runtime ...... READY / governed broker")
        if not no_open:
            s.stage("OPEN_BROWSER")
            self.open_browser()
        s.stage("READY")
        s.save(ready=True, error=None)
        print("Verifiable Financial Agent is ready.\nhttp://127.0.0.1:4173")

    def open_browser(self):
        # Host launcher consumes this fixed non-secret signal with the OS default browser.
        private_write(self.state.root / "open-browser", "http://127.0.0.1:4173")

    def install(self, *, version=None, source=False, **start_args):
        self.preflight()
        s = self.state
        s.stage("RELEASE_RESOLUTION")
        if source:
            # Explicit source mode: the host launcher already built this reviewed directory.
            selected, image = "source", self.services.image
            revision, image_digest = self.expected_revision, self.expected_digest
            s.stage("PRODUCT_INSTALL")
        else:
            manifest = self.resolve(version)
            selected = manifest["version"]
            s.stage("DOWNLOAD")
            directory = self.unpack(manifest, s.root / "releases" / selected)
            s.stage("INTEGRITY_VERIFY")
            image = "vfa-evaluator:" + selected.lower()
            s.stage("PRODUCT_INSTALL")
            self.services.image = image
            revision = manifest.get("commit")
            if not isinstance(revision, str):
                raise InstallError("RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED")
            self.services.install(directory, selected, revision)
            image_digest = self.services.command(
                ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                "RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED",
            )
            self.services.image = image_digest
            image = image_digest
            self.expected_revision, self.expected_digest = revision, image_digest
        # Do not mark a release current until its image build succeeds.
        s.save(version=selected, image=image, revision=revision, image_digest=image_digest)
        private_write(s.root / "image", image)
        private_write(s.root / "revision", revision)
        private_write(s.root / "image-digest", image_digest)
        self.start(checked=True, **start_args)

    def doctor(self, bundle=None):
        print("VFA Doctor")
        self.services.check()
        print("Docker PASS")
        print("Product version:", self.state.data.get("version", "not installed"))
        print(self.services.status())
        self.image_identity()
        self.services.runtime_dependencies()
        self.services.health()
        self.image_identity(running=True)
        path = self.discover_credential(bundle)
        session = self.unlock(path)
        self.readiness(session, record_stage=False)
        del session
        print("Database ............. READY")
        print("Backend .............. READY")
        print("Frontend ............. READY")
        print("Proof Runtime ........ READY / RISC Zero 3.0.6")
        print("Sandbox Runtime ...... READY / governed broker")
        print("Paid upstream calls 0")


def main():
    parser = argparse.ArgumentParser(description="Verifiable Financial Agent")
    parser.add_argument(
        "command",
        choices=["install", "start", "stop", "status", "doctor", "update", "open"],
        nargs="?",
        default="start",
    )
    parser.add_argument("--root", default="/install")
    parser.add_argument("--host-root", default=os.environ.get("VFA_HOST_ROOT"))
    parser.add_argument("--image", default="vfa-evaluator:source")
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-image-digest")
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--version")
    parser.add_argument("--bundle")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--full-proof", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    state = None
    try:
        state = State(args.root)
        (state.root / "open-browser").unlink(missing_ok=True)
        if args.command in {"start", "doctor"}:
            if state.data.get("image") not in {None, args.image}:
                raise InstallError("STALE_RUNTIME_IMAGE")
            if state.data.get("revision") not in {None, args.expected_revision}:
                raise InstallError("STALE_RUNTIME_IMAGE")
            if state.data.get("image_digest") not in {None, args.expected_image_digest}:
                raise InstallError("STALE_RUNTIME_IMAGE")
        services = DockerServices(args.root, args.host_root or args.root, args.image)
        installer = Installer(
            state,
            services,
            locations=["/credentials/downloads", "/credentials/desktop"],
            direct_path="/credentials/product/active.vfacred",
            expected_revision=args.expected_revision,
            expected_digest=args.expected_image_digest,
        )
        if args.command in {"install", "update"}:
            installer.install(
                version=args.version,
                source=args.source,
                bundle=args.bundle,
                no_open=args.no_open,
                full_proof=args.full_proof,
            )
        elif args.command == "start":
            installer.start(bundle=args.bundle, no_open=args.no_open, full_proof=args.full_proof)
        elif args.command == "stop":
            services.stop()
            state.save(ready=False)
            print("VFA stopped. Research data retained.")
        elif args.command == "status":
            print(services.status())
        elif args.command == "doctor":
            installer.doctor(bundle=args.bundle)
        elif args.command == "open":
            services.health()
            installer.open_browser()
    except InstallError as exc:
        _record_error(state, exc.code)
        print(str(exc))
        raise SystemExit(1) from None
    except Exception:
        _record_error(state, "INSTALLATION_FAILED")
        print(str(InstallError("INSTALLATION_FAILED")))
        raise SystemExit(1) from None


def _record_error(state, code):
    if state is not None:
        try:
            state.save(error=code, ready=False)
        except Exception:
            pass  # Storage errors must not expose a traceback or credential context.


if __name__ == "__main__":
    main()
