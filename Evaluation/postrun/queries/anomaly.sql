SELECT COALESCE(json_agg(row_to_json(t) ORDER BY t.detected_at, t.id), '[]'::json)
FROM anomaly_event t;
