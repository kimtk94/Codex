#!/usr/bin/env python3
"""Conservative read-only static audit of GitHub Actions indirect Git writes.

It never mutates branches and cannot establish the absence of indirect writes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
from pathlib import Path

SOURCE_EXT = {'.py', '.sh', '.bash', '.js', '.cjs', '.mjs', '.ts', '.tsx', '.ps1'}
WF_EXT = {'.yml', '.yaml'}
FILE_TOKEN = re.compile(r'(?<![\w/])(?:\./)?([\w.-]+(?:/[\w.-]+)+\.(?:py|sh|bash|js|cjs|mjs|ts|tsx|ps1))\b')
MODULE_TOKEN = re.compile(r'\bpython(?:3(?:\.\d+)?)?\s+-m\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)')
WORKFLOW_REUSE = re.compile(r'\buses\s*:\s*(?:\./)?(\.github/workflows/[\w.-]+\.ya?ml)')
WRITE_PATTERNS = {
    'git_push': re.compile(r'\bgit(?:\s+-C\s+(?:\S+|"[^"]+"))?\s+push\b|["\']git["\']\s*,\s*["\']push["\']', re.I),
    'git_ref_mutation': re.compile(r'\bgit\s+(?:update-ref|push|receive-pack)\b|\b(?:updateRef|createRef|deleteRef)\s*\(|\b(?:git\.refs\.update|git_refs\.update)\b', re.I),
    'github_ref_api': re.compile(r'(?:/git/refs(?:/heads)?|/git/refs/heads/main|\bgh\s+api\b.{0,80}\b(?:PATCH|POST|PUT|DELETE)\b)', re.I),
    'github_content_api': re.compile(r'(?:createOrUpdateFileContents|create_or_update_file_contents|github\.rest\.repos\.(?:createOrUpdateFileContents|deleteFile)|\bgh\s+api\b.{0,80}/contents/)', re.I),
    'pr_merge_api': re.compile(r'(?:mergePullRequest|merge_pull_request|\bgh\s+pr\s+merge\b)', re.I),
}
MAIN_REF = re.compile(r'(?:\bHEAD:refs/heads/main\b|\bHEAD:main\b|\b(?:origin|upstream)\s+main\b|git/refs/heads/main\b)', re.I)
PERMISSION = re.compile(r'^\s*(?:contents|pull-requests|workflows|actions)\s*:\s*write\s*(?:#.*)?$', re.I | re.M)
SCRIPT_CMD = re.compile(r'\b(?:python(?:3(?:\.\d+)?)?|bash|sh|node|npx|npm|yarn|pnpm)\b')
IGNORED_PREFIXES = ('#', '//', '*', '"""', "'''")

def source_findings(relative: str, content: str) -> list[dict]:
    findings = []
    for lineno, line in enumerate(content.splitlines(), 1):
        code = line.strip()
        if not code or code.startswith(IGNORED_PREFIXES):
            continue
        if relative.startswith('.github/workflows/') and re.match(
            r'^(?:-\s*)?(?:name|description|display-name|run-name)\s*:', code, re.I
        ):
            continue
        for kind, pattern in WRITE_PATTERNS.items():
            if pattern.search(line):
                context = ('test_fixture' if Path(relative).name.startswith('test_')
                           else 'audit_pattern_definition' if relative.endswith('audit_indirect_git_writes.py')
                           else 'unreviewed_executable')
                findings.append({'source': relative, 'line': lineno, 'signal': kind,
                                 'main_ref_literal': bool(MAIN_REF.search(line)),
                                 'context': context})
    return findings

def workflow_scripts(body: str, paths: set[str]) -> set[str]:
    found = set()
    for match in FILE_TOKEN.finditer(body):
        path = match.group(1)
        if path in paths:
            found.add(path)
    for match in MODULE_TOKEN.finditer(body):
        path = match.group(1).replace('.', '/') + '.py'
        if path in paths:
            found.add(path)
    return found

def scan(root: Path) -> dict:
    root = root.resolve(strict=True)
    workflow_dir = root / '.github' / 'workflows'
    if not workflow_dir.is_dir():
        raise ValueError('Missing workflow directory')
    workflows = sorted(p for p in workflow_dir.iterdir() if p.is_file() and p.suffix in WF_EXT)
    if not workflows:
        raise ValueError('No workflow files')
    sources = {p.relative_to(root).as_posix(): p for p in root.rglob('*')
               if p.is_file() and p.suffix.lower() in SOURCE_EXT
               and not any(x in p.parts for x in ('.git', 'node_modules', 'dist', 'build', '.next', '.venv'))}
    source_cache: dict[str, list[dict]] = {}
    findings: list[dict] = []
    inventory: list[dict] = []
    for wf in workflows:
        wf_rel = wf.relative_to(root).as_posix()
        body = wf.read_text(encoding='utf-8')
        scripts = workflow_scripts(body, set(sources))
        reused = sorted(set(WORKFLOW_REUSE.findall(body)))
        external = sorted(set(re.findall(r'^\s*-?\s*uses\s*:\s*([^\s#]+)', body, flags=re.M))
                          - set('./' + x for x in reused))
        for item in source_findings(wf_rel, body):
            findings.append({'workflow': wf_rel, **item, 'via': 'inline_workflow'})
        for rel in sorted(scripts):
            if rel not in source_cache:
                source_cache[rel] = source_findings(rel, sources[rel].read_text(encoding='utf-8'))
            for item in source_cache[rel]:
                findings.append({'workflow': wf_rel, **item, 'via': 'referenced_script'})
        can_write = bool(PERMISSION.search(body))
        if can_write or scripts or reused:
            inventory.append({'workflow': wf_rel, 'write_permission_declared': can_write,
                              'referenced_source_files': sorted(scripts), 'reusable_workflows': reused,
                              'external_action_count': len(external),
                              'external_actions': external[:20],
                              'has_untraced_execution': bool(reused or external or SCRIPT_CMD.search(body))})
    main_refs = sum(bool(f['main_ref_literal']) for f in findings)
    indirect_signals = sum(f['via'] == 'referenced_script' for f in findings)
    executable_main_candidates = sum(f['main_ref_literal'] and f['context'] == 'unreviewed_executable' for f in findings)
    return {
        'schema_version': 1,
        'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'status': 'BLOCK_REVIEW' if executable_main_candidates else 'REVIEW_REQUIRED',
        'workflow_count': len(workflows),
        'repo_sources_indexed': len(sources),
        'referenced_source_files_inspected': len(source_cache),
        'workflow_write_permission_count': sum(bool(x['write_permission_declared']) for x in inventory),
        'indirect_git_write_signals': indirect_signals,
        'literal_main_write_signals': main_refs,
        'executable_main_write_candidates': executable_main_candidates,
        'findings': findings,
        'write_capability_inventory': inventory,
        'limitations': [
            'Only files explicitly mentioned in workflow text are inspected; imported and transitively invoked scripts are not fully traced',
            'Existing or third-party GitHub Actions may write to GitHub even without a literal git push command',
            'Credential inheritance, default GITHUB_TOKEN permissions and external tokens are not proven safe',
            'This report cannot alone justify activating branch protection; review paths and test rules first',
        ],
        'actions_performed': {'git_write': False, 'branch_protection_mutation': False,
                              'workflow_dispatch': False}
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        report = scan(a.root)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('INDIRECT_AUDIT_STATUS:', report['status'])
        for key in ('workflow_count', 'repo_sources_indexed', 'referenced_source_files_inspected',
                    'workflow_write_permission_count', 'indirect_git_write_signals', 'literal_main_write_signals'):
            print(key.upper() + ':', report[key])
        unique = {}
        for finding in report['findings']:
            key = (finding['source'], finding['line'], finding['signal'], finding['main_ref_literal'])
            unique.setdefault(key, set()).add(finding['workflow'])
        print('EXECUTABLE_MAIN_WRITE_CANDIDATES:', report['executable_main_write_candidates'])
        for item in report['write_capability_inventory']:
            if item['write_permission_declared']:
                print('WRITE_CAPABLE_WORKFLOW:', item['workflow'])
        print('UNIQUE_WRITE_SIGNAL_LOCATIONS:', len(unique))
        for (source, line, signal, main_ref), workflows in sorted(unique.items()):
            print('WRITE_SIGNAL:', source + ':' + str(line), signal,
                  'main_ref=' + str(main_ref), 'referenced_by=' + str(len(workflows)))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print('INDIRECT_AUDIT_FAILED:', type(exc).__name__, str(exc)[:200])
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
