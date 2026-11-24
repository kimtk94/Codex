import tempfile
import unittest
from pathlib import Path
from automation.ops.audit_indirect_git_writes import scan, source_findings, workflow_scripts

class IndirectAuditTests(unittest.TestCase):
    def test_source_flags_git_push_in_local_script(self):
        matches = source_findings('tool.py', "subprocess.run(['git', 'push', 'origin', 'HEAD:main'])")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['signal'], 'git_push')
        self.assertTrue(matches[0]['main_ref_literal'])

    def test_source_flags_git_ref_api(self):
        matches = source_findings('tool.sh', 'gh api --method PATCH repos/x/y/git/refs/heads/main')
        self.assertTrue(any(x['signal'] == 'github_ref_api' for x in matches))
        self.assertTrue(all(x['main_ref_literal'] for x in matches))

    def test_local_source_detection(self):
        body = 'run: python scripts/worker.py && python -m pkg.module'
        found = workflow_scripts(body, {'scripts/worker.py', 'pkg/module.py', 'other.sh'})
        self.assertEqual(found, {'scripts/worker.py', 'pkg/module.py'})

    def test_indirect_trace_blocks_clean_assertion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wf = root / '.github/workflows'
            wf.mkdir(parents=True)
            (root / 'scripts').mkdir()
            (wf / 'probe.yml').write_text(
                'name: probe\non: workflow_dispatch\npermissions:\n  contents: write\njobs:\n  x:\n    steps:\n      - run: python scripts/worker.py\n', encoding='utf-8')
            (root / 'scripts/worker.py').write_text(
                'import subprocess\nsubprocess.run(["git", "push", "origin", "HEAD:main"])\n', encoding='utf-8')
            result = scan(root)
            self.assertEqual(result['workflow_count'], 1)
            self.assertEqual(result['literal_main_write_signals'], 1)
            self.assertEqual(result['workflow_write_permission_count'], 1)
            self.assertEqual(result['status'], 'BLOCK_REVIEW')
            self.assertFalse(result['actions_performed']['branch_protection_mutation'])

    def test_feature_branch_still_requires_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wf = root / '.github/workflows'
            wf.mkdir(parents=True)
            (root / 'scripts').mkdir()
            (wf / 'probe.yml').write_text(
                'jobs:\n  x:\n    steps:\n      - run: python scripts/worker.py\n', encoding='utf-8')
            (root / 'scripts/worker.py').write_text(
                'subprocess.run(["git", "push", "origin", "HEAD:refs/heads/feature/test"])\n', encoding='utf-8')
            report = scan(root)
            self.assertEqual(report['status'], 'REVIEW_REQUIRED')
            self.assertEqual(report['literal_main_write_signals'], 0)
            self.assertGreater(report['indirect_git_write_signals'], 0)

    def test_yaml_job_title_not_shell_command(self):
        self.assertEqual(source_findings('.github/workflows/test.yml', '- name: git push origin HEAD:main'), [])

    def test_empty_workflows_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / '.github/workflows').mkdir(parents=True)
            with self.assertRaises(ValueError):
                scan(root)

if __name__ == '__main__':
    unittest.main()
