"""Run the real health shell logic against isolated curl/systemctl fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HealthTests(unittest.TestCase):
    def test_health_exit_status_matches_readiness_and_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root/'health.sh'
            # Deployment setup changes PATH and redirects logs; isolate only
            # that setup, retaining the complete production health logic.
            script.write_text((ROOT/'scripts/health.sh').read_text().replace(
                'source /home/yyy/digital-human/deploy-env.sh', 'set -Eeuo pipefail'))
            curl = root/'curl'
            curl.write_text('''#!/usr/bin/env python3
import os, sys
args = sys.argv
url = next(a for a in args if a.startswith('http://'))
if os.environ['SCENARIO'] == 'unreachable' and ':8080/' in url:
    sys.exit(7)
body = '{"status":"ok"}'
if ':9881/' in url:
    body = {'not_ready':'{"ready":false}', 'string_ready':'{"ready":"true"}',
            'bad_json':'invalid', 'wrong_shape':'[]'}.get(os.environ['SCENARIO'], '{"ready":true}')
open(args[args.index('-o')+1], 'w').write(body)
''')
            unit = root/'systemctl'
            unit.write_text('#!/bin/sh\n[ "$SCENARIO" != "unit_failed" ]\n')
            curl.chmod(0o755)
            unit.chmod(0o755)
            for scenario in ('ok', 'not_ready', 'string_ready', 'bad_json', 'wrong_shape', 'unreachable', 'unit_failed'):
                with self.subTest(scenario=scenario):
                    result = subprocess.run(['bash', str(script)], env={**os.environ,
                        'PATH': str(root)+os.pathsep+os.environ['PATH'], 'SCENARIO': scenario,
                        'TMPDIR': str(root)}, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0 if scenario == 'ok' else 1, result.stdout+result.stderr)
                    self.assertEqual(sorted(p.name for p in root.iterdir()), ['curl', 'health.sh', 'systemctl'])


if __name__ == '__main__':
    unittest.main()
