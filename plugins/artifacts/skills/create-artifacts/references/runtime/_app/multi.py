"""Catalog repository-scoped outputs without putting framework files beside them."""
from __future__ import annotations
import hashlib
import json
import posixpath
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from . import validate
from .projects import SKILL, TYPES, brand_for, project_identity, template_path

CATEGORIES = ('reports','pr-reports','proposals','plans','specs','research','sessions','docs','scripts')
SUFFIXES = {'.html','.md','.json','.jsonl','.sh','.py','.exs','.cjs','.mjs'}

def migration(root):
    manifests = sorted(root.glob('jmagar-artifacts/reports/*-artifact-migration.json'))
    if not manifests:
        return {}
    return json.loads(manifests[-1].read_text())

def projected_source(source, old, current, mapping):
    """Repair presentation links, leaving the archived file and evidence bytes intact."""
    def link(match):
        before, href, after = match.groups()
        try:
            parsed = urlsplit(href)
        except ValueError:
            return match.group(0)  # Historical template slots can contain invalid URLs.
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'):
            return match.group(0)
        candidate = posixpath.normpath(posixpath.join(posixpath.dirname(old),parsed.path))
        target = mapping.get(candidate) or mapping.get(parsed.path)
        if not target:
            return match.group(0)
        path = posixpath.relpath(target,posixpath.dirname(current))
        return before + urlunsplit(('', '', path, parsed.query, parsed.fragment)) + after
    return re.sub(r'((?:href|src)=["\'])([^"\']+)(["\'])',link,source)

def load_catalog(root):
    from .catalog import metadata, find, text, plain_blurb, line_of
    root = root.resolve()
    receipt = migration(root)
    mapping = receipt.get('artifact_paths', {})
    inverse = {new: old for old,new in mapping.items()}
    items, issues, stamps = [], [], []
    if not root.is_dir():
        raise FileNotFoundError(root)
    git = subprocess.run(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True,capture_output=True)
    dirty = {line[3:].strip() for line in git.stdout.splitlines()}
    for project in sorted(root.iterdir()):
        if not project.is_dir() or project.is_symlink() or project.name.startswith(('.', '_')):
            continue
        if not any((project / c).is_dir() for c in CATEGORIES):
            continue
        try:
            repository = project_identity(project)
        except ValueError as error:
            issues.append(validate.issue('error',project.name,str(error),'PROJECT-IDENTITY'))
            continue
        for category in CATEGORIES:
            folder = project / category
            if not folder.is_dir() or folder.is_symlink():
                continue
            for path in sorted(folder.iterdir()):
                if (not path.is_file() or path.is_symlink() or path.suffix not in SUFFIXES
                        or path.name.startswith(('.', '_')) or path.name.endswith(('.evidence.jsonl','.manifest.json'))):
                    continue
                rel = path.relative_to(root).as_posix()
                original = path.read_text(errors='replace')
                source = projected_source(original,inverse.get(rel,rel),rel,mapping)
                meta = metadata(source,path.suffix)
                is_legacy = rel in inverse
                brand = meta.get('brand') or ('unraid' if is_legacy and 'UNRAID' in original else brand_for(repository))
                if brand not in {'aurora','unraid'}:
                    issues.append(validate.issue('error',rel,'unknown artifact.brand','BRAND'))
                    brand = brand_for(repository)
                if not is_legacy and brand != brand_for(repository,unraid_related=meta.get('unraid-related')=='true'):
                    issues.append(validate.issue('error',rel,'artifact uses the wrong project template family','BRAND'))
                if not is_legacy and path.suffix in {'.html','.md','.sh'} and meta.get('repository','').lower() != repository.lower():
                    issues.append(validate.issue('error',rel,'artifact.repository must match the project identity','PROJECT-IDENTITY'))
                st = path.stat()
                stamps.append(f'{rel}:{st.st_size}:{st.st_mtime_ns}')
                aside = find(r'<aside class="verified">(.*?)</aside>',source) or ''
                item = {'href':rel,'title':text(find(r'<title>(.*?)</title>',source) or path.stem),
                    'eyebrow':text(find(r'class="eyebrow">(.*?)</div>',source) or ''),
                    'blurb':text(find(r'class="eyebrow">.*?<p>(.*?)</p>',source) or plain_blurb(path,source.splitlines())),
                    'facts':[(text(a),text(b)) for a,b in re.findall(r'<li>\s*<span>(.*?)</span>\s*<strong>(.*?)</strong>',aside,re.S)],
                    'kind':path.suffix.lstrip('.'),'lines':source.count('\n')+1,'bytes':st.st_size,'modified':st.st_mtime,
                    'meta':meta,'id':meta.get('id') or rel,'topic':meta.get('topic','uncategorized'),
                    'status':meta.get('status','unclassified'),'date':meta.get('date',''),'dirty':rel in dirty,
                    'repository':repository,'project':project.name,'category':category,'brand':brand,'legacy':is_legacy,
                    'shas':sorted(set(re.findall(r'\b[0-9a-f]{40}\b',source))), 'references':[], 'related':[]}
                if path.suffix=='.html': item['source']=source
                if path.suffix in {'.html','.md'}:
                    check_source = original if is_legacy else source
                    check_rel = category + '/' + path.name
                    if category=='pr-reports': check_rel='pr-reports/'+project.name+'/'+path.name
                    found = validate.validate_artifact(root,check_rel,check_source,[check_rel],template_path(category,brand).read_text())
                    # Historical findings remain visible; migration never claims to repair old evidence.
                    for problem in found:
                        problem['where']=rel
                        if is_legacy:
                            problem['historical']=True
                        issues.append(problem)
                if path.suffix=='.sh' and not is_legacy:
                    for field in ('repository','brand','id','date','topic','status'):
                        if not meta.get(field): issues.append(validate.issue('error',rel,'missing artifact.'+field,'SCRIPT-META'))
                    if not original.startswith('#!/usr/bin/env bash\n') or 'set -euo pipefail' not in original:
                        issues.append(validate.issue('error',rel,'proof harness requires Bash and set -euo pipefail','SCRIPT-STRUCTURE'))
                    if re.search(r'\{\{|\[One line:|\[HARNESS NAME\]|\[state the claim|\[path\]|\[what a|\[what this',original):
                        issues.append(validate.issue('error',rel,'unresolved proof harness instructions','PLACEHOLDER'))
                    syntax=subprocess.run(['bash','-n',str(path)],text=True,capture_output=True)
                    if syntax.returncode: issues.append(validate.issue('error',rel,syntax.stderr.strip(),'SCRIPT-SYNTAX'))
                item['related_paths'] = [mapping.get(p.strip(),p.strip()) for p in meta.get('related','').split(',') if p.strip()]
                generated=meta.get('generated')
                if generated:
                    old_src=posixpath.join(posixpath.dirname(inverse.get(rel,rel)),generated)
                    src=mapping.get(old_src,posixpath.join(project.name,category,generated))
                    item['generated_from']=src
                    if not (root/src).is_file():
                        issues.append(validate.issue('error',rel,'generated source is missing: '+src,'GENERATED-SOURCE'))
                    elif (root/src).stat().st_mtime_ns>st.st_mtime_ns:
                        issues.append(validate.issue('error',rel,'render is older than its Markdown source','STALE-RENDER'))
                for href,label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',source,re.S):
                    if href.startswith(('file://','https://','http://')):
                        item['references'].append({'href':href,'label':text(label) or href,'line':line_of(source,'href="'+href)})
                items.append(item)
    hidden={i['generated_from'] for i in items if i.get('generated_from')}
    items=[i for i in items if i['href'] not in hidden]
    by_path={i['href']:i for i in items}
    for item in items:
        for other in items:
            if other is item: continue
            explicit=other['href'] in item['related_paths'] or item['href'] in other['related_paths']
            same_topic=(item['repository']==other['repository'] and item['topic']!='uncategorized' and item['topic']==other['topic'])
            if explicit or same_topic:
                item['related'].append({k:other[k] for k in ('href','title','category','status')})
        for related in item['related_paths']:
            if not (root/related).exists() and '[' not in related:
                issues.append(validate.issue('error',item['href'],'related artifact does not exist: '+related,'RELATED-MISSING'))
    ids={}
    for item in items:
        key=(item['repository'],item['id'])
        if key in ids: issues.append(validate.issue('error',item['href'],'duplicate project artifact.id','META-ID-DUPLICATE'))
        ids[key]=item['href']
    groups=[]
    for project in sorted({i['project'] for i in items}):
        for category in CATEGORIES:
            group=[i for i in items if i['project']==project and i['category']==category]
            if group: groups.append({'name':project+'/'+category,'blurb':plain_blurb(TYPES/(category+'.md'),(TYPES/(category+'.md')).read_text().splitlines()),'template':None,'items':group})
    return {'root':root,'groups':groups,'items':items,'issues':issues,'signature':hashlib.sha256('\n'.join(stamps).encode()).hexdigest(),
            'generated_at':datetime.now(timezone.utc),'shas':sorted({s for i in items for s in i['shas']}),'multi_project':True,'aliases':mapping}
