SELECT COALESCE(json_agg(row_to_json(j) ORDER BY j.created_at, j.remediation_job_id), '[]'::json)
FROM (
  SELECT
    r.id AS remediation_job_id,
    r.created_at,
    COALESCE((
      SELECT json_agg(row_to_json(c) ORDER BY c.created_at, c.id)
      FROM agent_tool_call c
      WHERE c.job_id = r.id AND c.service = 'remediator'
    ), '[]'::json) AS tool_calls,
    COALESCE((
      SELECT json_agg(row_to_json(a) ORDER BY a.id)
      FROM remediation_artifact a
      WHERE a.remediation_job_id = r.id
    ), '[]'::json) AS artifacts
  FROM remediation_job r
) j;
