"""Project identity, deterministic brand selection, and package-owned resources."""
from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
SKILL = ENGINE.parents[1]
TEMPLATES = SKILL / 'assets' / 'templates'
TYPES = SKILL / 'references' / 'types'
REPOSITORY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z')

def repository_slug(repository):
    if not REPOSITORY.fullmatch(repository) or any(x in {'.', '..'} for x in repository.split('/')):
        raise ValueError('repository must be an owner/repository identity')
    return re.sub(r'[^a-z0-9]+', '-', repository.lower()).strip('-')

def settings():
    path = SKILL / 'references' / 'projects.json'
    return json.loads(path.read_text()) if path.exists() else {'unraid_repositories': [], 'repositories': {}}

def brand_for(repository, *, unraid_related=False, worktree=None):
    repository_slug(repository)
    owner, name = repository.lower().split('/')
    unraid = (unraid_related or owner in {'unraid', 'limetech'} or name.startswith(('unraid-', 'limetech-'))
              or repository.lower() in settings()['unraid_repositories'])
    if worktree:
        result = subprocess.run(['git', '-C', str(worktree), 'remote', '-v'], text=True, capture_output=True)
        if result.returncode:
            raise ValueError('cannot read project remotes: ' + result.stderr.strip())
        unraid = unraid or bool(re.search(r'github\.com[:/](?:unraid|limetech)/', result.stdout, re.I))
    return 'unraid' if unraid else 'aurora'

def library_root():
    return Path(os.environ.get('ARTIFACTS_ROOT', str(Path.home() / 'artifacts'))).expanduser().resolve()

def selected_brand():
    repository = os.environ.get('ARTIFACTS_REPOSITORY')
    if not repository:
        return 'unraid'  # Compatibility for the original engine's isolated fixtures.
    return brand_for(repository, unraid_related=os.environ.get('ARTIFACTS_UNRAID_RELATED') == '1')

def template_path(category, brand=None):
    family = brand or selected_brand()
    if family not in {'unraid', 'aurora'}:
        raise ValueError('unknown template family')
    suffix = '.md' if category == 'plans' else '.sh' if category == 'scripts' else '.html'
    path = TEMPLATES / family / category / ('_template' + suffix)
    if not path.is_file():
        raise ValueError('unknown artifact type: ' + category)
    return path

def project_identity(folder):
    known = settings().get('repositories', {}).get(folder.name)
    if known:
        return known
    identities = set()
    for path in folder.glob('*/*'):
        if path.suffix not in {'.html', '.md', '.sh', '.py', '.exs', '.cjs', '.mjs'} or not path.is_file():
            continue
        source = path.read_text(errors='replace')[:14000]
        from .catalog import metadata
        value=metadata(source,path.suffix).get('repository')
        if value: identities.add(value)
        identities.update(re.findall(r'<meta name="artifact.repository" content="([^"]+)"', source))
        identities.update(re.findall(r'^artifact.repository:\s*[\"\']?([^\"\'\n]+)', source, re.M))
    identities = {value.strip() for value in identities}
    if len(identities) != 1:
        raise ValueError('repository identity is missing or ambiguous for ' + folder.name)
    identity = identities.pop()
    if repository_slug(identity) != folder.name:
        raise ValueError('repository identity does not match folder ' + folder.name)
    return identity

def assert_project(root, repository):
    """Reject normalized identity collisions and writes through escaping symlinks."""
    root = root.resolve()
    folder = root / repository_slug(repository)
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError('project destination must be a real directory')
    if folder.exists() and any(folder.iterdir()):
        if project_identity(folder).lower() != repository.lower():
            raise ValueError('normalized repository path collides with another owner/repository')
    return folder
