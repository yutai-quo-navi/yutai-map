#!/usr/bin/env python3
"""Wait for the next quota reset only when D1 explicitly returns code 7500."""
import datetime as dt
import subprocess
import time

COMMAND = ['npx', 'wrangler', 'd1', 'migrations', 'apply', 'yutai-map',
           '--remote', '--config', 'cloudflare/wrangler.toml']
MAX_WAIT_SECONDS = 2 * 60 * 60 + 30 * 60


def apply(run=subprocess.run, sleep=time.sleep, now=lambda: dt.datetime.now(dt.timezone.utc)):
    for attempt in range(4):
        result = run(COMMAND, capture_output=True, text=True)
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)
        if result.returncode == 0:
            return
        output = result.stdout + result.stderr
        if '7500' not in output or 'daily row read limit' not in output:
            raise RuntimeError('D1 migration failed; automatic quota retry does not apply')
        current = now()
        reset = (current + dt.timedelta(days=1)).replace(hour=0,minute=0,second=20,microsecond=0)
        wait = (reset-current).total_seconds() if attempt == 0 else 60
        if wait > MAX_WAIT_SECONDS or attempt == 3:
            raise RuntimeError('D1 quota reset is outside the bounded deployment recovery window')
        print(f'D1 read quota exhausted. Retry {attempt+1} at {(current+dt.timedelta(seconds=wait)).isoformat()}; no D1 queries during wait.', flush=True)
        while wait > 0:
            interval = min(wait, 60)
            sleep(interval)
            wait -= interval


if __name__ == '__main__':
    apply()
