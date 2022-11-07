CREATE OR REPLACE FUNCTION event_preprocess (_project_id numeric, _sentry_key uuid, _release_name text, _environment_name text, OUT _organization_id int, OUT _has_diffs boolean, OUT _is_accepting_events boolean, OUT _should_scrub_ip_addresses boolean, OUT _release_id int, OUT _environment_id int)
AS $$
DECLARE
  _first_event timestamp with time zone;
BEGIN
  SELECT
    INTO _organization_id,
    _first_event,
    _is_accepting_events,
    _should_scrub_ip_addresses,
    _has_diffs,
    _release_id,
    _environment_id --
    projects_project.organization_id,
    projects_project.first_event,
    is_accepting_events,
    projects_project.scrub_ip_addresses,
    EXISTS (
      SELECT
        1
      FROM
        difs_debuginformationfile
      WHERE
        project_id = _project_id
      LIMIT 1) AS has_diffs,
  releases_release.id,
  environments_environment.id
FROM
  projects_project
  INNER JOIN projects_projectkey ON (projects_project.id = projects_projectkey.project_id)
  INNER JOIN organizations_ext_organization ON (projects_project.organization_id = organizations_ext_organization.id)
  LEFT JOIN releases_releaseproject ON projects_project.id = releases_releaseproject.project_id
  LEFT JOIN releases_release ON (releases_release.id = releases_releaseproject.release_id
      AND releases_release.version = _release_name)
  LEFT JOIN environments_environmentproject ON projects_project.id = environments_environmentproject.project_id
  LEFT JOIN environments_environment ON (environments_environment.id = environments_environmentproject.environment_id
      AND environments_environment.name = _environment_name)
WHERE (projects_project.id = _project_id
    AND projects_projectkey.public_key = _sentry_key);
  IF _organization_id IS NOT NULL AND _project_id::int::bool THEN
    -- Get release_id, if not known and it exists
    IF _release_name IS NOT NULL AND _release_id IS NULL THEN
      SELECT
        INTO _release_id id
      FROM
        releases_release
      WHERE
        releases_release.organization_id = _organization_id
        AND releases_release.version = _release_name
      LIMIT 1;
      -- If no release, create it
      IF _release_id IS NULL THEN
        INSERT INTO releases_release (version, organization_id, created, data, commit_count, deploy_count)
          VALUES (_release_name, _organization_id, now(), '{}'::json, 0, 0)
        RETURNING
          id INTO _release_id;
      END IF;
      -- Insert project - release relationship if it doesn't exist
      INSERT INTO releases_releaseproject (project_id, release_id)
        VALUES (_project_id, _release_id)
      ON CONFLICT
        DO NOTHING;
    END IF;
    -- Get environment_id, if it exists
    IF _environment_name IS NOT NULL AND _environment_id IS NULL THEN
      SELECT
        INTO _environment_id environments_environment.id
      FROM
        environments_environment
      LEFT JOIN environments_environmentproject ON environments_environmentproject.environment_id = environments_environment.id
    WHERE
      environments_environment.organization_id = _organization_id
        AND environments_environment.name = _environment_name
      LIMIT 1;
      -- If no environment, create it
      IF _environment_id IS NULL THEN
        INSERT INTO environments_environment (name, organization_id, created)
          VALUES (_environment_name, _organization_id, now())
        RETURNING
          id INTO _environment_id;
      END IF;
      -- Insert project-environment relationship if not exists
      INSERT INTO environments_environmentproject (project_id, environment_id, is_hidden, created)
        VALUES (_project_id, _environment_id, FALSE, now())
      ON CONFLICT
        DO NOTHING;
    END IF;
    -- If not first event, set the project first event
    IF _first_event IS NULL THEN
      UPDATE
        projects_project
      SET
        first_event = now()
      WHERE
        id = _project_id;
    END IF;
  END IF;
END;
$$
LANGUAGE plpgsql;

