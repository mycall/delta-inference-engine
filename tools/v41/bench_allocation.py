"""Opt-in Windows DS41 allocation comparison; starts fresh engines sequentially.

Uses the DeepSeek API shim, fixed coding/JSON checks and a long coding context.
No model-produced code runs on the host. Stops an arm on engine death/replacement
instead of sending another request that could silently restart it. Reports stay
under logs. No installed configuration or executable is replaced.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid

ROOT = Path(__file__).resolve().parents[2]


def system_memory():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length',ctypes.c_uint32),('load',ctypes.c_uint32)] + [
            (name,ctypes.c_uint64) for name in ('total_physical','available_physical',
                'total_pagefile','available_pagefile','total_virtual','available_virtual','extended_virtual')]
    status = MemoryStatus(); status.length = ctypes.sizeof(status)
    function = ctypes.windll.kernel32.GlobalMemoryStatusEx
    function.argtypes = [ctypes.POINTER(MemoryStatus)]; function.restype = ctypes.c_int
    if not function(ctypes.byref(status)): raise ctypes.WinError()
    result = {name:getattr(status,name) for name in ('load','total_physical','available_physical','total_pagefile','available_pagefile')}
    # MEMORYSTATUSEX page-file fields can be limited to the calling process.
    # Read true system commit separately; neither is page-file disk usage.
    class PerformanceInfo(ctypes.Structure):
        _fields_ = [('length',ctypes.c_uint32)] + [(name,ctypes.c_size_t) for name in (
            'commit_total','commit_limit','commit_peak','physical_total','physical_available',
            'system_cache','kernel_total','kernel_paged','kernel_nonpaged','page_size')] + [
            (name,ctypes.c_uint32) for name in ('handles','processes','threads')]
    performance = PerformanceInfo(); performance.length = ctypes.sizeof(performance)
    query = ctypes.windll.psapi.GetPerformanceInfo
    query.argtypes = [ctypes.POINTER(PerformanceInfo),ctypes.c_uint32]; query.restype = ctypes.c_int
    if not query(ctypes.byref(performance),performance.length): raise ctypes.WinError()
    result.update(system_commit_used=performance.commit_total*performance.page_size,
        system_commit_limit=performance.commit_limit*performance.page_size,
        system_commit_available=(performance.commit_limit-performance.commit_total)*performance.page_size)
    return result


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def debugger_present(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CheckRemoteDebuggerPresent.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x400,False,pid)
    if not handle: raise ctypes.WinError()
    try:
        present = ctypes.c_int()
        if not kernel.CheckRemoteDebuggerPresent(handle,ctypes.byref(present)): raise ctypes.WinError()
        return bool(present.value)
    finally: kernel.CloseHandle(handle)


def api(base, path, body=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def existing_status(base):
    try:
        return api(base,'/v1/status')
    except urllib.error.URLError as error:
        # A reboot can leave the ordinary API intentionally stopped. Only an
        # actual refused connection counts as absent; timeouts/errors remain
        # failures. Engine inventory independently prevents a second model.
        reason = error.reason
        if isinstance(reason,ConnectionRefusedError) or getattr(reason,'winerror',None)==10061 or getattr(reason,'errno',None) in (10061,111):
            return dict(available=False,loaded=False,activity=dict(in_flight=0))
        raise


def engines(owner=None):
    command = ("Get-CimInstance Win32_Process -Filter \"Name LIKE 'ds41_generate%.exe' OR Name = 'python.exe'\" "
        "| Select-Object ProcessId,ParentProcessId,Name,CreationDate,ExecutablePath | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
        capture_output=True,check=True,timeout=15)
    value = json.loads(result.stdout) if result.stdout.strip() else None
    rows = value if isinstance(value,list) else [value] if value else []
    if owner is not None:
        # Windows venv python.exe is a launcher: the actual interpreter is its
        # child. Accept only descendants of the still-owned Popen process.
        descendants = {owner}
        while True:
            children = {row['ProcessId'] for row in rows if row['ParentProcessId'] in descendants}
            if children <= descendants: break
            descendants.update(children)
        rows = [row for row in rows if row['ParentProcessId'] in descendants]
    return sorted((row for row in rows if row['Name'].lower().startswith('ds41_generate')),key=lambda row:row['ProcessId'])


def environment(launcher, config, paths_config=None):
    # Source-derived test environment, not a claim to capture the live process.
    # Only unconditional literal engine settings; never evaluate batch commands.
    values = {}
    if paths_config is not None:
        for line in paths_config.read_text(encoding='utf-8-sig').splitlines():
            match = re.fullmatch(r'if not defined ([A-Z0-9_]+) set "\1=([^"%]*)"',line,re.I)
            if match and match[1].startswith(('STRATA_','MIMO_')): values[match[1]] = match[2]
    for line in launcher.read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'set ((?:STRATA_|DS41_PRIORITY|GGML_)[A-Z0-9_]*)=(.*)', line, re.I)
        if match and '%' not in match[2]: values[match[1]] = match[2]
    model = Path(config['args'][config['args'].index('-m')+1])
    drafter = next((parent / 'V41-1017-MTP-iq2xxs-imx.gguf' for parent in model.parents
        if (parent / 'V41-1017-MTP-iq2xxs-imx.gguf').is_file()), None)
    if drafter is None: raise RuntimeError('Expected the currently selected imatrix drafter')
    values.update(STRATA_SERVE_DSPARK=str(drafter),CUDA_DEVICE_ORDER='PCI_BUS_ID',CUDA_VISIBLE_DEVICES='0',
        STRATA_START_RETRIES='0',HF_HUB_DISABLE_TELEMETRY='1',PYTHONUNBUFFERED='1')
    values.update(config.get('env', {}))
    # Fixed equally for both arms; do not introduce eager CUDA loading here.
    result = {key:value for key,value in os.environ.items()
        if not key.startswith(('STRATA_', 'DS41_', 'GGML_', 'CUDA_', 'MIMO_'))}
    result.update(values)
    return result, values


def cases(functions=300):
    code = '\n'.join(f'def normalize_{i}(values):\n    return sorted(set(x for x in values if x is not None))\n'
        for i in range(functions))
    sort = ('Sort these records by score ascending, preserving input order for ties: '
        '[{"id":"a","score":2},{"id":"b","score":1},{"id":"c","score":1},{"id":"d","score":3}]. '
        'Return ONLY a JSON array of their ids, no markdown.')
    loop = ('Python code `out=[]; i=0` then `while i <= 3: out.append(i); i+=1` runs. '
        'The intended bound is i < 3. Return ONLY a JSON object with keys actual and fixed, '
        'each holding the corresponding output array. No markdown.')
    return [
        ('warmup', 'What is 2+2? Return only a JSON number.', 4, 24),
        ('stable_sort', sort, ['b','c','a','d'], 96),
        ('long_alpha', 'Coding snapshot ALPHA. Read this module as context:\n'+code+'\n'+sort, ['b','c','a','d'], 96),
        ('loop_bounds', loop, {'actual':[0,1,2,3],'fixed':[0,1,2]}, 96),
        ('long_bravo', 'Coding snapshot BRAVO. Read this module as context:\n'+code+'\n'+loop,
            {'actual':[0,1,2,3],'fixed':[0,1,2]}, 96),
        ('long_alpha_repeat', 'Coding snapshot ALPHA. Read this module as context:\n'+code+'\n'+sort,
            ['b','c','a','d'], 96),
    ]


def drafter_cases(functions=300):
    """Longer, exactly checked coding outputs; no generated code is executed."""
    records = [{'id':i,'score':(i*17)%11} for i in range(64)]
    expected = [record['id'] for record in sorted(records,key=lambda record:record['score'])]
    sort = ('Python sorted(records, key=lambda r: r["score"]) is stable. '
        'Return ONLY a JSON array containing every id in that sorted order. Records: '
        +json.dumps(records,separators=(',',':')))
    code = '\n'.join(f'def normalize_{i}(values):\n    return sorted(set(x for x in values if x is not None))\n'
        for i in range(functions))
    return [
        ('warmup_object','What is 2+2? Return ONLY the JSON object {"value":4}.',{'value':4},32),
        ('sort_64',sort,expected,1024),
        ('loop_64','Python code `out=[]; i=0` then `while i <= 63: out.append(i); i+=1` runs. '
            'The intended bound is i < 63. Return ONLY a JSON object with keys actual and fixed, '
            'each holding the complete corresponding output array. No markdown.',
            {'actual':list(range(64)),'fixed':list(range(63))},1024),
        ('long_sort_64','Read this coding snapshot as context:\n'+code+'\n'+sort,expected,1024),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--launcher',type=Path,required=True)
    parser.add_argument('--paths-config',type=Path,default=ROOT/'ds41-paths.bat')
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--candidate-config',type=Path,
        help='Compare a separate config, optionally using the same executable; recorded per arm')
    parser.add_argument('--workload',choices=['allocation','draft-coding'],default='allocation')
    parser.add_argument('--rounds',type=int,default=1,choices=range(1,5))
    parser.add_argument('--functions',type=int,default=300,choices=[150,300])
    parser.add_argument('--arms',nargs='+',choices=['original','candidate'],default=['original','candidate'])
    parser.add_argument('--procdump',type=Path,help='Explicit local diagnostic monitor, not installed as a system debugger')
    parser.add_argument('--port',type=int,default=8097)
    parser.add_argument('--existing-url',default='http://127.0.0.1:8080')
    parser.add_argument('--unload-existing',action='store_true')
    args = parser.parse_args()
    if os.name!='nt': raise RuntimeError('This qualification uses native Windows process and memory observations')
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    original = Path(config['exe']).resolve(strict=True)
    if not args.candidate and not args.candidate_config:
        parser.error('--candidate or --candidate-config is required')
    candidate_config = json.loads(args.candidate_config.read_text(encoding='utf-8-sig')) if args.candidate_config else config
    candidate = (args.candidate or Path(candidate_config['exe'])).resolve(strict=True)
    if candidate == original and candidate_config == config:
        raise ValueError('Distinct candidate executable or configuration required')
    if not all(path.name.lower().startswith('ds41_generate') for path in (original,candidate)):
        raise ValueError('Expected ds41_generate-named engine binaries for process inventory')
    if len(set(args.arms))!=len(args.arms): raise ValueError('Duplicate arms')
    if args.procdump:
        args.procdump = args.procdump.resolve(strict=True)
        # Pin the already Authenticode-verified Microsoft ARM64 ProcDump 12.02.
        if digest(args.procdump)!='3448555503526053bd819c760ad7b40368e130db8348f535f5212e12e9ab2ea5':
            raise ValueError('Diagnostic monitor differs from the verified tool')
    # Verify a separate loopback test port before unloading anything.
    with socket.socket() as available: available.bind(('127.0.0.1',args.port))
    output = ROOT / 'logs' / ('allocation-ab-'+uuid.uuid4().hex)
    output.mkdir()
    print(output,flush=True)
    result = dict(schema=1,passed=False,harness_sha256=digest(__file__),config_sha256=digest(args.config),launcher_sha256=digest(args.launcher),
        paths_sha256=digest(args.paths_config),
        candidate_config_sha256=digest(args.candidate_config) if args.candidate_config else None,
        candidate_config=str(args.candidate_config.resolve()) if args.candidate_config else None,
        workload=args.workload,
        source_environment='literal path-file engine defaults then unconditional launcher settings, config env and explicit imatrix drafter',
        config=args.config.resolve().as_posix(),arms=[],existing_before=existing_status(args.existing_url))
    save = lambda: (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    env, values = environment(args.launcher, config,args.paths_config)
    (output/'environment.json').write_text(json.dumps(values,indent=2),encoding='utf-8')
    result['environment_sha256'] = digest(output/'environment.json')
    fixture = drafter_cases(args.functions) if args.workload=='draft-coding' else cases(args.functions)
    result['functions'] = args.functions
    result['procdump_sha256'] = digest(args.procdump) if args.procdump else None
    (output/'harness-snapshot.py').write_bytes(Path(__file__).read_bytes())
    (output/'cases.json').write_text(json.dumps(fixture,indent=2),encoding='utf-8')
    result['cases_sha256'] = digest(output/'cases.json')
    save()
    if result['existing_before']['activity']['in_flight']: raise RuntimeError('Existing API is busy')
    if result['existing_before']['loaded']:
        if not args.unload_existing: raise RuntimeError('Explicit --unload-existing required')
        result['existing_unload'] = api(args.existing_url,'/unload',{},timeout=60)
    if existing_status(args.existing_url)['loaded'] or engines():
        raise RuntimeError('Another engine remains; refusing concurrent full model allocation')
    base = f'http://127.0.0.1:{args.port}'
    for round_index in range(args.rounds):
        arms = [(name,original if name=='original' else candidate) for name in args.arms]
        if round_index % 2: arms.reverse()
        for label, exe in arms:
            if engines() or existing_status(args.existing_url)['loaded']:
                raise RuntimeError('Unexpected engine before arm; no process was killed')
            trial = output / f'{round_index}-{label}'; trial.mkdir()
            source_config = config if label=='original' else candidate_config
            cfg = dict(source_config,exe=str(exe),port=args.port,log=str(trial/'engine.log'))
            arm_env, arm_values = environment(args.launcher,cfg,args.paths_config)
            (trial/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
            (trial/'environment.json').write_text(json.dumps(arm_values,indent=2),encoding='utf-8')
            arm = dict(round=round_index,arm=label,exe_sha256=digest(exe),
                config_sha256=digest(trial/'config.json'),environment_sha256=digest(trial/'environment.json'),
                requests=[],passed=False,cleanup=False)
            result['arms'].append(arm); save()
            with (trial/'server.log').open('wb') as log:
                process = subprocess.Popen([sys.executable,str(ROOT/'tools/v41/serve/serve_ds41.py'),
                    '--engine','strata','--config',str(trial/'config.json'),'--host','127.0.0.1','--port',str(args.port)],
                    cwd=ROOT,env=arm_env,stdout=log,stderr=subprocess.STDOUT)
            arm['server_pid'] = process.pid
            monitor = monitor_log = None
            try:
                deadline = time.monotonic()+180
                while True:
                    if process.poll() is not None: raise RuntimeError('Test API exited before ready')
                    try:
                        if api(base,'/v1/status',timeout=2)['loaded']: break
                    except (OSError,ValueError): pass
                    if time.monotonic()>=deadline: raise TimeoutError('Test API readiness')
                    time.sleep(1)
                identity = engines()
                if len(identity)!=1 or engines(process.pid)!=identity or Path(identity[0]['ExecutablePath'])!=exe:
                    raise RuntimeError('Engine ownership/identity differs before measurement')
                arm['engine'] = identity
                arm['memory_ready'] = system_memory()
                if args.procdump:
                    monitor_log = (trial/'procdump.log').open('wb')
                    monitor = subprocess.Popen([str(args.procdump),'-accepteula','-e','-mt',
                        str(identity[0]['ProcessId']),str(trial/'crash.dmp')],stdout=monitor_log,stderr=subprocess.STDOUT)
                    deadline = time.monotonic()+15
                    while not debugger_present(identity[0]['ProcessId']):
                        if monitor.poll() is not None or time.monotonic()>=deadline:
                            raise RuntimeError('Crash monitor did not attach to the owned engine')
                        time.sleep(.1)
                    arm['crash_monitor_attached'] = True
                print(f'{round_index} {label}: ready pid={identity[0]["ProcessId"]}',flush=True)
                for tag,prompt,expected,maximum in fixture:
                    if engines()!=identity: raise RuntimeError('Engine died/replaced; no new request sent')
                    if existing_status(args.existing_url)['loaded']: raise RuntimeError('Foreign API loaded during measurement')
                    row = dict(case=tag,expected=expected,passed=False,memory_before=system_memory())
                    arm['requests'].append(row); save()
                    started = time.monotonic()
                    response = api(base,'/v1/chat/completions',dict(model=cfg['model_name'],
                        messages=[dict(role='user',content=prompt)],temperature=0,stream=False,max_tokens=maximum,
                        reasoning_budget_tokens=32,chat_template_kwargs=dict(enable_thinking=False)),timeout=600)
                    row.update(elapsed_s=time.monotonic()-started,timings=response.get('timings'),usage=response.get('usage'))
                    row['memory_after'] = system_memory()
                    row['engine_stable'] = engines()==identity
                    (trial/(tag+'.json')).write_text(json.dumps(response,indent=2),encoding='utf-8')
                    text = response['choices'][0]['message'].get('content','').strip()
                    try: row['answer_correct'] = json.loads(text)==expected
                    except ValueError: row['answer_correct'] = False
                    row['passed'] = row['engine_stable'] and row['answer_correct']
                    save(); print(f'{round_index} {label}: {tag} {row["elapsed_s"]:.2f}s correct={row["answer_correct"]} stable={row["engine_stable"]}',flush=True)
                    if not row['engine_stable']: raise RuntimeError('Engine died/replaced during request; arm stopped')
                arm['passed'] = all(row['passed'] for row in arm['requests'])
            except Exception as error:
                arm['error'] = type(error).__name__+': '+str(error)
                if isinstance(error,urllib.error.HTTPError):
                    arm['http_error_body'] = error.read(65536).decode('utf-8',errors='replace')
                print(f'{round_index} {label}: {arm["error"]}',flush=True)
            finally:
                if process.poll() is None:
                    try: arm['unload'] = api(base,'/unload?wait=10',{},timeout=25)
                    except Exception as error: arm['unload_error'] = str(error)
                remaining = engines(process.pid)
                # Never abandon a live owned engine by terminating only its API.
                if remaining:
                    arm['remaining_engines'] = remaining; save()
                    raise RuntimeError('Test engine cleanup unconfirmed; API retained for explicit inspection')
                if monitor is not None:
                    if monitor.poll() is None:
                        subprocess.run([str(args.procdump),'-cancel',str(identity[0]['ProcessId'])],
                            capture_output=True,check=True,timeout=15)
                    monitor.wait(timeout=20)
                    arm['crash_monitor_exit'] = monitor.returncode
                    monitor_log.close()
                    arm['crash_dump'] = str(trial/'crash.dmp') if (trial/'crash.dmp').exists() else None
                if process.poll() is None: process.terminate()
                process.wait(timeout=20)
                arm['cleanup'] = True
                arm['memory_after_cleanup'] = system_memory()
                if (trial/'engine.log').exists():
                    text = (trial/'engine.log').read_text(encoding='utf-8',errors='replace')
                    arm['engine_start_count'] = text.count('engine started:')
                    arm['allocation_messages'] = [line for line in text.splitlines()
                        if any(part in line for part in ('out of memory','scratch reduced','scratch unavailable','staging reduced'))]
                    if arm['engine_start_count']!=1: arm['passed']=False
                save()
    result['existing_after'] = existing_status(args.existing_url)
    result['passed'] = all(arm['passed'] and arm['cleanup'] for arm in result['arms'])
    save(); print(output/'report.json',flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
