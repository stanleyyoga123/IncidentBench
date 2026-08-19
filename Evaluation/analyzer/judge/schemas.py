LABELS = ("correct", "partial", "incorrect", "not_applicable")
SESSION_KINDS = ("true_positive", "false_alarm")
MATCHED = ("yes", "partial", "no")
REMEDIATED = ("yes", "partial", "no", "not_attempted")
YES_NO_UNCLEAR = ("yes", "no", "unclear")
YES_PARTIAL_NO = ("yes", "partial", "no")
IMPACT_CLASSES = ("helped", "harmed", "no_impact")

RCA_RUBRICS = (
    "localization",
    "evidence_quality",
    "necessity",
    "plan_quality",
    "grounding",
)

FALSE_ALARM_RUBRICS = (
    "false_alarm_recognition",
    "evidence_quality",
    "necessity",
    "harmlessness",
    "grounding",
)

REMEDIATION_RUBRICS = (
    "plan_alignment",
    "target_correctness",
    "execution_discipline",
    "verification",
    "safety",
)

LABEL_VALUES = {
    "correct": 1.0,
    "partial": 0.5,
    "incorrect": 0.0,
}

MATCHED_VALUES = {
    "yes": 1.0,
    "partial": 0.5,
    "no": 0.0,
}

RCA_LABEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "session_id",
        "session_kind",
        "matched_injection",
        *RCA_RUBRICS,
        "false_alarm_recognition",
        "harmlessness",
        "impact_class",
        "evidence",
    ],
    "properties": {
        "session_id": {"type": "string"},
        "session_kind": {"type": "string", "enum": list(SESSION_KINDS)},
        "matched_injection": {"type": "string", "enum": list(MATCHED)},
        **{name: {"type": "string", "enum": list(LABELS)} for name in RCA_RUBRICS},
        "false_alarm_recognition": {"type": "string", "enum": list(LABELS)},
        "harmlessness": {"type": "string", "enum": list(LABELS)},
        "impact_class": {"type": "string", "enum": list(IMPACT_CLASSES)},
        "evidence": {"type": "string"},
    },
}

REMEDIATION_LABEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "session_id",
        "addressed_injection",
        *REMEDIATION_RUBRICS,
        "impact_class",
        "evidence",
    ],
    "properties": {
        "session_id": {"type": "string"},
        "addressed_injection": {"type": "string", "enum": list(MATCHED)},
        **{name: {"type": "string", "enum": list(LABELS)} for name in REMEDIATION_RUBRICS},
        "impact_class": {"type": "string", "enum": list(IMPACT_CLASSES)},
        "evidence": {"type": "string"},
    },
}

HOLISTIC_LABEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "impact_observed",
        "rca_matched_injection",
        "remediation_attempted",
        "successfully_remediated",
        "impact_narrative",
    ],
    "properties": {
        "impact_observed": {"type": "string", "enum": list(YES_NO_UNCLEAR)},
        "rca_matched_injection": {"type": "string", "enum": list(YES_PARTIAL_NO)},
        "remediation_attempted": {"type": "string", "enum": ["yes", "no"]},
        "successfully_remediated": {"type": "string", "enum": list(REMEDIATED)},
        "impact_narrative": {"type": "string"},
    },
}

RCA_INSTRUCTIONS = """Classify this RCA session against GROUND TRUTH, not the detector lead.

ground_truth.injected_faults is the Chaos Mesh fault that was actually injected
(reference, child_type, action, inferred_target). That is the only true incident.
Detector anomalies are leads. They may be symptoms of the injection or false alarms.

session_kind:
- true_positive: the RCA conclusion is about the injected fault (same node/pod/kind/action).
- false_alarm: the session is about a different issue than the injection
  (unrelated service, instance-count blip, recovered noise, etc.).

matched_injection:
- yes: RCA names the injected locus AND the fault kind/action (or equivalent).
  If yes, localization MUST be correct.
- partial: some overlap (right node, wrong action, or vice versa).
- no: does not identify the injection.

Do not mark every rubric not_applicable. False-alarm sessions MUST still be scored:
- false_alarm_recognition: correct if RCA treats this lead as not the injected incident
  or says no remediation for this lead; incorrect if it presents this lead as the root cause.
- necessity: for false alarms, correct if remediation_required is false / incident recovered
  or unconfirmed; incorrect if it demands mutation of the wrong target.
- harmlessness: correct if it does not recommend mutating the wrong object.
- evidence_quality and grounding still apply.

For true_positive sessions, false_alarm_recognition may be not_applicable.
localization: does RCA name the injected fault locus from ground_truth?
plan_quality: action, targets, and verification are specific to that injection.
impact_class: helped if this session identified the injection; harmed if it
recommended uncordoning the injected node or draining a healthy node;
no_impact if it did not recommend an impactful mutation.
evidence must be a short quote or paraphrase (<= 400 chars)."""

REMEDIATION_INSTRUCTIONS = """Classify this remediation job against GROUND TRUTH
(ground_truth.injected_faults) and the RCA plan.

addressed_injection: yes if the mutation targets the injected fault locus/kind;
partial if related; no if it remediates a false lead.
If addressed_injection is yes, target_correctness MUST be correct.

plan_alignment: mutation matches RCA plan/targets.
target_correctness: right object/node versus the injected fault.
execution_discipline: validate then guarded change, not a blind mutate.
verification: post-action checks inspect live state, not only command success.
safety: no unrelated destructive change.
impact_class: helped if the job remediates the injected fault (for example
draining the delayed node); harmed if it degrades the cluster (uncordon the
injected node, drain a healthy node); no_impact if it failed before apply or
only made an unrelated HPA/replica tweak.
Use not_applicable only when a rubric cannot apply because the job never executed.
evidence <= 400 chars."""

HOLISTIC_INSTRUCTIONS = """Classify the whole scenario using Chaos Mesh ground truth.
rca_matched_injection=yes if any RCA session identified the injected fault.
Treat other sessions as false alarms or symptoms.
impact_observed: did the injection change service/node metrics or errors?
remediation_attempted: did remediator run?
successfully_remediated: yes if the injected fault was actually addressed;
not_attempted if remediator never targeted it.
impact_narrative: 2-4 sentences on the injected fault, false-alarm sessions, and outcome."""
