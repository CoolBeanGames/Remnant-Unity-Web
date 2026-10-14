"""Package only compiled browser assets; validate the same bundle in Pages Actions."""
import argparse
import hashlib
import json
import pathlib
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
LIMIT=1_000_000_000
def digest(data):return hashlib.sha256(data).hexdigest()
def validate(folder):
    manifest=json.loads((folder/'game-build.json').read_text())
    assert (folder/'index.html').is_file(), 'Missing game page'
    actual={p.relative_to(folder).as_posix():p for p in folder.rglob('*') if p.is_file()}
    assert set(actual)==set(manifest['files'])|{'game-build.json'}, 'Unexpected/missing published file'
    assert sum(p.stat().st_size for p in actual.values())<LIMIT,'Pages size limit exceeded'
    for name,expected in manifest['files'].items():assert digest(actual[name].read_bytes())==expected,name
    return manifest
def package(folder,output,commit,previous=()):
    build=json.loads((folder/'build.json').read_text())
    source=json.loads((folder/'source.json').read_text())
    for name,expected in source['sha256'].items():
        if name.startswith(('Assets/','Packages/')):assert digest((ROOT/name).read_bytes())==expected,'Rebuild changed input: '+name
    assert build['errors']==0,'Build contains errors'
    files={};retained=[]
    for bundle in previous:
        with zipfile.ZipFile(bundle) as archive:
            old=json.loads(archive.read('game-build.json'))
            for name in old.get('current_files',old['files']):
                if not name.startswith(('Build/','StreamingAssets/','TemplateData/')):continue
                path=pathlib.PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
                data=archive.read(name);assert digest(data)==old['files'][name],name
                files[name]=data
            retained.append({'source_commit':old['source_commit'],'built_utc':old['built_utc']})
    current=[]
    for p in folder.rglob('*'):
        if not p.is_file():continue
        name=p.relative_to(folder).as_posix()
        if name=='index.html' or name.startswith(('Build/','StreamingAssets/','TemplateData/')):
            assert digest(p.read_bytes())==build['files'][name],name
            files[name]=p.read_bytes()
            current.append(name)
    assert files and 'index.html' in files
    files['.nojekyll']=b''
    manifest={'project':'Remnant Unity','unity':build['unity'],'built_utc':build['utc'],
              'source_commit':commit,'build_source_commit':source['source_commit'],
              'mode':build['mode'],'build_warnings':build['warnings'],
              'current_files':sorted(current+['.nojekyll']),'retained_builds':retained,
              'files':{name:digest(data) for name,data in sorted(files.items())}}
    files['game-build.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    assert sum(map(len,files.values()))<LIMIT,'Pages size limit exceeded'
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for name,data in sorted(files.items()):archive.writestr(name,data)
    return {'asset':output.name,'sha256':digest(output.read_bytes()),'source_commit':commit,'built_utc':build['utc'],'bytes':output.stat().st_size}
def extract(bundle,output,expected):
    assert digest(bundle.read_bytes())==expected,'Release bundle hash mismatch'
    output.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(bundle) as archive:
        assert sum(i.file_size for i in archive.infolist())<LIMIT,'Pages size limit exceeded'
        names=archive.namelist();assert len(names)==len(set(names)),'Duplicate archive paths'
        for name in names:
            path=pathlib.PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name,'Unsafe archive path'
        archive.extractall(output)
    return validate(output)
if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    pack=sub.add_parser('package');pack.add_argument('--build',type=pathlib.Path);pack.add_argument('--output',type=pathlib.Path,required=True);pack.add_argument('--commit',required=True)
    unpack=sub.add_parser('extract');unpack.add_argument('--bundle',type=pathlib.Path,required=True);unpack.add_argument('--output',type=pathlib.Path,required=True);unpack.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.command=='package':result=package(args.build or pathlib.Path((ROOT/'Builds/latest-web.txt').read_text().strip()),args.output,args.commit)
    else:result=extract(args.bundle,args.output,args.sha256)
    print(json.dumps(result,indent=2))
