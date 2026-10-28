"""Retrain every new candidate from frozen cohort and frozen baseline inputs."""
from study_common import ROOT,digest,write_json
from pathlib import Path
import sys,shutil,subprocess,uuid,json,platform
import numpy as np,pandas as pd

NUMERIC=['study_common.py','risk_model.py','evaluation.py','delinquency_model.py','run_experiment.py','run_shared.py','analyze_results.py']
PROTOCOLS=['实验协议.md','协议补充_B.md','协议补充_C.md']
def compare_json(a,b):
    if isinstance(a,dict):
        assert a.keys()==b.keys()
        for k in a:compare_json(a[k],b[k])
    elif isinstance(a,list):
        assert len(a)==len(b)
        for x,y in zip(a,b):compare_json(x,y)
    elif isinstance(a,(int,float)) and not isinstance(a,bool):np.testing.assert_allclose(a,b,rtol=1e-10,atol=1e-12,equal_nan=True)
    else:assert a==b,(a,b)
def main():
    fresh=ROOT.parent/'tmp'/('delinquency-reproduction-'+uuid.uuid4().hex[:12]);fresh.mkdir(parents=True)
    inputs={}
    for folder in ['data','baseline']:
        shutil.copytree(ROOT/folder,fresh/folder)
        for p in (ROOT/folder).rglob('*'):
            if p.is_file():inputs[p.relative_to(ROOT).as_posix()]=digest(p)
    for folder,names in [('src',NUMERIC),('docs',PROTOCOLS)]:
        (fresh/folder).mkdir()
        for name in names:
            p=ROOT/folder/name;shutil.copy2(p,fresh/folder/name);inputs[p.relative_to(ROOT).as_posix()]=digest(p)
    commands=[['run_experiment.py'],['run_shared.py','--group','shared'],['run_shared.py','--group','rolling'],['analyze_results.py']]
    with (fresh/'reproduction.log').open('w',encoding='utf-8') as log:
        for command in commands:
            print('Fresh candidate retraining:',command,flush=True)
            subprocess.run([sys.executable,str(fresh/'src'/command[0])]+command[1:],cwd=fresh,stdout=log,stderr=subprocess.STDOUT,check=True);log.flush()
    checked=[]
    for p in sorted((fresh/'results').glob('*')):
        original=ROOT/'results'/p.name
        if p.suffix=='.csv':
            a=pd.read_csv(original,float_precision='round_trip');b=pd.read_csv(p,float_precision='round_trip');pd.testing.assert_frame_equal(a,b,check_exact=False,rtol=1e-10,atol=1e-12)
        elif p.suffix=='.json':compare_json(json.loads(original.read_text(encoding='utf-8')),json.loads(p.read_text(encoding='utf-8')))
        else:continue
        checked.append({'path':'results/'+p.name,'original_sha256':digest(original),'fresh_sha256':digest(p)})
    assert len(list((fresh/'models').glob('*.joblib')))==54
    for path,h in inputs.items():assert digest(ROOT/path)==h,path
    write_json(ROOT/'results/reproduction.json',{'status':'passed','scope':'New candidates retrained in an empty result/model directory from frozen prepared cohort, observed-transition inputs and 18 frozen previous-stage baseline models. Same host/environment; original raw CSV cleaning is not rerun here.','fresh_workspace':str(fresh),'inputs':inputs,'checked_outputs':checked,'new_model_files_retrained':54,'frozen_baseline_model_files':18,'python':sys.version,'platform':platform.platform()})
    print('Fresh reproduction passed:',len(checked),'outputs and 54 new models.',flush=True)
if __name__=='__main__':main()
