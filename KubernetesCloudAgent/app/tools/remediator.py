import re
import shutil
from pathlib import Path
from typing import Any

import ansible_runner

from common.session import get_session_id
from controller.postgres import get_postgres_store


class RemediatorTool:
    def __init__(self, output_root: str = "remediation"):
        self.output_root = Path(output_root).resolve()

    def write_file(self, filename: str, content: str) -> dict[str, Any]:
        session_id = get_session_id()
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._session_file(session_dir, filename)
        file_path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "session_id": session_id,
            "session_dir": str(session_dir),
            "filename": filename,
            "path": str(file_path),
            "bytes": len(content.encode("utf-8")),
        }

    def run_ansible(
        self,
        playbook_file: str = "remediation.yml",
        inventory_file: str | None = None,
        check: bool = True,
        extra_vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = get_session_id()
        self._remove_env_folder(session_id)
        session_dir = self._session_dir(session_id)
        playbook_path = self._session_file(session_dir, playbook_file)
        if not playbook_path.exists():
            return {
                "ok": False,
                "executed": False,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "error": f"playbook file not found: {playbook_file}",
            }
        playbook_content = playbook_path.read_text(encoding="utf-8")

        inventory_path = None
        if inventory_file:
            inventory_path = self._session_file(session_dir, inventory_file)
            if not inventory_path.exists():
                return {
                    "ok": False,
                    "executed": False,
                    "session_id": session_id,
                    "session_dir": str(session_dir),
                    "error": f"inventory file not found: {inventory_file}",
                }

        ident = "check" if check else "execute"
        extra_vars = dict(extra_vars or {})

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
            postgres_record = self._record_ansible_run(
                session_id=session_id,
                playbook_content=playbook_content,
                stdout=stdout,
                check=check,
                extra_vars=extra_vars,
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
                "postgres_record": postgres_record,
            }
        except Exception as exc:
            artifact_dir = session_dir / "artifacts" / ident
            stdout_path = artifact_dir / "stdout"
            stdout = (
                stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
            )
            postgres_record = self._record_ansible_run(
                session_id=session_id,
                playbook_content=playbook_content,
                stdout=stdout,
                check=check,
                extra_vars=extra_vars,
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
                "postgres_record": postgres_record,
            }

    def _remove_env_folder(self, session_id: str):
        shutil.rmtree(self._session_dir(session_id) / "env", ignore_errors=True)

    def _record_ansible_run(
        self,
        session_id: str,
        playbook_content: str,
        stdout: str,
        check: bool,
        extra_vars: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            ansible_run_id = get_postgres_store().record_remediation_ansible_run(
                session_id=session_id,
                ansible_file_content=playbook_content,
                stdout=stdout,
                check=check,
                extra_vars=extra_vars,
            )
            return {"ok": True, "id": ansible_run_id}
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "exception_type": type(exc).__name__,
            }

    def _session_dir(self, session_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id).strip("._")
        return self.output_root / (safe or "default")

    def _session_file(self, session_dir: Path, filename: str) -> Path:
        if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
            raise ValueError(f"unsafe filename: {filename}")
        return session_dir / filename

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
