from pathlib import Path
from datetime import datetime,UTC,timedelta
import os,sys,json,hashlib,tarfile
FROZEN=Path('/Users/cortex/Crypto2Data/reports/phase7-constrained-20261117/crypto2-source-133f49ef5b2c')
sys.path.insert(0,str(FROZEN/'src'))
FULL=Path('/Users/cortex/Crypto2Data/lightning-full/crypto2-persistent')
TRANSFER=Path('/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107/crypto2-persistent')
os.environ['PHASE7_DATA_ROOT']=str(FULL/'data');os.environ['PHASE7_LEGACY_DATA_ROOT']='/home/nssharath123/crypto2.0/data'
from crypto_ai.phase7.registry import read_registry
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.acquisition import _silver_segment_manifests,validated_candle_manifest_range,_DATE_PARTITION
RUN='phase7a-core20-primary-93f987736b1a79d26b773957'
artifact=TRANSFER/'phase7/artifacts'/RUN
data=json.loads((artifact/'data/data_manifest.json').read_text());registry=read_registry(artifact/'registry/symbol_registry.json').by_symbol()
config=load_phase7_config(FROZEN/'configs/phase7/research_core20_primary_v1.toml')
protocol=json.loads(Path('/Users/cortex/Projects/crypto2.0/docs/research/PHASE7A_G0_A6_60M_RAW_4FOLD_PILOT_PROTOCOL_20261118.json').read_text())
# 2026-11-21: remaining canonical folds. Fold k ends training 3k months after Fold 0; checked against the 4 protocol folds.
def _months(d,n):
 m=d.month-1+n;return d.replace(year=d.year+m//12,month=m%12+1)
_f0=datetime.fromisoformat(protocol['folds'][0]['train_end'])
for _f in protocol['folds']:assert datetime.fromisoformat(_f['train_end'])==_months(_f0,3*_f['index']),_f
sys.path.insert(0,'/Users/cortex/.crypto2-transfer/operator-opsfix8/crypto2-operator-kit/scripts/closure')
from runpod_phase7_ops import CANONICAL_FOLDS
WANTED=(1,2,3,4,6,7,8,9,11,12,13,14)
protocol={'folds':[{'index':k,'fold_id':CANONICAL_FOLDS[k],'train_end':_months(_f0,3*k).isoformat()} for k in WANTED]}
supplement_a=json.loads(Path('/Users/cortex/Crypto2Data/reports/phase7-constrained-20261117/pilot-daily-supplement-20261118/manifest.json').read_text())
original=json.loads(Path('/Users/cortex/Projects/crypto2.0/docs/runpod/transfer.expected.json').read_text());covered={r['path'] for r in original['records']}|{r['path'] for r in supplement_a['files']}
records={};windows=[];missing=[];mismatch=[];manifests={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for fold in protocol['folds']:
 end=datetime.fromisoformat(fold['train_end']);start=end-timedelta(days=config.universe.selection_lookback_days);symbols=[]
 for symbol,ref in sorted(data['candle_silver_manifests']['1d'].items()):
  rec=registry[symbol]
  if not(rec.causal_available_from<end and (rec.available_until is None or rec.available_until>start)):continue
  manifest=TRANSFER/'data/phase7/silver/binance/manifests'/Path(ref).name
  payload=json.loads(manifest.read_text());accepted_start,accepted_end=validated_candle_manifest_range(manifest)
  lower=max(start,accepted_start);upper=min(end,accepted_end)
  assert lower<upper,(symbol,fold['index'])
  symbols.append(symbol);manifests[str(manifest.relative_to(TRANSFER))]=sha(manifest)
  for child in _silver_segment_manifests(manifest,payload):
   child_payload=json.loads(child.read_text())
   for output in child_payload.get('output_files',[]):
    date=_DATE_PARTITION.search(output['file'].replace('\\','/'))
    if date:
     day=datetime.fromisoformat(date.group(1)).date()
     if day<lower.date() or day>upper.date():continue
    source=FULL/'data/phase7/silver/binance'/output['file']
    path='crypto2-persistent/'+str(source.relative_to(FULL))
    if path in covered:continue
    if not source.is_file():missing.append({'path':path,'fold':fold['index']});continue
    digest=sha(source)
    if digest!=output['sha256']:mismatch.append({'path':path,'expected':output['sha256'],'actual':digest});continue
    if path not in records:records[path]={'path':path,'sha256':digest,'bytes':source.stat().st_size,'folds':[]}
    if fold['index'] not in records[path]['folds']:records[path]['folds'].append(fold['index'])
 windows.append({'fold_index':fold['index'],'fold_id':fold['fold_id'],'start':start.isoformat(),'exclusive_end':end.isoformat(),'loader_end_day_partition_required_for_hash_check':True,'symbols':symbols})
out=Path('/Users/cortex/Crypto2Data/reports/phase7-constrained-20261117/pilot-daily-supplement-20261121');out.mkdir(exist_ok=True)
manifest={'schema':'phase7a_manifest_bound_daily_supplement_v1','source_commit':'133f49ef5b2c5b31d4d6d5ffef3c5c72db5f6e70','schema_note':'supplement B, built 2026-11-21','purpose':'Existing canonical 1d Silver files omitted from Fold-0-only transfer, required for frozen descriptor windows of folds 1-4,6-9,11-14 (supplement B; excludes supplement A files)','source_data_changed':False,'gold_sidecar_and_canonical_manifests_changed':False,'july_2026_or_august_2026_accessed':False,'windows':windows,'files':[records[k] for k in sorted(records)],'source_manifest_sha256':manifests,'missing':missing,'mismatch':mismatch,'total_bytes':sum(r['bytes'] for r in records.values())}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert not missing and not mismatch, 'AUTHORITATIVE_SOURCE_NOT_COMPLETE_OR_HASH_MISMATCH'
archive=out/'daily-supplement.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
 for r in manifest['files']:tar.add(FULL/Path(r['path']).relative_to('crypto2-persistent'),arcname=r['path'],recursive=False)
summary={'status':'ALL_REQUIRED_LOCAL_FILES_HASH_VERIFIED','files':len(records),'uncompressed_bytes':manifest['total_bytes'],'archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'manifest':str(out/'manifest.json'),'manifest_sha256':sha(out/'manifest.json'),'windows':windows}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
