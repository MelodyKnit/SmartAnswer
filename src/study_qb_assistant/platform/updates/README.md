# Project Update Control Plane

This package reads the latest tagged public GitHub Release for the system configuration page. It
does not execute shell commands, access Docker, retain GitHub credentials, or trigger deployment.
GitHub Actions owns the release and deployment steps.

## Responsibilities

- `contracts.py` defines the validated configuration, release, and operation data shapes.
- `github.py` is the anonymous GitHub REST adapter. It validates the Release manifest before an
  update is reported.
- `service.py` coordinates manual checks and persists only non-secret check state through the
  existing settings repository.

## Configuration

The official repository `MelodyKnit/SmartAnswer` is the default release source. A release image
normally injects its repository through `STQB_SOURCE_REPOSITORY`; a valid value overrides the
default for a fork or a separately released deployment. Release checks are anonymous and only
discover updates. They never deploy the application.

## Extension And Testing

`ProjectUpdateService` accepts the `ProjectUpdateGateway` protocol, so tests can use a deterministic
gateway without making network calls.

Run the focused validation with:

```powershell
conda run --no-capture-output -n ai-study-qb python -m pytest tests/test_project_updates.py tests/test_release_deployment.py -q
```
