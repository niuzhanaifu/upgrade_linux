from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .config import Settings


PUBLISH_PASSWORD = "300075"
OTA_PACKAGE_PATTERN = re.compile(r"^(?P<timestamp>.+)_(?P<version>[^_]+)_ota\.bin$")
SIGN_ALG = "ecdsa-p256-sha256"


class PublishError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class OtaPublishStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.ota_publish_history_path
        self._lock = threading.Lock()

    def list_records(self) -> list[dict[str, object]]:
        with self._lock:
            return self._load_unlocked()

    def save_record(self, record: dict[str, object]) -> None:
        with self._lock:
            records = self._load_unlocked()
            records.insert(0, record)
            try:
                self._save_unlocked(records[:200])
            except OSError as exc:
                raise PublishError(f"failed to save OTA publish history: {self.path}") from exc

    def _load_unlocked(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _save_unlocked(self, records: list[dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)


def scan_ota_packages(directory: Path) -> list[dict[str, object]]:
    if not directory.exists():
        raise PublishError(f"OTA package directory does not exist: {directory}", 404)
    if not directory.is_dir():
        raise PublishError(f"OTA package path is not a directory: {directory}", 400)

    packages: list[dict[str, object]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        package = package_info(path)
        if package is not None:
            packages.append(package)
    return sorted(packages, key=lambda item: str(item["name"]), reverse=True)


def publish_ota_package(
    settings: Settings,
    store: OtaPublishStore,
    package_name: str,
    password: str,
    board: str | None = None,
) -> dict[str, object]:
    if password != PUBLISH_PASSWORD:
        raise PublishError("发布密码错误", 401)

    source_dir = settings.ota_package_dir
    board_name = normalize_board(board or settings.ota_default_board)
    publish_dir = settings.ota_publish_dir / board_name
    package_path = source_dir / Path(package_name).name

    info = package_info(package_path)
    if info is None or not package_path.is_file():
        raise PublishError(f"OTA package not found: {package_name}", 404)

    publish_dir.mkdir(parents=True, exist_ok=True)
    for child in publish_dir.iterdir():
        if child.is_file() or child.is_symlink():
                try:
                    child.chmod(0o666)
                    child.unlink()
                except OSError as exc:
                    raise PublishError(f"failed to remove old publish package: {child}") from exc

    target_path = publish_dir / package_path.name
    shutil.copy2(package_path, target_path)
    published_info = package_info(target_path)
    if published_info is None:
        raise PublishError(f"invalid published OTA package: {target_path}")

    manifest = build_manifest(settings, board_name, target_path, published_info)
    manifest_path = publish_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)

    record = {
        "id": str(uuid.uuid4()),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "board": board_name,
        "package_name": target_path.name,
        "version": manifest["version"],
        "timestamp": published_info["timestamp"],
        "size": manifest["size"],
        "sha256": manifest["sha256"],
        "sign_alg": manifest["sign_alg"],
        "source_path": str(package_path),
        "publish_path": str(target_path),
        "manifest_path": str(manifest_path),
        "url": manifest["url"],
    }
    store.save_record(record)
    return record


def unpublish_ota_package(
    settings: Settings,
    store: OtaPublishStore,
    password: str,
    board: str | None = None,
) -> dict[str, object]:
    if password != PUBLISH_PASSWORD:
        raise PublishError("发布密码错误", 401)

    board_name = normalize_board(board or settings.ota_default_board)
    publish_dir = settings.ota_publish_dir / board_name
    removed_files: list[str] = []
    failed_remove_files: list[str] = []

    if publish_dir.exists():
        if not publish_dir.is_dir():
            raise PublishError(f"OTA publish path is not a directory: {publish_dir}")
        publish_dir.mkdir(parents=True, exist_ok=True)
        disabled_manifest = {
            "available": False,
            "board": board_name,
            "unpublished_at": datetime.now(timezone.utc).isoformat(),
        }
        with (publish_dir / "manifest.json").open("w", encoding="utf-8") as file:
            json.dump(disabled_manifest, file, ensure_ascii=False, indent=2)
        for child in publish_dir.iterdir():
            if child.name == "manifest.json":
                continue
            if child.is_file() or child.is_symlink():
                try:
                    child.chmod(0o666)
                    child.unlink()
                except OSError as exc:
                    failed_remove_files.append(child.name)
                    continue
                removed_files.append(child.name)
    else:
        publish_dir.mkdir(parents=True, exist_ok=True)
        disabled_manifest = {
            "available": False,
            "board": board_name,
            "unpublished_at": datetime.now(timezone.utc).isoformat(),
        }
        with (publish_dir / "manifest.json").open("w", encoding="utf-8") as file:
            json.dump(disabled_manifest, file, ensure_ascii=False, indent=2)

    record = {
        "id": str(uuid.uuid4()),
        "action": "unpublish",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "board": board_name,
        "package_name": "",
        "version": "",
        "size": 0,
        "source_path": "",
        "publish_path": str(publish_dir),
        "manifest_path": str(publish_dir / "manifest.json"),
        "url": "",
        "removed_files": removed_files,
        "failed_remove_files": failed_remove_files,
        "removed_count": len(removed_files),
    }
    store.save_record(record)
    return record


def package_info(path: Path) -> dict[str, object] | None:
    match = OTA_PACKAGE_PATTERN.match(path.name)
    if match is None:
        return None
    if not path.is_file():
        return None
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "timestamp": match.group("timestamp"),
        "version": match.group("version"),
        "size": stat.st_size,
        "sha256": sha256_file(path),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def normalize_board(board: str) -> str:
    value = board.strip()
    if not value or Path(value).name != value or "/" in value or "\\" in value:
        raise PublishError("invalid board")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(settings: Settings, board: str, path: Path, package: dict[str, object]) -> dict[str, object]:
    size = int(package["size"])
    sha256 = str(package["sha256"]).lower()
    version = str(package["version"])
    url = build_package_url(settings, board, path.name)
    text = signing_text(board, version, url, size, sha256)
    signature = sign_text(settings, text)
    return {
        "board": board,
        "version": version,
        "url": url,
        "size": size,
        "sha256": sha256,
        "sign_alg": SIGN_ALG,
        "signature": signature,
        "force": 1 if settings.ota_force else 0,
        "package_name": path.name,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def build_package_url(settings: Settings, board: str, package_name: str) -> str:
    base_url = settings.ota_public_base_url.rstrip("/")
    return f"{base_url}/firmwares/{board}/{package_name}"


def signing_text(board: str, version: str, url: str, size: int, sha256: str) -> str:
    return f"board={board}\nversion={version}\nurl={url}\nsize={size}\nsha256={sha256}"


def sign_text(settings: Settings, text: str) -> str:
    ensure_signing_keys(settings)
    private_key = load_private_key(settings.ota_sign_private_key_path)
    signature = private_key.sign(text.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature).decode("ascii")


def ensure_signing_keys(settings: Settings) -> None:
    private_path = settings.ota_sign_private_key_path
    public_path = settings.ota_sign_public_key_path
    if private_path.is_file():
        return
    if not settings.ota_auto_generate_test_keys:
        raise PublishError(f"OTA private key not found: {private_path}", 500)

    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)


def load_private_key(path: Path) -> ec.EllipticCurvePrivateKey:
    try:
        private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except Exception as exc:
        raise PublishError(f"failed to load OTA private key: {path}", 500) from exc
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise PublishError(f"OTA private key is not an EC private key: {path}", 500)
    if not isinstance(private_key.curve, ec.SECP256R1):
        raise PublishError("OTA private key must use ECDSA P-256", 500)
    return private_key


def verify_manifest_signature(settings: Settings, manifest: dict[str, object]) -> bool:
    public_path = settings.ota_sign_public_key_path
    if not public_path.is_file():
        return False
    try:
        public_key = serialization.load_pem_public_key(public_path.read_bytes())
        signature = base64.b64decode(str(manifest["signature"]), validate=True)
        text = signing_text(
            str(manifest["board"]),
            str(manifest["version"]),
            str(manifest["url"]),
            int(manifest["size"]),
            str(manifest["sha256"]),
        )
        public_key.verify(signature, text.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False
