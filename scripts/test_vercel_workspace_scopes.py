"""Validate Vercel automatic deployment-skip workspace definitions (no secrets)."""
import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths=json.loads((ROOT/"package.json").read_text())["workspaces"]

    def test_all_workspaces_named_and_private(self):
        names=[]
        for path in self.paths:
            manifest=ROOT/path/"package.json"
            self.assertTrue(manifest.is_file(),str(manifest))
            p=json.loads(manifest.read_text())
            self.assertTrue(p.get("private"),path)
            names.append(p["name"])
        self.assertEqual(len(names),len(set(names)))

    def test_css_and_kalman_are_distinct_app_scopes(self):
        self.assertIn("apps/css-sales-workspace",self.paths)
        self.assertIn("research/kalman_triple_barrier/web",self.paths)
        css=json.loads((ROOT/"apps/css-sales-workspace/package.json").read_text())
        kal=json.loads((ROOT/"research/kalman_triple_barrier/web/package.json").read_text())
        self.assertNotEqual(css["name"],kal["name"])
        self.assertTrue((ROOT/"apps/css-sales-workspace/index.html").is_file())
        self.assertTrue((ROOT/"research/kalman_triple_barrier/web/index.html").is_file())

    def test_automation_and_github_are_not_global_changes(self):
        for path in [".github","automation","research/kalman_triple_barrier",
                     "research/upbit_eth","scripts","docs"]:
            self.assertIn(path,self.paths)

    def test_lockfile_if_committed_matches_workspace_list(self):
        lock=ROOT/"package-lock.json"
        if lock.exists():
            payload=json.loads(lock.read_text())
            self.assertEqual(sorted(payload["packages"][""]["workspaces"]),
                             sorted(self.paths))
            self.assertTrue(all(k in payload["packages"]
                                for k in self.paths))

if __name__=="__main__":unittest.main()
