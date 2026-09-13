SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.created_at, t.id), '[]'::json)
FROM agent_workflow t;
