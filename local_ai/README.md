# Windows 16 GB Local AI (Ollama)

### Missing model name: "pull model manifest: file does not exist"

The model `qwen3-codex16k` is a LOCAL custom alias, **not** a registry model.
Do not call `ollama pull qwen3-codex16k` or try to launch Codex before creating it.

One-time direct PowerShell commands:

    $mf = Join-Path $env:TEMP 'Modelfile.codex16k'
    "FROM qwen3:4b`nPARAMETER num_ctx 16384`n" | Set-Content -LiteralPath $mf -Encoding ascii
    ollama create qwen3-codex16k -f $mf
    ollama list
    codex.cmd --oss -m qwen3-codex16k:latest -c 'model_context_window=16384'

Alternatively run `Fix-Codex-4096.cmd`, which also checks the actual allocation.
The **Start-Local-Codex.cmd** launcher now detects a missing `qwen3-codex16k`, calls the local creator automatically, verifies that it was created, then starts Codex. No remote model download for the alias is required.

## Recommended fix when Codex still reports 4096-token context (Nov 21)

If Codex says `request (5875 tokens) exceeds available context (4096 tokens)`, the running Ollama model is still limited to 4K. **Changing only Codex's `model_context_window` does not enlarge Ollama's runtime context.**

**One-time fix:** close Codex, then run **Fix-Codex-4096.cmd**. It creates a NEW local Ollama alias `qwen3-codex16k` from the installed `qwen3:4b`, using this persistent Modelfile:

    FROM qwen3:4b
    PARAMETER num_ctx 16384

It then checks `ollama show --modelfile`, executes a synthetic no-private-data inference, and verifies the real `context_length` returned by local `/api/ps`. It exits nonzero if the server is still allocating 4096 or if memory is insufficient.

**Next time:** use **Start-Local-Codex.cmd**, which now selects `qwen3-codex16k` by default. Direct PowerShell alternative: `codex.cmd --oss -m qwen3-codex16k -c 'model_context_window=16384'`.

The original `qwen3:4b` model remains untouched. This does not require an Administrator sandbox or Internet model API; it only talks to `http://127.0.0.1:11434`. The official Ollama Modelfile docs confirm the `FROM` and `PARAMETER num_ctx` syntax: https://docs.ollama.com/modelfile.

The older **Set-Ollama-Context-16K.cmd** remains as an optional environment-variable fallback, but it does NOT by itself prove that an already-running Ollama process has picked up the configuration. **Verify-Local-Codex-16K.cmd** now checks the new custom alias.

On 16GB RAM, 16K is only the first feasible test size. Ollama recommends a >=64K context for Codex; high context can be prohibitively slow or fail without enough RAM/VRAM. Neither this setup nor CI claims full agent quality at 16K.


## Real Windows context/inference verification (after restarting Ollama)

1. Run **Set-Ollama-Context-16K.cmd** once, if it was not run before.
2. Fully quit Ollama from the Windows tray and relaunch it; close the previous Codex session.
3. Run **Verify-Local-Codex-16K.cmd**. This sends **one synthetic prompt** only to `127.0.0.1:11434`, does not set `options.num_ctx`, and then reads the effective `context_length` from `/api/ps`.
4. Expect **PASS** and `CONTEXT=16384` or greater. If it reports `4096`, check Ollama desktop Settings > Context length and restart Ollama fully, then run again.
5. After PASS, run **Start-Local-Codex.cmd**, type `/status` and confirm the selected model and workspace. Test a short, read-only question.
6. This verification does NOT prove that Codex agent's 5,875-token prompt or large tool-calling tasks are guaranteed to work: it validates the local model response and the loaded context allocation separately. Use a real Codex prompt as a separate acceptance test.

The script performs no credential access, GitHub or Google Drive data transfers, and does not create files. Running an inference loads the model temporarily and may consume considerable RAM.

## Fix Codex's "request exceeds available context size (4096)" error

On a 16GB RAM Windows laptop, Codex may send ~5,875 prompt tokens while Ollama allocates only 4,096. This is a **context-window mismatch**, not npm/Codex installation failure.

**One-time change:** double-click **Set-Ollama-Context-16K.cmd** in this folder. It saves OLLAMA_CONTEXT_LENGTH=16384 in the current user's environment (no Administrator rights); it does not modify your GitHub or Drive credentials.

**Critical:** fully Quit both Codex and Ollama (Ollama tray icon > Quit), then reopen Ollama from the Windows Start menu. A new PowerShell session by itself is NOT enough if the old Ollama server remains running. Another officially supported option is to set Ollama's *Settings > Context length* slider to 16K and restart the model if needed. If the UI setting overrides the environment variable, prefer checking actual loaded context rather than assuming the saved value took effect.

Then open Start-Local-Codex.cmd. The launcher now passes model_context_window=16384 so Codex's conversation budget matches the intended Ollama allocation. **This option does not itself enlarge the Ollama server's actual allocation.**

Use a small, no-file-write prompt to test. From a separate PowerShell after model loading, run:

    ollama ps

The **CONTEXT** column must be 16384 (or at least greater than the prompt size). If it still shows 4096, the previous Ollama process or an app/model-specific override is likely still in effect.

Ollama recommends >=64K for coding agents, but 16K is only a **resource-constrained initial test**, not a guarantee for larger repositories. The 32K or 64K settings may exceed practical 16GB laptop memory limits. For large codebases use smaller task scopes or GitHub-hosted CI, not an unverified huge context.

Source: https://docs.ollama.com/context-length and https://docs.ollama.com/integrations/codex


## GitHub + Google Drive for desktop (mandatory local connections)

A Google Drive connection in ChatGPT is **not** automatically inherited by local Codex CLI. This configuration uses GitHub CLI authentication and Windows Google Drive for desktop sync.

### One-time setup

1. In the Codex Windows sandbox prompt, choose option 1 (default sandbox) with administrator approval if permitted. Do not bypass sandbox policies.
2. Exit Codex for setup, then double-click **Setup-Git-Drive.cmd** from the reviewed local_ai folder.
   - Git for Windows and GitHub CLI are checked; missing tools are installed with winget when available.
   - GitHub CLI uses browser authentication (gh auth login). OAuth approval belongs to the user.
   - The repository kimtk94/Codex is cloned to %USERPROFILE%\Projects\Codex, without overwriting an existing non-Git folder.
   - A Git-ignored local staging folder named .local_ai_data is created in the clone. It is ignored in .git/info/exclude.
3. Separately install [Google Drive for desktop](https://support.google.com/drive/answer/10838124?hl=ko), sign in, and create a folder called LocalAI_Workspace in your Google My Drive. Provide the Windows folder path when prompted, for example G:\My Drive\LocalAI_Workspace.
4. Drive for desktop may stream or mirror; if streaming, make required files available offline for offline work. Confirm that the sync status is fully complete. Folder existence alone cannot prove syncing.
5. The setup saves only local directory paths to %LOCALAPPDATA%\LocalAI\workspace.json (never passwords or tokens).
6. Run **Check-Git-Drive.cmd**. All three checks (GitHub authentication, Git clone, Drive folder) must succeed. A nonzero code 2 means one is pending.
7. Run **Start-Local-Codex.cmd** for normal future use: it starts the local model inside the saved GitHub clone. Run /status and verify provider/model; run /permissions to inspect sandbox access.

### Deliberate, per-file Drive transfers

Code and Git history belong in GitHub. Private research/customer data remain in Google Drive and are NOT automatically uploaded to GitHub.

- Place an approved input file under <Drive LocalAI_Workspace>\inbox.
- Import that single file into Git-ignored local staging (from the cloned repo, after PR merge):

    powershell.exe -NoProfile -File .\local_ai\drive-staging.ps1 -Action Import -FileName "example.csv"

- The approved file becomes available under <repo>\.local_ai_data\inbox.
- Write a reviewed, non-sensitive output into <repo>\.local_ai_data\outbox and export that named file:

    powershell.exe -NoProfile -File .\local_ai\drive-staging.ps1 -Action Export -FileName "result.csv"

- Exports go into <Drive LocalAI_Workspace>\results. No destination overwrites, remote API writes, Git commits or Git pushes occur.
- If using the PR ZIP before merge, the scripts are in that ZIP rather than in the main-branch clone. Use the full script path from the ZIP until PR merge completes.
- Native Google Docs, Sheets and Slides are not automatically editable through a Windows file bridge. Direct edits need a separately authorized Google Workspace MCP/API connection.
- Never commit client records, tokens, identifiable health data or confidential analysis outputs to the public Codex repo. For sensitive workloads use a private Git repository and organization-approved Google Drive.
- Files in arbitrary Drive locations are not automatically accessible to Codex's sandbox. The bridge deliberately imports only approved files into the selected local workspace.

### Manual Git verification

    git --version
    gh --version
    gh auth status
    gh repo view kimtk94/Codex
    git -C "$env:USERPROFILE\Projects\Codex" remote -v

No self-hosted runner is needed for interactive Codex work. Local inference from GitHub Actions requires a separate PRIVATE repository and runner provisioning.


## Recommended one-time setup + daily launch (Windows)

The Windows Ollama app is already installed. No need to install Node.js/npm manually if winget is available.

1. Get the reviewed local_ai folder from this branch/PR (or clone the repo).
2. Double-click **Setup-Local-Codex.cmd** once. This checks Node/npm, installs Node.js LTS through winget only when missing, installs/updates @openai/codex with npm.cmd, checks Ollama localhost, and pulls qwen3:4b if missing. Confirm any installation prompts.
3. Double-click **Check-Local-Codex.cmd** to verify local dependencies.
4. For future coding sessions double-click **Start-Local-Codex.cmd**. It starts Codex CLI in the repository root with an explicitly selected **local** Ollama model. Drag another project folder onto this .cmd file if you want to work in that project.
5. Do not use automatic approvals or the "dangerously bypass" flags. Review generated code and diffs before committing.

To use a different local model from PowerShell (after downloading it with ollama pull):

    .\local_ai\local-codex.ps1 -Mode Start -Model qwen3:1.7b -ProjectPath C:\path\to\project

The launcher uses **codex --oss -m qwen3:4b** and disables web search for that session. The Ollama API is on 127.0.0.1 only, but this is not an air-gapped security guarantee: Codex shell tools may access the network unless separately restricted. Avoid feeding private work data before checking company policy.

**Important:** Ollama recommends at least 64k context for Codex. A 16GB RAM machine with qwen3:4b can be slower or fail on large context/tool-calling work. The setup does **not** automatically increase context to 64k. Start with small isolated coding tasks and verify the model and GPU capability in actual Windows testing.

If PowerShell execution policy blocks the script, verify its contents, then use Unblock-File .\local_ai\local-codex.ps1. Do not change machine-wide execution policies.


**Status:** staged / read-only. This folder does not change CSS, SFDC, Quote, Feishu or research workflows. Inference is NOT executed on public GitHub runners.

## Suggested setup

- Windows 16 GB RAM; GPU not yet identified.
- Initial model: qwen3:4b (official registry, ~2.5 GB download, Q4_K_M). Can run on CPU, but speed may be slow.
- Fallback: qwen3:1.7b (~1.4 GB); upgrade later: qwen3:8b (~5.2 GB) only after checking resources.
- Install Ollama from https://ollama.com/download/windows
- Keep Ollama bound to localhost 127.0.0.1:11434. Do not expose it with OLLAMA_HOST=0.0.0.0, public forwarding or firewall rules.

## Windows laptop steps (PowerShell at cloned repository root)

1. Install the official Windows Ollama application and start it.
2. Install Python 3.10+ if Python is absent. No third-party Python packages required.
3. Inspect hardware, connectivity and model inventory: 
   
       .\local_ai\bootstrap.ps1

4. Download local model (about 2.5 GB):

       .\local_ai\bootstrap.ps1 -PullModel

5. Run synthetic-data smoke test:

       python .\local_ai\ollama_client.py --input .\local_ai\demo_inputs\synthetic_lead.txt --task lead_triage

6. Other commands:

       ollama list
       ollama ps
       python .\local_ai\ollama_client.py --check
       python -m unittest discover -s local_ai/tests -v

If local execution policy blocks the script, review the script and run Unblock-File .\local_ai\bootstrap.ps1. Do not disable PowerShell security machine-wide.

Local result files are stored under %USERPROFILE%\LocalAI_Results by default, not in the repository.

## Guarantees and limitations

- Python talks only to http://127.0.0.1:11434 via Ollama's local API; :cloud model names are rejected.
- No CRM/Feishu write, no mail sending, no Quote pricing, no automatic project updates.
- Each result is draft-only and marked review_required=true. AI output is not verified truth.
- Lead description presence is NOT proof that any outgoing contact occurred. A contacted state requires explicit outbound-mail evidence in supplied data.
- No automatic access to customer emails, Salesforce, files, or private Drive data.
- Real customer data must not be committed to public GitHub, used as workflow inputs/fixtures or exposed in Actions logs/artifacts. Review employer data-handling policies before processing even locally.
- The model itself can be mistaken and produce incomplete JSON. Deterministic checks and human approval remain mandatory before any future writes.

## GitHub Actions integration

- The live .github/workflows/local-ai-offline-checks.yml runs Python tests on a GitHub-hosted Ubuntu runner. No customer data or real Ollama model is used. The green workflow does NOT prove the laptop setup is operational.
- The private runner example is local_ai/templates/private-runner-workflow.yml.example. It is NOT active.
- GitHub specifically discourages self-hosted runners in public repositories. **Never register the Windows laptop as a self-hosted runner for the public Codex repository.**
- To execute model inference by GitHub Actions, create a dedicated PRIVATE repo, copy reviewed local_ai sources there, register a Windows self-hosted runner with label local-ai (Settings > Actions > Runners), and move the example to the private repo's .github/workflows/local-ai-smoke.yml.
- The laptop and Ollama must be online. Restrict who can edit workflows, avoid untrusted pull_request triggers, and grant only contents:read. Sample workflow uses synthetic data and never uploads content.
- Private repo registration is a separate action, not automatically performed here.

## Troubleshooting

- Ollama missing: install official Windows app, reopen PowerShell.
- Localhost unavailable: start Ollama from Start menu and rerun diagnostic.
- Too slow: download smaller model (.\local_ai\bootstrap.ps1 -Model qwen3:1.7b -PullModel), pass --model qwen3:1.7b to client.
- Models empty: model not yet pulled.
- GPU acceleration cannot be assumed until diagnostic identifies device.
