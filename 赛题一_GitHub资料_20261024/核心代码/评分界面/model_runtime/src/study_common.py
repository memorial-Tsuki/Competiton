from pathlib import Path
import hashlib,json,os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
ROOT=Path(__file__).resolve().parents[1]
SEEDS=[20260923,101,211,307,401,503]
VERSION='delinquency-development-20260928'
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path,x):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')
