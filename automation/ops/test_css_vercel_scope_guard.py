"""Offline Vercel scope guard tests, including real Git diff command semantics."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from css_vercel_scope_guard import PROJECT,ROOT,IGNORE,assess

class ScopeGuardTests(unittest.TestCase):
    def test_project_skip_guard_matches_exact_configuration(self):
        item={"id":PROJECT,"rootDirectory":ROOT,
              "enableAffectedProjectsDeployments":True,
              "commandForIgnoringBuildStep":IGNORE}
        result=assess(item)
        self.assertEqual(result["skip_guard"],"VERIFIED")
        self.assertFalse(result["production_authorized"])
        self.assertEqual(result["preview_authenticated_browser_e2e"],"NOT_VERIFIED")
        self.assertEqual(result["deployments_created"],0)

    def test_missing_or_wrong_config_never_verifies(self):
        for field,value in [("rootDirectory","research/hcc"),
                            ("enableAffectedProjectsDeployments",False),
                            ("commandForIgnoringBuildStep","echo skip")]:
            item={"id":PROJECT,"rootDirectory":ROOT,
                 "enableAffectedProjectsDeployments":True,
                 "commandForIgnoringBuildStep":IGNORE}
            item[field]=value
            self.assertEqual(assess(item)["skip_guard"],"NOT_VERIFIED")

    def test_wrong_project_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_VERCEL_PROJECT_ID"):
            assess({"id":"other","rootDirectory":ROOT})

    @staticmethod
    def git(base,*args):
        return subprocess.run(["git","-C",str(base),*args],capture_output=True,text=True,check=True)

    def test_ignored_build_step_respects_app_and_lockfile_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            web=root/"apps"/"css-sales-workspace"
            research=root/"research"/"hcc"
            web.mkdir(parents=True)
            research.mkdir(parents=True)
            (web/"index.js").write_text("module.exports=1;\n")
            (research/"experiment.py").write_text("print(1)\n")
            (root/"package.json").write_text("{}\n")
            (root/"package-lock.json").write_text("{}\n")
            self.git(root,"init","--quiet")
            self.git(root,"config","user.name","CI Test")
            self.git(root,"config","user.email","ci@example.invalid")
            self.git(root,"add",".")
            self.git(root,"commit","-qm","init")
            def edit(relative,text):
                (root/relative).write_text(text)
                self.git(root,"add",".")
                self.git(root,"commit","-qm","test")
            def result():
                return subprocess.run(IGNORE,shell=True,cwd=web,stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL).returncode
            edit("research/hcc/experiment.py","print(2)\n")
            self.assertEqual(result(),0,"Research-only change should skip CSS build")
            edit("apps/css-sales-workspace/index.js","module.exports=2;\n")
            self.assertEqual(result(),1,"CSS app changed so build must proceed")
            edit("package-lock.json",'{"lockfileVersion":3}\n')
            self.assertEqual(result(),1,"Root lockfile potentially affects CSS")
            edit("research/hcc/experiment.py","print(3)\n")
            self.assertEqual(result(),0)

    def test_previous_successful_sha_catches_multi_commit_css_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            web=root/"apps"/"css-sales-workspace"
            research=root/"research"/"hcc"
            web.mkdir(parents=True)
            research.mkdir(parents=True)
            (web/"index.js").write_text("a\n")
            (research/"data.py").write_text("a\n")
            (root/"package.json").write_text("{}\n")
            (root/"package-lock.json").write_text("{}\n")
            self.git(root,"init","--quiet")
            self.git(root,"config","user.name","CI Test")
            self.git(root,"config","user.email","ci@example.invalid")
            self.git(root,"add",".")
            self.git(root,"commit","-qm","baseline")
            previous=self.git(root,"rev-parse","HEAD").stdout.strip()
            (web/"index.js").write_text("b\n")
            self.git(root,"add",".")
            self.git(root,"commit","-qm","css changed")
            (research/"data.py").write_text("b\n")
            self.git(root,"add",".")
            self.git(root,"commit","-qm","research changed after css")
            def check(env):
                return subprocess.run(IGNORE,shell=True,cwd=web,env=env,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
            plain=os.environ.copy()
            plain.pop("VERCEL_GIT_PREVIOUS_SHA",None)
            self.assertEqual(check(plain),0,"Single parent does not see older CSS change")
            scoped=plain.copy()
            scoped["VERCEL_GIT_PREVIOUS_SHA"]=previous
            self.assertEqual(check(scoped),1,"Successful-deploy base sees earlier CSS change")
            scoped["VERCEL_GIT_PREVIOUS_SHA"]="deadbeef"
            self.assertNotEqual(check(scoped),0,"Unresolvable base fails open and builds")

if __name__=="__main__":
    unittest.main()
