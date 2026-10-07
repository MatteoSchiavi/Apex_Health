"""Measured runtime telemetry; no Docker socket, health records or shell commands."""
import asyncio
import json
import os
import shutil
from pathlib import Path
from sqlalchemy import text

LOG_KEY='apex:operational:logs'

def integer_file(path):
    try: return int(Path(path).read_text().strip())
    except (OSError,ValueError): return None

def cpu_ticks():
    try:
        values=[int(v) for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
        return sum(values), values[3]+values[4]
    except (OSError,ValueError,IndexError): return None

async def system_metrics(session):
    container=Path('/.dockerenv').exists() or Path('/run/.containerenv').exists()
    memory={}
    try:
        memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    except (OSError,ValueError): pass
    total=memory.get('MemTotal'); used=total-memory.get('MemAvailable',0) if total else None
    scope='host kernel'
    limit=integer_file('/sys/fs/cgroup/memory.max')
    current=integer_file('/sys/fs/cgroup/memory.current')
    if limit is None:
        limit=integer_file('/sys/fs/cgroup/memory/memory.limit_in_bytes')
        current=integer_file('/sys/fs/cgroup/memory/memory.usage_in_bytes')
    if limit and total and limit<total:
        total=limit;used=current;scope='container cgroup'
    disk=shutil.disk_usage('/')
    try: load=os.getloadavg()[0]
    except OSError: load=None
    first=cpu_ticks()
    await asyncio.sleep(0.1)
    second=cpu_ticks()
    percent=None
    if first and second and second[0]>first[0]:
        percent=round(100*(1-(second[1]-first[1])/(second[0]-first[0])),2)
    result={'scope':'container' if container else 'host','cpu':{'load_1m':load,'logical_cpus':os.cpu_count(),'utilization_percent':percent,'sample_seconds':0.1,'scope':'host kernel CPU (/proc/stat; container limit not inferred)'},'memory':{'scope':scope,'total_bytes':total,'used_bytes':used},'disk':{'scope':'container filesystem' if container else 'root filesystem','total_bytes':disk.total,'used_bytes':disk.used}}
    try:
        row=(await session.execute(text("SELECT count(*) AS connections, count(*) FILTER (WHERE state='active') AS active_connections, current_setting('max_connections')::int AS max_connections FROM pg_stat_activity"))).mappings().one()
        result['postgres']=dict(row)
    except Exception:
        await session.rollback();result['postgres']={'available':False}
    from app.tasks.celery_app import celery_app
    def inspect():
        return celery_app.control.inspect(timeout=1.0).ping() or {}
    try:
        workers=await asyncio.wait_for(asyncio.to_thread(inspect),timeout=2.0)
        result['celery']={'available':bool(workers),'workers':[{'name':name[:100],'status':'online'} for name in list(workers)[:50]]}
    except Exception: result['celery']={'available':False,'workers':[]}
    return result

async def read_logs(redis,limit,level,source):
    rows=await redis.lrange(LOG_KEY,0,999)
    items=[]
    for raw in rows:
        try: row=json.loads(raw)
        except (ValueError,TypeError): continue
        if level and row.get('level')!=level: continue
        if source and row.get('source')!=source: continue
        items.append(row)
        if len(items)>=limit: break
    return items
