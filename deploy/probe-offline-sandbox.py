"""One-shot host acceptance probe; execute only inside the offline unit sandbox."""
import argparse
import errno
import json
import os
from pathlib import Path
import pwd
import socket

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--job', type=Path, required=True)
parser.add_argument('--release', type=Path, required=True)
parser.add_argument('--outside-file', type=Path, required=True,
                    help='Existing service-user-writable file outside the job; opening must fail in sandbox')
parser.add_argument('--host-tmp-marker', type=Path, required=True,
                    help='Existing host /tmp marker which PrivateTmp must hide')
args = parser.parse_args()
job, release = args.job, args.release
checks = {}
checks['unprivileged_identity'] = os.getuid() == pwd.getpwnam('trad3r').pw_uid != 0
checks['no_new_privileges'] = 'NoNewPrivs:\t1' in Path('/proc/self/status').read_text()
checks['no_effective_capabilities'] = 'CapEff:\t0000000000000000' in Path('/proc/self/status').read_text()
checks['loopback_only'] = socket.if_nameindex() == [(1, 'lo')]
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
    connection.settimeout(1)
    checks['external_ipv4_unreachable'] = connection.connect_ex(('198.51.100.1', 443)) == errno.ENETUNREACH
with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as connection:
    connection.settimeout(1)
    checks['external_ipv6_unreachable'] = connection.connect_ex(('2001:db8::1', 443)) == errno.ENETUNREACH
for name, path in {
    'source_read_only': job/'source.zip',
    'assumptions_read_only': job/'assumptions.json',
    'registration_read_only': job/'registration.json',
    'code_read_only': release/'trad3r/jobs.py',
    'environment_read_only': release/'.venv/pyvenv.cfg',
    'outside_job_read_only': args.outside_file,
}.items():
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    except OSError as error:
        checks[name] = error.errno in (errno.EROFS, errno.EACCES)
    else:
        os.close(descriptor)
        checks[name] = False
checks['private_tmp'] = not args.host_tmp_marker.exists()
probe = job/'sandbox-write-probe'
with probe.open('x') as stream:
    stream.write('synthetic probe\n')
checks['job_write_permitted'] = probe.read_text() == 'synthetic probe\n'
probe.unlink()
group = Path('/sys/fs/cgroup') / Path('/proc/self/cgroup').read_text().strip().split('::')[1].lstrip('/')
checks['memory_limit_1gib'] = (group/'memory.max').read_text().strip() == '1073741824'
checks['task_limit_32'] = (group/'pids.max').read_text().strip() == '32'
report = {'checks': checks, 'passed': all(checks.values()), 'cgroup': str(group)}
print(json.dumps(report, sort_keys=True), flush=True)
if not report['passed']:
    raise SystemExit(1)
