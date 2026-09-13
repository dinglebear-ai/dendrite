from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_artifacts as common
SKILL=common.SKILL
from _app import evidence
from _app.catalog import load_catalog, metadata
from _app.contracts import check_content

class EvidenceIntegration(unittest.TestCase):
    setUp=common.ArtifactIntegration.setUp
    cli=common.ArtifactIntegration.cli
    new=common.ArtifactIntegration.new
    def test_new_content_contract_rejects_missing_record_parts(self):
        report=self.new(type='reports')
        source=report.read_text()
        item=next(i for i in load_catalog(self.root)['items'] if i['href']==report.relative_to(self.root).as_posix())
        self.assertEqual(item['meta']['contract-version'],'1')
        self.assertEqual(check_content(item,source),[])
        broken=source.replace('class="limit"','class="removed"')
        self.assertIn('CONTENT-STRUCTURE',{i['rule'] for i in check_content(item,broken)})
        empty='<details class="issue"><div class="trace"></div><div class="evidence"></div><div class="links"></div><div class="limit"></div></details>'
        self.assertTrue(check_content(item,empty))
    def test_evidence_integrity_and_nonexecution(self):
        report=self.new();folder=evidence.start(self.root,report,'capture-1','model-run')
        (folder/'raw/input.txt').write_text('original source\n')
        (folder/'raw/README.md').write_text('captured documentation')
        (folder/'raw/.settings').write_text('captured configuration')
        (folder/'derived/model.txt').write_text('generated inference\n')
        self.assertTrue(evidence.verify(self.root,folder)['errors'])
        evidence.seal(self.root,folder,'fixture capture')
        self.assertEqual(evidence.verify(self.root,folder)['errors'],[])
        self.assertEqual(evidence.inventory(self.root,load_catalog(self.root))['model_runs'],1)
        with self.assertRaises(ValueError):evidence.seal(self.root,folder,'again')
        (folder/'raw/input.txt').write_text('changed\n')
        self.assertTrue(evidence.verify(self.root,folder)['errors'])
    def test_lossless_organization_and_old_links(self):
        report=self.new(type='reports',slug='review')
        old=report.parent/'evidence/review';old.mkdir(parents=True)
        (old/'observed.json').write_text('{"result":"original"}\n')
        before=(old/'observed.json').read_bytes()
        plan=evidence.organization_plan(self.root,load_catalog(self.root))
        self.assertEqual(plan['file_count'],1)
        result=evidence.organize(self.root,plan)
        self.assertEqual(result['moved_files'],1)
        self.assertTrue(old.is_symlink())
        self.assertEqual((old/'observed.json').read_bytes(),before)
        canonical=self.root/plan['moves'][0]['destination']
        self.assertEqual(evidence.verify(self.root,canonical.parent)['errors'],[])
        counts=evidence.inventory(self.root,load_catalog(self.root))
        self.assertEqual(counts['evidence_files'],2)  # retained observation + administrative receipt
        self.assertEqual(counts['catalog_items'],1)
        self.assertEqual(evidence.organization_plan(self.root,load_catalog(self.root))['file_count'],0)
    def test_changed_source_rejects_without_moving(self):
        report=self.new(type='reports',slug='review')
        old=report.parent/'evidence/review';old.mkdir(parents=True);(old/'raw.txt').write_text('first')
        plan=evidence.organization_plan(self.root,load_catalog(self.root));(old/'raw.txt').write_text('second')
        with self.assertRaises(ValueError):evidence.organize(self.root,plan)
        self.assertFalse(old.is_symlink());self.assertEqual((old/'raw.txt').read_text(),'second')
    def test_organization_rolls_back_on_receipt_failure(self):
        report=self.new(type='reports',slug='review')
        old=report.parent/'evidence/review';old.mkdir(parents=True);(old/'raw.txt').write_text('preserve')
        plan=evidence.organization_plan(self.root,load_catalog(self.root));original=evidence.write_json
        def fail_receipt(path,data,exclusive=False):
            if 'organization' in path.parts:raise OSError('simulated receipt failure')
            return original(path,data,exclusive)
        with patch.object(evidence,'write_json',fail_receipt),self.assertRaises(OSError):evidence.organize(self.root,plan)
        self.assertFalse(old.is_symlink());self.assertEqual((old/'raw.txt').read_text(),'preserve')
    def test_evidence_root_symlink_refused(self):
        report=self.new();outside=self.base/'outside';outside.mkdir()
        (report.parent.parent/'_evidence').symlink_to(outside)
        with self.assertRaises(ValueError):evidence.start(self.root,report,'escape')
        self.assertEqual(list(outside.iterdir()),[])
    def test_export_contains_canonical_evidence(self):
        report=self.new();folder=evidence.start(self.root,report,'capture-1');raw=folder/'raw/result.txt';raw.write_text('actual')
        (folder/'raw/README.md').write_text('captured docs')
        (folder/'raw/.settings').write_text('captured settings')
        evidence.seal(self.root,folder,'fixture')
        self.cli('export','--out',self.base/'export')
        self.assertEqual((self.base/'export'/raw.relative_to(self.root)).read_text(),'actual')
        self.assertFalse(evidence.verify(self.base/'export',self.base/'export'/folder.relative_to(self.root))['errors'])
    def test_bad_bundle_and_export_snapshot_do_not_inflate_live_runs(self):
        report=self.new();folder=evidence.start(self.root,report,'run-1','model-run')
        (folder/'raw/a.txt').write_text('a');evidence.seal(self.root,folder,'fixture')
        self.cli('export','--out',self.root/'acme-relay/exports/snapshot')
        bad=self.root/'acme-relay/_evidence/bad/run';bad.mkdir(parents=True);(bad/evidence.BUNDLE).write_text('{}')
        counts=evidence.inventory(self.root,load_catalog(self.root))
        self.assertEqual(counts['model_runs'],1);self.assertEqual(counts['evidence_bundles'],1)
        self.assertEqual(len(counts['invalid_bundles']),1)
    def test_organization_rejects_linked_evidence_and_receipt_parent(self):
        report=self.new(type='reports',slug='review');old=report.parent/'evidence/review';old.mkdir(parents=True)
        (old/'a.txt').write_text('a');(old/'link').symlink_to('a.txt')
        with self.assertRaises(ValueError):evidence.organization_plan(self.root,load_catalog(self.root))
        (old/'link').unlink();plan=evidence.organization_plan(self.root,load_catalog(self.root))
        outside=self.base/'outside';outside.mkdir();(self.root/'jmagar-artifacts').symlink_to(outside)
        with self.assertRaises(ValueError):evidence.organize(self.root,plan)
        self.assertFalse(old.is_symlink());self.assertEqual(list(outside.iterdir()),[])
    def test_rendered_plan_validation_includes_its_markdown(self):
        plan=self.new(type='plans');source=plan.read_text().split('### Task 1:')[0];plan.write_text(source)
        self.cli('render-plan',plan)
        result=json.loads(self.cli('validate','--path',plan.with_suffix('.html'),'--json',success=False).stdout)
        self.assertIn('PLAN-TASKS',{i['rule'] for i in result})
    def test_root_guidance_is_only_a_pointer(self):
        self.cli('init-root')
        self.assertTrue((self.root/'AGENTS.md').is_symlink())
        self.assertEqual((self.root/'AGENTS.md').resolve(),SKILL/'references/output-AGENTS.md')
        self.cli('init-root')

if __name__=='__main__':unittest.main()
