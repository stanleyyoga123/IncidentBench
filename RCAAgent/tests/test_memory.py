from common.memory import (
    ENTRY_END,
    ENTRY_START,
    RCA_END,
    RCA_START,
    REMEDIATION_END,
    SessionMemoryEntry,
    SessionMemoryStore,
)


def test_new_memory_entries_are_rca_only(tmp_path):
    path = tmp_path / "MEMORY.md"
    store = SessionMemoryStore(path, max_prompt_chars=4096)

    store.append(
        SessionMemoryEntry(
            session_id="job-1",
            prompt="investigate checkout",
            orchestration_output="root cause evidence",
            remediation_required=True,
        )
    )

    content = path.read_text()
    assert "root cause evidence" in content
    assert "### Remediation" not in content
    assert "remediation result" not in content


def test_legacy_remediation_is_accepted_but_not_injected(tmp_path):
    path = tmp_path / "MEMORY.md"
    path.write_text(
        f"""{ENTRY_START}
## Session legacy

### Root Cause Analysis

{RCA_START}
legacy evidence
{RCA_END}

### Remediation

<!-- cloudagent-memory-remediation:start -->
legacy mutation instructions
{REMEDIATION_END}
{ENTRY_END}
"""
    )
    store = SessionMemoryStore(path, max_prompt_chars=4096)

    context = store.load_prompt_context()

    assert "legacy evidence" in context
    assert "legacy mutation instructions" not in context
    assert "### Remediation" not in context
