SELECT COALESCE(json_agg(row_to_json(j) ORDER BY j.created_at, j.id), '[]'::json)
FROM (
  SELECT
    l.*,
    COALESCE((
      SELECT json_agg(row_to_json(i) ORDER BY i.ordinal, i.id)
      FROM incident_lesson i
      WHERE i.learning_job_id = l.id
    ), '[]'::json) AS lessons
  FROM learning_job l
) j;
