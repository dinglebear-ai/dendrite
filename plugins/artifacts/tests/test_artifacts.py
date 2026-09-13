"""Regression gates for family routing, output isolation, and retained evidence."""
from pathlib import Path
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL=Path(__file__).resolve().parents[1]/'skills/create-artifacts'
ENGINE=SKILL/'references/runtime'
sys.path.insert(0,str(ENGINE))
from _app.projects import brand_for, template_path, project_identity
from _app.catalog import load_catalog, metadata
from _app.asset_files import embed_fonts
from _app.portable import export_catalog

class ArtifactIntegration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.root=self.base/'outputs';self.root.mkdir()
    def cli(self,*args,success=True):
        p=subprocess.run([sys.executable,str(SKILL/'scripts/artifacts.py'),'--root',str(self.root),*map(str,args)],capture_output=True,text=True,timeout=15)
        if success:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        else:self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        return p
    def new(self,repo='acme/relay',type='docs',slug='audit'):
        return Path(json.loads(self.cli('new','--repository',repo,'--type',type,'--slug',slug,'--date','2026-09-13').stdout)['path'])
    def test_routing_and_family_parity(self):
        for repo in ['unraid/core','limetech/docs','dinglebear-ai/core','acme/unraid-addon']:
            self.assertEqual(brand_for(repo),'unraid')
        self.assertEqual(brand_for('acme/relay'),'aurora')
        self.assertEqual(brand_for('acme/relay',unraid_related=True),'unraid')
        for kind in ['reports','pr-reports','proposals','plans','specs','research','sessions','docs','scripts']:
            self.assertTrue(template_path(kind,'aurora').is_file())
            self.assertTrue(template_path(kind,'unraid').is_file())
    def test_script_first_identity_and_scaffold_gate(self):
        script=self.new(type='scripts')
        self.assertEqual(project_identity(script.parent.parent),'acme/relay')
        self.new(slug='second')
        issues=json.loads(self.cli('validate','--path',script,'--json',success=False).stdout)
        self.assertIn('PLACEHOLDER',{i['rule'] for i in issues})
    def test_collision_and_symlink_containment(self):
        self.new(repo='acme-team/relay')
        self.cli('new','--repository','acme/team-relay','--type','docs','--slug','collision',success=False)
        outside=self.base/'outside';outside.mkdir()
        (self.root/'other-relay').symlink_to(outside)
        self.cli('new','--repository','other/relay','--type','docs','--slug','escape',success=False)
        self.assertEqual(list(outside.iterdir()),[])
    def pr_args(self,repo='acme/relay'):
        work=self.base/'checkout';work.mkdir(exist_ok=True)
        sha='a'*40
        return ['--repository',repo,'--branch','feature/audit','--base','main @ '+sha,'--head-sha',sha,'--merge-base',sha,'--worktree',str(work),'--topic','audit','--github-authoritative']
    def test_pr_context_fonts_dates_and_validator(self):
        self.cli('pr-new',*self.pr_args(), '--unraid-related')
        report=next(self.root.rglob('*.html'));source=report.read_text();meta=metadata(source,'.html')
        self.assertEqual(meta['brand'],'unraid');self.assertEqual(meta['unraid-related'],'true')
        self.assertNotRegex(source,r'url\(["\'](?:file:|assets/)[^)]*\.woff2')
        self.assertNotIn('PR-BRANCH',{i['rule'] for i in load_catalog(self.root)['issues']})
        advanced=subprocess.run([sys.executable,str(ENGINE/'scripts/validate-pr-report.py'),str(report),'--root',str(self.root)],capture_output=True,text=True,timeout=15)
        self.assertNotIn('Traceback',advanced.stderr)
        self.assertNotIn('PR-BRANCH',advanced.stdout)
        # Deliberately incomplete dossier must fail content validation, not crash.
        self.assertNotEqual(advanced.returncode,0)
        self.cli('pr-new',*self.pr_args(),success=False)
    def test_pr_symlink_and_aurora_fonts(self):
        outside=self.base/'outside';outside.mkdir();(self.root/'acme-relay').symlink_to(outside)
        self.cli('pr-new',*self.pr_args(),success=False)
        self.assertFalse(list(outside.iterdir()));(self.root/'acme-relay').unlink()
        self.cli('pr-new',*self.pr_args())
        source=next(self.root.rglob('*.html')).read_text()
        self.assertIn('data:font/woff2;base64,',source)
        self.assertNotRegex(source,r'url\(["\']assets/fonts/')
    def test_export_preserves_evidence_and_correct_revision(self):
        report=self.new();sha='b'*40;other='c'*40
        source=report.read_text().replace('content="[commit sha]"','content="'+sha+'"').replace('content="[absolute path of the checkout]"','content="/Users/jmagar/workspace/core"')
        source+='<a href="file:///Users/jmagar/workspace/core/src/a.ex#L3">own</a><a href="file:///Users/jmagar/workspace/phoenix/lib/b.ex">companion</a>'
        report.write_text(source)
        manifest=report.with_suffix('.evidence.jsonl');manifest.write_text('{"captured":true}\n')
        proof=report.parent/'evidence/run/output.txt';proof.parent.mkdir(parents=True);proof.write_text('observed bytes\n')
        destination=self.base/'export';export_catalog(load_catalog(self.root),destination,embed_fonts)
        rendered=(destination/report.relative_to(self.root)).read_text()
        self.assertTrue('/'+sha+'/src/a.ex#L3' in rendered,'own citation is pinned')
        self.assertIn('/phoenix/blob/main/lib/b.ex',rendered)
        self.assertEqual((destination/proof.relative_to(self.root)).read_bytes(),proof.read_bytes())
        self.assertEqual((destination/manifest.relative_to(self.root)).read_bytes(),manifest.read_bytes())
        with self.assertRaises(FileExistsError):export_catalog(load_catalog(self.root),destination,embed_fonts)
    def test_every_html_family_has_embedded_fonts_and_stable_pr_sections(self):
        for family in ['aurora','unraid']:
            for kind in ['reports','pr-reports','proposals','specs','research','sessions','docs']:
                source=embed_fonts(template_path(kind,family).read_text())
                self.assertNotRegex(source,r'url\(["\'](?:file:|assets/)[^)]*\.woff2')
        ids=lambda family:re.findall(r'<section[^>]*\bid="([^"]+)"',template_path('pr-reports',family).read_text())
        self.assertEqual(ids('aurora'),ids('unraid'))

    def test_generic_plan_header_and_discovery_output_root(self):
        from _app.validate import check_plan
        self.assertNotIn('PLAN-HEADER',{i['rule'] for i in check_plan('plans/example.md',template_path('plans','aurora').read_text())})
        spec=importlib.util.spec_from_file_location('discover_draft_test',ENGINE/'scripts/generate-pr-report-draft.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        work=self.base/'work';work.mkdir()
        sha='a'*40
        context={'pr':{'head_branch':'feature/audit','head_sha':sha,'base_branch':'main','base_sha':sha,'merge_base':sha,'number':1,'state':'OPEN','url':'https://github.com/acme/relay/pull/1','files':[]}}
        real_run=helper.run
        def fake_run(*args,capture=False):
            args=list(map(str,args));name=Path(args[1]).name
            if name=='discover-pr-context.py':
                self.assertEqual(args[args.index('--artifacts-root')+1],str(self.root))
                Path(args[args.index('--output')+1]).write_text(json.dumps(context));return ''
            if name=='new-pr-report.py':return real_run(*args,capture=capture)
            return ''
        with patch.dict(os.environ,{'ARTIFACTS_ROOT':str(self.root)}), patch.object(sys,'argv',['discover','--repository','acme/relay','--pr','1','--worktree',str(work),'--unraid-related']),patch.object(helper,'run',fake_run):
            self.assertEqual(helper.main(),0)
        proof=next(self.root.glob('acme-relay/_evidence/*/*/raw/context.json'))
        self.assertEqual(json.loads(proof.read_text()),context)
        report=next(self.root.glob('acme-relay/pr-reports/*.html'))
        self.assertEqual(metadata(report.read_text(),'.html')['brand'],'unraid')

if __name__=='__main__':unittest.main()
