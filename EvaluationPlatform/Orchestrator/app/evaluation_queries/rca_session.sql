SELECT COALESCE(json_agg(row_to_json(j) ORDER BY j.created_at, j.id), '[]'::json)
FROM (
  SELECT
    r.*,
    COALESCE((
      SELECT json_agg(row_to_json(c) ORDER BY c.created_at, c.id)
      FROM agent_tool_call c
      WHERE c.job_id = r.id AND c.service = 'rca'
    ), '[]'::json) AS tool_calls
  FROM rca_job r
) j;
