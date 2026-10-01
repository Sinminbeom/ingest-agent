from __future__ import annotations

import json
import os
import threading

from python_library.logger.app_logger import AppLogger

from upload.upload_state import BatchUploadState


class UploadStateStore:
    """배치 업로드 진행 상태의 파일 영속화.

    배치당 JSON 파일 하나. 파트 완료마다 저장되므로 tmp 파일에 쓴 뒤
    os.replace로 원자 교체한다 — 저장 도중 전원이 나가도 직전 스냅샷이 남는다.
    """

    DEFAULT_DIR = "./state/upload"

    def __init__(self, dir_path: str = DEFAULT_DIR) -> None:
        self._dir_path = dir_path
        self._lock = threading.Lock()

    def _path(self, batch_public_id: str) -> str:
        return os.path.join(self._dir_path, f"{batch_public_id}.json")

    def save(self, state: BatchUploadState) -> None:
        with self._lock:
            os.makedirs(self._dir_path, exist_ok=True)
            path = self._path(state.batch_public_id)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, ensure_ascii=False)
            os.replace(tmp_path, path)

    def load(self, batch_public_id: str) -> BatchUploadState | None:
        with self._lock:
            path = self._path(batch_public_id)
            if not os.path.isfile(path):
                return None
            return self._read(path)

    def load_all(self) -> list[BatchUploadState]:
        with self._lock:
            if not os.path.isdir(self._dir_path):
                return []
            states: list[BatchUploadState] = []
            for name in sorted(os.listdir(self._dir_path)):
                if not name.endswith(".json"):
                    continue
                state = self._read(os.path.join(self._dir_path, name))
                if state is not None:
                    states.append(state)
            return states

    def delete(self, batch_public_id: str) -> None:
        with self._lock:
            path = self._path(batch_public_id)
            if os.path.isfile(path):
                os.remove(path)

    def _read(self, path: str) -> BatchUploadState | None:
        try:
            with open(path, encoding="utf-8") as f:
                return BatchUploadState.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # 깨진 스냅샷은 재개 불가 — 배치 전체를 막지 않도록 건너뛴다.
            AppLogger.instance().error(f"Broken upload state file: {path} \n {e}")
            return None
