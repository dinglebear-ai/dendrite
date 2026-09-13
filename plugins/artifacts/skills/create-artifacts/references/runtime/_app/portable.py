"""Export a fresh portable artifact snapshot without replacing existing work."""
from __future__ import annotations
import html
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import tempfile
from urllib.parse import quote, urlsplit, unquote
from .projects import SKILL

def export_catalog(catalog, destination, embed_fonts):
    from .render import render_index
    destination=destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('export destination already exists: '+str(destination))
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.artifact-export-',dir=destination.parent))
    repos=json.loads((SKILL/'references/legacy-index-meta.json').read_text()).get('repos',{})
    try:
        root=catalog['root'].resolve()
        files={i['href']:i.get('source') for i in catalog['items']}
        by_path={i['href']:i for i in catalog['items']}
        # Retain the complete evidence subtree and paired ledgers for each
        # exported project/type. Never traverse symlinks or copy framework files.
        for folder in ({root/Path(i['href']).parent for i in catalog['items']} | {root/i['project']/'_evidence' for i in catalog['items'] if i.get('project')}):
            for path in folder.rglob('*'):
                rel=path.relative_to(root)
                evidence_file='_evidence' in rel.parts
                if evidence_file and path.is_symlink():raise ValueError('evidence contains a symlink: '+str(rel))
                if not evidence_file and any(p.startswith('.') or p in {'node_modules','__pycache__'} for p in rel.parts): continue
                if path.is_symlink() or not path.is_file(): continue
                if not path.resolve().is_relative_to(root): raise ValueError('evidence escapes artifact root: '+str(rel))
                if not evidence_file and (path.name in {'CLAUDE.md','AGENTS.md','GEMINI.md','README.md'} or path.name.startswith('_template')): continue
                files.setdefault(rel.as_posix(),None)
        for item in catalog['items']:
            if item.get('generated_from'): files.setdefault(item['generated_from'],None)
        files['index.html']=render_index(catalog,False)
        for rel,source in files.items():
            if Path(rel).is_absolute() or '..' in Path(rel).parts:
                raise ValueError('export path escapes artifact root')
            target=stage/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            if source is None:
                shutil.copy2(catalog['root']/rel,target)
                continue
            def citation(match):
                before,path,after,label=match.groups()
                parsed=urlsplit('file://'+path)
                local_path=Path(unquote(parsed.path)).resolve()
                if local_path.is_relative_to(root):
                    linked=local_path.relative_to(root).as_posix()
                    if linked in files:
                        url=posixpath.relpath(linked,posixpath.dirname(rel) or '.')
                        if parsed.fragment: url+='#'+parsed.fragment
                        return '<a'+before+'href="'+html.escape(url,quote=True)+'"'+after+'>'+label+'</a>'
                item=by_path.get(rel,{})
                meta=item.get('meta',{})
                for local,spec in sorted(repos.items(),key=lambda p:-len(p[0])):
                    if path.startswith(local.rstrip('/')+'/'):
                        remainder=path[len(local.rstrip('/'))+1:]
                        # A target SHA belongs to the artifact's own checkout;
                        # companion repository citations keep their own revision.
                        base=spec['base'].rstrip('/')
                        owner_repo=base.removeprefix('https://github.com/').removesuffix('/blob')
                        worktree=meta.get('worktree','').rstrip('/')
                        subject=meta.get('repository') or item.get('repository','')
                        same=(worktree==local.rstrip('/') or owner_repo.lower()==subject.lower()
                              or (catalog.get('aliases') and local=='/Users/jmagar/workspace/core' and subject.endswith('/core')))
                        ref=meta.get('target') if same else None
                        if not ref or not re.fullmatch(r'[0-9a-fA-F]{7,40}',ref): ref=spec.get('ref','main')
                        url=base+'/'+ref+'/'+quote(remainder,safe='/#')
                        return '<a'+before+'href="'+html.escape(url,quote=True)+'"'+after+'>'+label+'</a>'
                return '<span class="unlinked" title="'+html.escape(path,quote=True)+'">'+label+'</span>'
            source=re.sub(r'<a([^>]*?)href="file://([^"]+)"([^>]*)>(.*?)</a>',citation,source,flags=re.S)
            def internal(match):
                path=match[1]
                if path in files:
                    return 'href="'+posixpath.relpath(path,posixpath.dirname(rel) or '.')+'"'
                if path=='': return 'href="'+posixpath.relpath('index.html',posixpath.dirname(rel) or '.')+'"'
                return match[0]
            source=re.sub(r'href="/([^"#]*)"',internal,source)
            source=re.sub(r'<link rel="icon"[^>]*>', '',source)
            target.write_text(embed_fonts(source))
        os.rename(stage,destination)
    except BaseException:
        shutil.rmtree(stage)
        raise
