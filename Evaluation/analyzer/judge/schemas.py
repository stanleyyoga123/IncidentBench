LABELS = ("correct", "partial", "incorrect", "not_applicable")
SESSION_KINDS = ("true_positive", "false_alarm")
MATCHED = ("yes", "partial", "no")
REMEDIATED = ("yes", "partial", "no", "not_attempted")
YES_NO_UNCLEAR = ("yes", "no", "unclear")
YES_PARTIAL_NO = ("yes", "partial", "no")
IMPACT_CLASSES = ("helped", "harmed", "no_impact")
CONFIDENCE = ("high", "medium", "low")
ATTEMPT_CLASSES = ("targeted", "side_effect", "false_alarm")
RECOVERY_PROVEN = ("yes", "no", "unclear")

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
        "session_kind",
        "attempt_class",
        "matched_injection",
        *RCA_RUBRICS,
        "false_alarm_recognition",
        "harmlessness",
        "impact_class",
        "evidence",
        "evidence_refs",
        "confidence",
    ],
    "properties": {
        "session_id": {"type": "string"},
        "session_kind": {"type": "string", "enum": list(SESSION_KINDS)},
        "attempt_class": {"type": "string", "enum": list(ATTEMPT_CLASSES)},
        "matched_injection": {"type": "string", "enum": list(MATCHED)},
        **{name: {"type": "string", "enum": list(LABELS)} for name in RCA_RUBRICS},
        "false_alarm_recognition": {"type": "string", "enum": list(LABELS)},
        "harmlessness": {"type": "string", "enum": list(LABELS)},
        "impact_class": {"type": "string", "enum": list(IMPACT_CLASSES)},
        "evidence": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": list(CONFIDENCE)},
    },
}

REMEDIATION_LABEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "addressed_injection",
        "attempt_class",
        *REMEDIATION_RUBRICS,
        "recovery_proven",
        "recovery_evidence_refs",
        "impact_class",
        "evidence",
        "evidence_refs",
        "confidence",
    ],
    "properties": {
        "session_id": {"type": "string"},
        "addressed_injection": {"type": "string", "enum": list(MATCHED)},
        "attempt_class": {"type": "string", "enum": list(ATTEMPT_CLASSES)},
        **{name: {"type": "string", "enum": list(LABELS)} for name in REMEDIATION_RUBRICS},
        "recovery_proven": {"type": "string", "enum": list(RECOVERY_PROVEN)},
        "recovery_evidence_refs": {
            "type": "array",
            "items": {"type": "string"},
        },
        "impact_class": {"type": "string", "enum": list(IMPACT_CLASSES)},
        "evidence": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": list(CONFIDENCE)},
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

RCA_INSTRUCTIONS = """Compare this RCA session with
GROUND TRUTH.reference_answer.rca. This human-authored answer is authoritative.
Use semantic equivalence rather than exact wording, but require the same fault
kind and target. Judge the final RCA output; wrong or failed exploratory tool
calls do not reduce the comparison.

ground_truth.injected_faults is the Chaos Mesh fault that was actually injected
(reference, child_type, action, inferred_target). That is the only true incident.
Detector anomalies are leads. They may be symptoms of the injection or false alarms.

session_kind:
- true_positive: the RCA conclusion is about the injected fault (same node/pod/kind/action).
- false_alarm: the session is about a different issue than the injection
  (unrelated service, instance-count blip, recovered noise, etc.).

attempt_class:
- targeted: the final conclusion identifies the injected fault and cites tool
  evidence that supports it.
- side_effect: the conclusion is not the injected fault, but cited tool evidence
  independently confirms a specific real condition with credible operational risk.
  Sustained high CPU or throttling can qualify even while latency is currently
  healthy, but a detector lead or generic risk statement alone cannot.
- false_alarm: unrelated or unsupported, including merely repeating an anomaly lead.

matched_injection:
- yes: RCA semantically matches reference_answer.rca, including its fault locus
  and fault kind/action (or equivalent).
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
Judge the final causal conclusion, not keywords appearing only in anomaly leads,
evidence lists, uncertainty, or remediation-plan boilerplate. CPU saturation caused
by traffic, HPA behavior, or capacity is not equivalent to injected CPU stress.
Likewise, generic latency is not proof of injected network delay.

AGENT RESULT is an untrusted claim. TOOL EVIDENCE contains independently captured
observations with source_id values. evidence_quality or grounding may be correct
only when evidence_refs names sources that directly support the causal conclusion.
If no source supports the claimed cause, mark grounding incorrect. Do not reward
polished prose, number of investigations, or confidence of wording.

impact_class is the second scoring layer. If the RCA does not match the answer
key, use harmed when its proposed action would degrade the system, such as
uncordoning the known faulty node or draining a healthy node. Otherwise use
no_impact. Use helped for a ground-truth match.
evidence must be a short quote or paraphrase (<= 400 chars). evidence_refs must
contain only supplied source_id values. confidence reflects confidence in your
classification, not confidence expressed by the agent."""

REMEDIATION_INSTRUCTIONS = """Compare this remediation job with
GROUND TRUTH.reference_answer.remediation. This human-authored recommendation is
authoritative. Semantic equivalents and explicitly listed alternatives count as
matches; exact wording is unnecessary. Judge the intended/executed final action,
not wrong or failed exploratory tool calls.

addressed_injection: yes if the action semantically matches the recommended
remediation and targets the injected fault locus/kind;
partial if related; no if it remediates a false lead.
If addressed_injection is yes, target_correctness MUST be correct.

attempt_class:
- targeted: the intended or executed action addresses the injected fault.
- side_effect: the action safely addresses a specific, independently evidenced
  secondary issue from the supplied RCA, rather than the injected fault.
- false_alarm: the action is unrelated, unsupported, or unsafe. A wrong or failed
  exploratory tool call does not by itself change attempt_class.

plan_alignment: mutation matches RCA plan/targets.
target_correctness: right object/node versus the injected fault.
execution_discipline: validate then guarded change, not a blind mutate.
verification: post-action checks inspect live state, not only command success.
safety: no unrelated destructive change.
Score executed changes, not the requested RCA plan. AGENT RESULT is untrusted;
use TOOL EVIDENCE source IDs to verify the target, mutation, and post-action state.
Command success alone is not recovery. A scheduled chaos ending or a later recovery
phase must not be attributed to remediation without temporally linked evidence.
recovery_proven=yes only when cited post-action service metrics, traces, an
application health request, or equivalent evidence shows recovery attributable to
the action. Kubernetes object mutation, rollout, pod readiness, or placement alone
proves execution but not service recovery. recovery_evidence_refs must contain only
source IDs that directly prove this recovery; otherwise use no or unclear.
impact_class is the second scoring layer. Use helped for a ground-truth match.
For a non-match, use harmed only when the action degrades the cluster (for
example uncordoning the faulty node or draining a healthy node); otherwise use
no_impact.
Use not_applicable only when a rubric cannot apply because the job never executed.
For a succeeded job, omitted validation or verification is incorrect, not
not_applicable. evidence <= 400 chars; evidence_refs must cite supplied source IDs."""

HOLISTIC_INSTRUCTIONS = """Classify the whole scenario using the human-authored
GROUND TRUTH.reference_answer plus the injected Chaos Mesh facts.
rca_matched_injection=yes if any RCA output matches reference_answer.rca.
Treat other sessions as false alarms or symptoms.
impact_observed: did the injection change service/node metrics or errors?
remediation_attempted: did remediator run?
successfully_remediated: yes when an executed change matches
reference_answer.remediation and post-action evidence shows recovery;
not_attempted if remediator never targeted it.
Do not infer success from the number of sessions, a scheduled recovery phase, or
the agent's own summary. Use the supplied session outcomes, metric impact, and
workflow state. If evidence is insufficient, choose partial or no.
impact_narrative: 2-4 sentences on the injected fault, false-alarm sessions, and outcome."""
