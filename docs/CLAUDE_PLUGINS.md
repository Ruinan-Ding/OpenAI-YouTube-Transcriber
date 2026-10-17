# Claude workflow plugins

[Project settings](../.claude/settings.json) declare the catalogs and defaults. These tools
support [SAFe/Scrum delivery](../SCRUM_WORKFLOW.md); they do not replace its SDD/vibe intake,
BDD/TDD, owner decisions, file ownership, runtime policy or Definition of Done.

| Plugin ID | Use / default |
|---|---|
| `ponytail@ponytail` | Required by AGENTS.md; enabled. Its installed instructions own Ponytail behavior. |
| `ralph-loop@claude-plugins-official` | Enabled, idle until explicitly invoked; bounded iteration on one ready story. |
| `pyright-lsp@claude-plugins-official` | Enabled; local Python navigation/type information. Mypy and repo tests remain authoritative checks. |
| `commit-commands@claude-plugins-official` | Enabled; commit/push/PR helpers only within the user's publication instruction. |
| `pr-review-toolkit@claude-plugins-official` | Installed, disabled by default; activate for targeted review, then disable locally. |

The toolkit's six extra agent descriptions cost about 1,600 tokens per enabled session in
Claude's local `plugin details` estimate. It is phase-specific, not routine startup context.
Ralph's inactive hook does not start a loop. No automatic full-team reviews or parallel
review swarm are added. These estimates are not measured model usage or billing savings.
Hook output and invoked work can add further context and usage.

## Setup, once per machine/runtime

Native Windows and WSL have separate plugin caches/registries, even with the same checkout.
Project declarations do not download plugins onto another machine. Install in each runtime
you use, with Claude Code's project scope; keep the existing permission/account policy.

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install ralph-loop@claude-plugins-official --scope project
claude plugin install pyright-lsp@claude-plugins-official --scope project
claude plugin install commit-commands@claude-plugins-official --scope project
claude plugin install pr-review-toolkit@claude-plugins-official --scope project
claude plugin disable pr-review-toolkit@claude-plugins-official --scope project
```

Ponytail setup is in [AGENTS.md](../AGENTS.md). For its current optional task-board settings,
this installation uses `--config ledger=false --config sendNames=false` with project install;
no webhook URL/token is configured. These options are machine-local, not credentials in the
repo. Do not configure external reporting as part of workflow setup.

Ralph needs Bash, `jq` and Perl. Native Windows uses Git for Windows' Bash (including Perl)
and `jq` on PATH, e.g. through Scoop. Pyright needs Node.js and `pyright-langserver` on PATH;
`npm install --global pyright` installs that development tool separately from app Python.
On WSL, a user prefix such as `npm install --global --prefix ~/.local pyright` works when
`~/.local/bin` is already on PATH. Do not modify application requirements to install tooling.

Restart Claude or run `/reload-plugins` after changing activation; avoid repeated reloads
that rebuild the prompt cache. Check `claude plugin list --json` and
`claude plugin details <plugin-id>`. Native discovery does not prove live model execution.

## Ralph: bounded, explicit work

Invoke only for an already authorized story with resolved dependent product choices,
accessible tools, concrete AC IDs/checks and one assigned writer. Keep one loop per checkout;
workers do not create nested loops. Always supply a **positive** `--max-iterations`; upstream
omission or zero means unlimited, so installation alone does not enforce this repo rule.

```text
/ralph-loop:ralph-loop "Implement <spec path>#<story>, AC <IDs>. Follow AGENTS.md and the existing SDD/BDD/TDD plan. Keep file ownership and run the specified checks. Output <promise>AC_VERIFIED</promise> only after actual applicable checks pass. On a missing owner decision, tool or account access, cancel and report the blocker." --max-iterations 3 --completion-promise "AC_VERIFIED"
```

Three is a small starting budget, not an application default or a required budget for every
task. Choose an explicit cap proportionate to the story. Do not run vague planning, a whole
PI, pending subtitle decisions, account retries or publishing loops. A cap is not a token/
dollar limit. Stop when blocked with `/ralph-loop:cancel-ralph`; never fake the completion
promise to escape. Reaching the cap or removing state leaves incomplete ACs pending, not Done
or SEEN. The plugin's local state is ignored by Git and must not become a shipped artifact.

## Targeted review and delivery

Enable the toolkit locally for the review phase, preserving the shared disabled default:

```bash
claude plugin enable pr-review-toolkit@claude-plugins-official --scope local
```

Reload once, then select a narrow aspect, e.g. `/pr-review-toolkit:review-pr errors` or
`tests`. Prefer the corresponding single analyst when invoking agents directly. Supply the
spec/AC IDs, readable dirty delta/new files and source-bound evidence. Follow runtime
permission/delegation limits and the existing independent-review requirement.

Upstream `code-reviewer` and `code-simplifier` select Opus; the other four analysts inherit
the session model. Broad `all`, code and simplification reviews can therefore cost more.
Do not automatically invoke every aspect or use a second reviewer that repeats the first.
Project specialists still inherit their lead's model. Restore the local disabled state and
reload when that phase ends:

```bash
claude plugin disable pr-review-toolkit@claude-plugins-official --scope local
```

Use `/commit-commands:commit` or `/commit-commands:commit-push-pr` only when the user's
instruction covers those side effects and checks have passed. Stage only intended files;
preserve other dirty work, branch conventions and secret handling. The PR helper does not
merge or replace Linux/Windows CI. GitHub CLI access is a separate prerequisite; do not
change credentials/account policy to make a validation pass. No PR comments, messages,
merges, model upgrades or extra services are authorized by installing these plugins.

## Selection rationale and evidence

The existing team already owns planning, SDD/BDD/TDD and senior security/reliability review.
Superpowers/feature-dev would introduce a second delivery process; standalone code-review
and code-simplifier duplicate the toolkit/Ponytail. The current security-guidance package
runs model-backed reviews from lifecycle hooks and bootstraps an SDK; it is omitted from
routine startup to preserve the requested token policy. External GitHub/docs MCP servers
are unnecessary while existing CLI/web tools cover those tasks.

Versions, native installs, isolated Windows/WSL Ralph checks, LSP initialization and runtime
limits belong to WF-004 in [the backlog](../SCRUM_BACKLOG.md). Live model review/iteration
and actual usage need separate observation. Unchanged app suites are not plugin tests.

Sources: [Claude plugin management](https://code.claude.com/docs/en/discover-plugins),
[official catalog](https://github.com/anthropics/claude-plugins-official),
[Ralph](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/ralph-loop),
[PR toolkit](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/pr-review-toolkit),
[Pyright](https://github.com/microsoft/pyright), [Ponytail](https://github.com/DietrichGebert/ponytail).
