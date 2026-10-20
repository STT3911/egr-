import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.bankrot_archive import (
    BankrotArchiveWriter, iter_bankrot_archive, compress_completed_archive,
    maintain_bankrot_archives,
)


def record(case_id=1):
    return {'case_id':case_id,'list_data':{'id':case_id},'detail_data':{},'judgements_group':[],
            'related_data':{'properties':{'payload':[{'id':case_id}]},
                            'manager_debtors':{'payload':[{'name':'Должник '+str(n)} for n in range(100)]},
                            'manager_full_info':{'payload':{'name':'Управляющий'}}}}


def export_path(tmp_path, run=1, suffix='.jsonl.tmp'):
    return tmp_path / f'bankrot_cases_{run}_20260101_010000{suffix}'


def test_manager_data_is_stored_once_and_restored_losslessly(tmp_path):
    path=export_path(tmp_path)
    rows=[record(1),record(2)]
    original=copy.deepcopy(rows)
    with BankrotArchiveWriter(path,'w') as writer:
        for row in rows:writer.write_record(row)
        writer.flush()
    assert rows==original
    on_disk=[json.loads(line) for line in path.read_text().splitlines()]
    assert on_disk[0]['manager_data_ref']==on_disk[1]['manager_data_ref']
    assert 'manager_debtors' not in on_disk[0]['related_data']
    assert len(list(tmp_path.glob('*.managers/*.json.gz')))==1
    assert list(iter_bankrot_archive(path))==rows


def test_resumed_file_can_mix_legacy_and_compact_records(tmp_path):
    path=export_path(tmp_path)
    old=record(1)
    path.write_text(json.dumps(old)+'\n')
    before=path.read_bytes()
    with BankrotArchiveWriter(path,'a') as writer:writer.write_record(record(2))
    assert path.read_bytes().startswith(before)
    with BankrotArchiveWriter(path,'a') as writer:writer.write_record(record(3))
    assert list(iter_bankrot_archive(path))==[old,record(2),record(3)]
    assert len(list(tmp_path.glob('*.managers/*.json.gz')))==1


def test_compression_is_byte_exact_and_preserves_manager_references(tmp_path):
    partial=export_path(tmp_path)
    with BankrotArchiveWriter(partial,'w') as writer:writer.write_record(record())
    path=export_path(tmp_path,suffix='.jsonl')
    partial.rename(path)
    before=path.read_bytes()
    calls=[]
    target=compress_completed_archive(path,before_remove=lambda p,meta:calls.append((p,meta)))
    assert not path.exists()
    assert gzip.decompress(target.read_bytes())==before
    assert calls[0][1]['source_sha256']==hashlib.sha256(before).hexdigest()
    assert list(iter_bankrot_archive(target))==[record()]


def test_metadata_commit_failure_keeps_original_and_retry_is_safe(tmp_path):
    path=export_path(tmp_path,suffix='.jsonl')
    path.write_text(json.dumps(record())+'\n')
    before=path.read_bytes()
    def fail(*_):raise RuntimeError('DB unavailable')
    with pytest.raises(RuntimeError):compress_completed_archive(path,before_remove=fail)
    assert path.read_bytes()==before
    target=compress_completed_archive(path)
    assert gzip.decompress(target.read_bytes())==before


def test_conflicting_gzip_preserves_both_files(tmp_path):
    path=export_path(tmp_path,suffix='.jsonl')
    path.write_text(json.dumps(record())+'\n')
    target=path.with_name(path.name+'.gz')
    target.write_bytes(gzip.compress(b'different'))
    with pytest.raises(ValueError,match='Conflicting'):compress_completed_archive(path)
    assert path.exists() and gzip.decompress(target.read_bytes())==b'different'


@pytest.mark.parametrize('suffix',['.jsonl.tmp','.log'])
def test_never_compresses_active_or_unrecognized_files(tmp_path,suffix):
    path=export_path(tmp_path,suffix=suffix)
    path.write_text('preserve')
    with pytest.raises(ValueError):compress_completed_archive(path)
    assert path.read_text()=='preserve'


def test_corrupt_manager_blob_is_not_silently_reused(tmp_path):
    path=export_path(tmp_path)
    with BankrotArchiveWriter(path,'w') as writer:writer.write_record(record())
    blob=next(tmp_path.glob('*.managers/*.json.gz'))
    blob.write_bytes(gzip.compress(b'wrong'))
    with pytest.raises(ValueError,match='Corrupt'):
        list(iter_bankrot_archive(path))
    with pytest.raises(ValueError,match='Corrupt'):
        with BankrotArchiveWriter(path,'a') as writer:writer.write_record(record(2))


def test_reference_traversal_is_rejected(tmp_path):
    path=export_path(tmp_path)
    path.write_text(json.dumps({'archive_version':2,'manager_data_ref':'../secret'})+'\n')
    with pytest.raises(ValueError):list(iter_bankrot_archive(path))


def fake_db(rows):
    db=MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value=rows
    db.get_bind.return_value.begin.return_value.__enter__.return_value.execute.return_value.scalar.return_value=True
    return db


def run_row(path,*,status='done'):
    return SimpleNamespace(id=int(path.name.split('_')[2]),status=status,failed_cases=0,
                           finished_at='2026-01-01' if status=='done' else None,
                           output_file=str(path),stats_json={})


def test_default_keeps_every_snapshot_and_does_not_touch_running_tmp(tmp_path):
    first=export_path(tmp_path,1,'.jsonl');second=export_path(tmp_path,2,'.jsonl')
    active=export_path(tmp_path,3)
    for path in (first,second,active):path.write_text(json.dumps(record())+'\n')
    before=active.read_bytes()
    rows=[run_row(second),run_row(first),run_row(active,status='running')]
    result=maintain_bankrot_archives(fake_db(rows),tmp_path)
    assert result['compressed']==2 and result['pruned']==0
    assert all(Path(r.output_file).exists() for r in rows)
    assert active.read_bytes()==before
    assert all(list(iter_bankrot_archive(Path(r.output_file)))==[record()] for r in rows[:2])


def test_database_metadata_is_committed_before_original_removal(tmp_path):
    path=export_path(tmp_path,1,'.jsonl');path.write_text(json.dumps(record())+'\n')
    row=run_row(path);db=fake_db([row])
    def commit():
        assert path.exists()
        assert row.output_file.endswith('.jsonl.gz')
    db.commit.side_effect=commit
    maintain_bankrot_archives(db,tmp_path)
    assert not path.exists()


def test_maintenance_lock_blocks_concurrent_archivers(tmp_path):
    path=export_path(tmp_path,1,'.jsonl');path.write_text('preserve')
    db=fake_db([run_row(path)])
    db.get_bind.return_value.begin.return_value.__enter__.return_value.execute.return_value.scalar.return_value=False
    assert maintain_bankrot_archives(db,tmp_path)['status']=='already_running'
    assert path.read_text()=='preserve'


def test_optional_retention_never_removes_database_business_rows(tmp_path):
    rows=[]
    for run in (3,2,1):
        path=export_path(tmp_path,run,'.jsonl')
        path.write_text(json.dumps(record())+'\n');rows.append(run_row(path))
    db=fake_db(rows)
    result=maintain_bankrot_archives(db,tmp_path,keep=2)
    assert result['pruned']==1 and rows[2].output_file is None
    assert all(Path(r.output_file).exists() for r in rows[:2])
    db.delete.assert_not_called()


@pytest.mark.parametrize('archive_error',[False,True,'soft'])
def test_sync_saves_full_manager_payloads_to_db_before_compacting_file(tmp_path,monkeypatch,archive_error):
    from datetime import datetime
    import app.services.bankrot_sync as sync
    run=SimpleNamespace(id=1,status='partial',started_at=datetime(2026,1,1,1),
                        finished_at=None,error=None,stats_json={},last_page=0,total_cases=0,
                        failed_cases=0,output_file=None)
    db=MagicMock()
    query=db.query.return_value
    query.filter.return_value.order_by.return_value.first.return_value=run
    query.filter_by.return_value.update.side_effect=lambda values:[setattr(run,k,v) for k,v in values.items()]
    captured=[]
    monkeypatch.setattr(sync,'_upsert_cases',lambda db,rows:None)
    monkeypatch.setattr(sync,'_upsert_case_datasets',lambda db,rows:captured.extend(copy.deepcopy(rows)))
    manager={'endpoint':'/manager/debtors/?id=77','http_method':'GET','payload':[{'id':10},{'id':11}],'fetch_error':None}
    client=MagicMock()
    client.__enter__.return_value=client
    client.get_case_detail.side_effect=lambda case_id:{'manager':{'id':77},'organization':{'unp':193879557}}
    client.get_case_related_data.return_value={}
    client.get_manager_related_data.return_value={'manager_debtors':manager}
    client.get_case_judgements_group.return_value={}
    def cases(**kwargs):
        yield {'id':1}
        yield {'id':2}
        kwargs['page_complete'](1,2,2)
    client.iter_all_cases.side_effect=cases
    monkeypatch.setattr(sync,'BankrotClient',lambda **kwargs:client)
    def maintain(*args,**kwargs):
        assert run.status=='done'
        if archive_error=='soft':
            from billiard.exceptions import SoftTimeLimitExceeded
            raise SoftTimeLimitExceeded()
        if archive_error:raise OSError('disk full')
        return {'compressed':0,'pruned':0,'bytes_released':0}
    monkeypatch.setattr(sync,'maintain_bankrot_archives',maintain)
    result=sync.sync_bankrot_cases(db,output_dir=str(tmp_path),delay=0,detail_delay=0,max_runtime=0)
    assert result['complete'] and run.status=='done' and run.last_page==1
    assert [r['payload'] for r in captured]==[manager['payload'],manager['payload']]
    path=export_path(tmp_path,1,'.jsonl')
    disk=[json.loads(line) for line in path.read_text().splitlines()]
    assert all('manager_debtors' not in row['related_data'] for row in disk)
    assert all(row['related_data']['manager_debtors']==manager for row in iter_bankrot_archive(path))


def test_retention_keeps_snapshots_with_failed_child_datasets(tmp_path):
    rows=[]
    for run in (3,2,1):
        path=export_path(tmp_path,run,'.jsonl')
        path.write_text(json.dumps(record())+'\n');rows.append(run_row(path))
    rows[2].stats_json={'datasets_failed':1}
    result=maintain_bankrot_archives(fake_db(rows),tmp_path,keep=1)
    assert result['pruned']==1
    assert rows[2].output_file is not None and Path(rows[2].output_file).exists()
