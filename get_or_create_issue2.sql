with issue_id as (
    INSERT INTO issues_issue (project_id) VALUES (1)
    WHERE NOT EXISTS (SELECT id from issues_issue where )


    SELECT issues_issue.id
    FROM issues_issue
    INNER JOIN issues_issuehash on issues_issuehash.issue_id = issues_issue.id
    WHERE issues_issuehash.value = 'acbd18db-4cc2-f85c-edef-654fccc4a4d8'::uuid
)
INSERT INTO issues_issuehash (value, issue_id, project_id)
VALUES ('acbd18db-4cc2-f85c-edef-654fccc4a4d8'::uuid, 1, 1)



INSERT INTO issues_issuehash ()




CREATE OR REPLACE FUNCTION get_or_create_issue(_project_id INT, _issue_hash UUID, _level int, _title varchar) RETURNS RECORD AS $$
DECLARE
  ret RECORD;
BEGIN
  LOOP
    SELECT issues_issue.id, issues_issue.status, False as created_issue
    FROM issues_issue
    INNER JOIN issues_issuehash ON issues_issuehash.issue_id = issues_issue.id
    WHERE issues_issuehash.value = _issue_hash AND issues_issuehash.project_id = _project_id
    INTO ret;

    EXIT WHEN FOUND;

    INSERT INTO issues_issue (created, project_id, has_seen, is_public, level, metadata, title, type, status, count, last_seen, tags)
    SELECT now(), _project_id, False, False, _level, '{}'::jsonb, _title, 1, 1, 0, now(), '{}'::jsonb
    WHERE NOT EXISTS (
        SELECT 1 FROM issues_issuehash WHERE issues_issuehash.value = _issue_hash AND issues_issuehash.project_id = _project_id
    )
    RETURNING issues_issue.id, issues_issue.status, True as created_issue
    INTO ret;

    EXIT WHEN FOUND;
  END LOOP;

  if ret.created_issue = True THEN
    INSERT INTO issues_issuehash (issue_id, project_id, value)
    VALUES (ret.id, _project_id, _issue_hash)
    ON CONFLICT DO NOTHING;
  END IF;
return ret;
END;
$$ LANGUAGE plpgsql;;