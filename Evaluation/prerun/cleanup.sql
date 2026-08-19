BEGIN;
TRUNCATE incident_lesson, learning_job, agent_tool_call, remediation_artifact,
         remediation_job, rca_job, anomaly_event, agent_workflow RESTART IDENTITY;
UPDATE agent_execution_slot
   SET holder_type = NULL,
       holder_job_id = NULL,
       lease_owner = NULL,
       lease_expires_at = NULL
 WHERE id = 1;
COMMIT;
