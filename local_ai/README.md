# Windows 16 GB Local AI (Ollama)

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
