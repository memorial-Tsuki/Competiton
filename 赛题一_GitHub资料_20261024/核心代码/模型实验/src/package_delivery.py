"""Package verified research outputs and smoke-test the extracted delivery."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, uuid, zipfile
from study_common import ROOT, digest, read_json, write_json
from verify import numerical_fingerprint


def main():
    verified = read_json(ROOT / 'results/verification.json')
    assert verified['status'] == 'passed'
    assert numerical_fingerprint() == verified['fingerprint'], 'Numerical evidence is stale'
    visual = read_json(ROOT / 'results/visual_review.json')
    assert visual['status'] == 'passed' and visual['reviewed_pages'] == 8
    assert digest(ROOT / visual['pdf']) == visual['pdf_sha256'], 'PDF changed after review'
    assert len(visual['rendered_pages']) == 8
    for name, expected in visual['rendered_pages'].items():
        assert digest(ROOT / name) == expected, name
    fluctuation = read_json(ROOT / 'results/figures/fluctuation_verification.json')
    assert fluctuation['status'] == 'passed'
    for name, expected in {**fluctuation['sources'], **fluctuation['plot_data']}.items():
        assert digest(ROOT / name) == expected, name

    excluded = {'__pycache__', '.pytest_cache', 'tmp'}
    files = sorted(p for p in ROOT.rglob('*') if p.is_file()
                   and not (set(p.relative_to(ROOT).parts) & excluded)
                   and p.name not in {'FILE_MANIFEST.json', 'delivery_summary.json'})
    records = {p.relative_to(ROOT).as_posix(): digest(p) for p in files}
    manifest = ROOT / 'FILE_MANIFEST.json'
    write_json(manifest, {'algorithm': 'sha256', 'files': records,
                         'scope': 'All delivery files except this self-referencing manifest and post-package delivery summary.'})
    package = ROOT.parent / '赛题一_逾期增强实验成果.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in files + [manifest]:
            z.write(path, (Path(ROOT.name) / path.relative_to(ROOT)).as_posix())

    smoke = ROOT.parent / 'tmp' / ('delinquency-package-smoke-' + uuid.uuid4().hex[:12])
    smoke.mkdir(parents=True)
    with zipfile.ZipFile(package) as z:
        assert len(z.namelist()) == len(set(z.namelist())) == len(records) + 1
        assert z.testzip() is None
        packaged = json.loads(z.read(ROOT.name + '/FILE_MANIFEST.json'))
        assert packaged['files'] == records
        for info in z.infolist():
            target = (smoke / info.filename).resolve()
            assert target.is_relative_to(smoke.resolve()), info.filename
            with z.open(info) as f:
                actual = hashlib.file_digest(f, 'sha256').hexdigest()
            expected = digest(manifest) if info.filename.endswith('/FILE_MANIFEST.json') else records[info.filename.removeprefix(ROOT.name + '/')]
            assert actual == expected, info.filename
        z.extractall(smoke)

    extracted = smoke / ROOT.name
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8')
    examples = []
    for source in sorted((extracted / 'examples').glob('*.json')):
        if source.stem.endswith('_output'):
            continue
        output = extracted / 'tmp/smoke' / (source.stem + '.json')
        run = subprocess.run([sys.executable, str(extracted / 'src/predict.py'), str(source),
                              '--output', str(output)], cwd=extracted, env=env,
                             capture_output=True, text=True, encoding='utf-8', timeout=120)
        assert run.returncode == 0, run.stderr
        actual = read_json(output)
        assert actual == read_json(source.with_name(source.stem + '_output.json')), source.name
        assert json.loads(run.stdout) == actual
        examples.append(source.name)
    assert len(examples) == 5
    summary = {'status': 'passed', 'package': str(package), 'bytes': package.stat().st_size,
               'sha256': digest(package), 'files_including_manifest': len(records) + 1,
               'numerical_fingerprint': verified['fingerprint'],
               'pdf_sha256': visual['pdf_sha256'],
               'extracted_cli_examples_passed': examples,
               'smoke_workspace': str(smoke)}
    write_json(ROOT / 'delivery_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
