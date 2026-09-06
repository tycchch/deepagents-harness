from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox


class DockerSandboxBackend(BaseSandbox):
    """Docker sandbox. Container lifecycle stays outside the graph."""

    def __init__(
        self,
        *,
        container_id: str = "",
        workdir: str = "/workspace",
        image: str = "python:3.12-slim",
    ) -> None:
        self._container_id = container_id or "unstarted"
        self._workdir = workdir
        self._image = image

    @property
    def id(self) -> str:
        return self._container_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        raise RuntimeError("Docker sandbox container not started")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error="not_started") for path, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=path, error="not_started") for path in paths]
