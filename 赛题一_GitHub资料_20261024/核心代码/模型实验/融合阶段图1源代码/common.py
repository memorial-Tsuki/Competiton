from pathlib import Path
import hashlib,json,os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def fingerprint():
    records={}
    for folder in ['src','tests','models','data','results']:
        for p in sorted((ROOT/folder).rglob('*')):
            if not p.is_file() or any(x in p.parts for x in ['__pycache__','.mplcache','figures']):continue
            if p.name in ['verification.json','reproduction.json','visual_review.json']:continue
            if p.suffix in ['.py','.joblib','.csv','.json']:records[p.relative_to(ROOT).as_posix()]=digest(p)
    return {'sha256':hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),'files':len(records)}
