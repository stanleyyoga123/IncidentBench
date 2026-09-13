# Sync run results to Amazon S3

This hook syncs the run output directory to
`<s3_results_uri>/<output-directory-name>/` using the AWS CLI. The bundled global
configuration already selects it after `export-sessions`. For other global or
scenario configurations, select the ordered hooks:

```json
"postrun": ["export-sessions", "upload"]
```

In `config/environment.json`, set a destination you own:

```json
"s3_results_uri": "s3://YOUR-BUCKET/evaluation-results"
```

Leave it `null` to disable uploads. JSON arrays replace inherited arrays, so
include any other post-run hooks you want to retain and put `upload` last.

The Runner requirements include `awscli`. Supply credentials through the AWS
CLI credential chain, such as an IAM role, a configured AWS profile, or
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and (for temporary credentials)
`AWS_SESSION_TOKEN`. Do not place credentials in scenario or environment JSON.
The identity needs access to list the destination prefix and upload its objects.

The hook receives `CONTEXT_JSON OUTPUT_DIR` and runs from the Runner directory.
It syncs only that run's output directory, including exported sessions and
metrics, without `--delete`. Repeating it updates the same destination; choose
unique output directory names to keep separate experiments separate. AWS CLI
failure fails the hook and is recorded by the runner.

The upload captures files available during this post-run phase. Final local
`run-status.json`, release state, and the upload hook's own completed log/status
are written afterward. To refresh S3 with those final files after a run, invoke
this hook again from the Runner directory:

```bash
bash hooks/postrun/upload/run.sh \
  results/MY-RUN/run-context.json results/MY-RUN
```

This command performs a real upload. Local tests mock AWS and upload nothing.
