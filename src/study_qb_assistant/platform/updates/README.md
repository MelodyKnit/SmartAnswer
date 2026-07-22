# Project Update Control Plane

This package implements the application-side control plane for checking and deploying tagged
GitHub Releases. It deliberately does not execute shell commands, access Docker, or retain SSH
credentials. GitHub Actions owns the deployment step and uses repository secrets to invoke
`deploy/remote-release.sh` on the server.

## Responsibilities

- `contracts.py` defines the validated configuration, release, and operation data shapes.
- `github.py` is the GitHub REST adapter. It validates the Release manifest before an update can
  be offered and dispatches only the configured workflow.
- `service.py` coordinates manual checks, optional periodic checks, task recovery, and token
  clearing rules. It persists only non-secret check and operation state through the existing
  settings repository.
- `monitor.py` starts the periodic background cycle only for the real runtime application.

## Configuration

The system configuration page stores the GitHub repository, workflow file, automatic-check
setting, interval (1 to 168 hours), and a write-only access token. The token must be able to read
Release assets and dispatch the configured workflow for the selected repository. Automatic checks
only discover releases; deployment always requires an explicit administrator action.

## Extension And Testing

`ProjectUpdateService` accepts the `ProjectUpdateGateway` protocol, so tests can use a deterministic
gateway without making network calls. A queued task that has no GitHub Actions run after ten
minutes is marked failed instead of permanently blocking future updates.

Run the focused validation with:

```powershell
conda run --no-capture-output -n ai-study-qb python -m pytest tests/test_project_updates.py tests/test_release_deployment.py -q
```
