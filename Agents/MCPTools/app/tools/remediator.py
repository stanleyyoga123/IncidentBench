import re
import shutil
import hashlib
import json
from pathlib import Path
from typing import Any

import ansible_runner

class RemediatorTool:
    def __init__(self, output_root: str = "remediation"):
        self.output_root = Path(output_root).resolve()

    def write_file(self, session_id: str, filename: str, content: str) -> dict[str, Any]:
        session_dir = self._session_dir(session_id)
        try:
            file_path = self._session_file(session_dir, filename)
        except ValueError as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "filename": filename,
                "error": str(exc),
            }
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "session_id": session_id,
            "session_dir": str(session_dir),
            "filename": file_path.name,
            "path": str(file_path),
            "bytes": len(content.encode("utf-8")),
        }

    def run_ansible(
        self,
        session_id: str,
        playbook_file: str = "remediation.yml",
        inventory_file: str | None = None,
        check: bool = True,
        extra_vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._remove_env_folder(session_id)
        session_dir = self._session_dir(session_id)
        try:
            playbook_path = self._session_file(session_dir, playbook_file)
            inventory_path = (
                self._session_file(session_dir, inventory_file) if inventory_file else None
            )
        except ValueError as exc:
            return {
                "ok": False,
                "executed": False,
                "check": check,
                "session_id": session_id,
                "error": str(exc),
            }
        if not playbook_path.exists():
            return {
                "ok": False,
                "executed": False,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "error": f"playbook file not found: {playbook_file}",
            }
        playbook_content = playbook_path.read_text(encoding="utf-8")
        if inventory_path is not None and not inventory_path.exists():
            return {
                "ok": False,
                "executed": False,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "error": f"inventory file not found: {inventory_file}",
            }

        ident = "check" if check else "execute"
        extra_vars = dict(extra_vars or {})
        execution_contract = {
            "playbook_sha256": hashlib.sha256(playbook_content.encode()).hexdigest(),
            "inventory_sha256": (
                hashlib.sha256(inventory_path.read_bytes()).hexdigest()
                if inventory_path else None
            ),
            "extra_vars": extra_vars,
        }
        execution_sha256 = hashlib.sha256(
            json.dumps(execution_contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        check_record = session_dir / ".approved-check.json"
        if not check:
            if not check_record.exists():
                return {
                    "ok": False,
                    "executed": False,
                    "check": False,
                    "error": "live execution requires a successful check-mode run",
                }
            try:
                approved = json.loads(check_record.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                approved = {}
            if approved.get("execution_sha256") != execution_sha256:
                return {
                    "ok": False,
                    "executed": False,
                    "check": False,
                    "error": "execution inputs changed after check mode; run check mode again",
                }

        try:
            runner = ansible_runner.run(
                private_data_dir=str(session_dir),
                playbook=str(playbook_path),
                inventory=str(inventory_path) if inventory_path else None,
                cmdline="--check" if check else None,
                extravars=extra_vars,
                ident=ident,
            )
            artifact_dir = session_dir / "artifacts" / ident
            stdout_path = artifact_dir / "stdout"
            stdout = (
                stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
            )
            stats = getattr(runner, "stats", None)
            changed_summary = self._changed_summary(stats)
            if check and runner.rc == 0:
                check_record.write_text(
                    json.dumps({"execution_sha256": execution_sha256}),
                    encoding="utf-8",
                )
            return {
                "ok": runner.rc == 0,
                "executed": True,
                "check": check,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "artifact_dir": str(artifact_dir),
                "playbook_file": str(playbook_path),
                "inventory_file": str(inventory_path) if inventory_path else None,
                "status": runner.status,
                "returncode": runner.rc,
                "stdout": stdout.strip(),
                "stats": stats,
                "changed": changed_summary["changed"],
                "changed_summary": changed_summary,
            }
        except Exception as exc:
            artifact_dir = session_dir / "artifacts" / ident
            stdout_path = artifact_dir / "stdout"
            stdout = (
                stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
            )
            return {
                "ok": False,
                "executed": True,
                "check": check,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "playbook_file": str(playbook_path),
                "inventory_file": str(inventory_path) if inventory_path else None,
                "error": str(exc),
                "exception_type": type(exc).__name__,
            }

    def _remove_env_folder(self, session_id: str):
        shutil.rmtree(self._session_dir(session_id) / "env", ignore_errors=True)

    def _session_dir(self, session_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id).strip("._")
        return self.output_root / (safe or "default")

    def _session_file(self, session_dir: Path, filename: str) -> Path:
        return session_dir / self._safe_name(filename)

    @staticmethod
    def _safe_name(filename: str) -> str:
        text = str(filename or "").replace("\\", "/").strip()
        path = Path(text)
        if not text or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe filename: {filename}")
        name = path.name
        if name in {"", ".", ".."}:
            raise ValueError(f"unsafe filename: {filename}")
        return name

    def _changed_summary(self, stats: Any) -> dict[str, Any]:
        if not isinstance(stats, dict):
            return {"changed": False, "hosts": {}, "total_changed": 0}

        hosts: dict[str, Any] = {}
        total_changed = 0
        for host, values in stats.items():
            if not isinstance(values, dict):
                continue
            changed = int(values.get("changed") or 0)
            total_changed += changed
            hosts[host] = {
                "changed": changed,
                "ok": int(values.get("ok") or 0),
                "failures": int(values.get("failures") or 0),
                "unreachable": int(values.get("unreachable") or 0),
                "skipped": int(values.get("skipped") or 0),
            }

        return {
            "changed": total_changed > 0,
            "hosts": hosts,
            "total_changed": total_changed,
        }
