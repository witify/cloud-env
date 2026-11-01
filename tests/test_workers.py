"""Run with: python3 -m unittest discover tests"""
import pathlib
import socket
import subprocess
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / 'lib.sh'


def not_up(workers):
    script = f'''
source "{LIB}" 2>/dev/null
background_workers() {{ cat <<'EOF'
{workers}
EOF
}}
workers_not_up
'''
    # On stdin: pgrep on Linux would match the worker list in the argv of bash -c.
    return subprocess.run(['bash', '-s'], input=script, capture_output=True, text=True, check=True).stdout.split()


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class WorkersNotUpTest(unittest.TestCase):
    def run_process(self, seconds):
        process = subprocess.Popen(['sleep', seconds])
        # Cleanups run last in, first out.
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return f'sleep {seconds}'

    def listen_later(self, port, delay):
        server = socket.socket()
        self.addCleanup(server.close)

        def start():
            server.bind(('127.0.0.1', port))
            server.listen()

        timer = threading.Timer(delay, start)
        self.addCleanup(timer.cancel)
        timer.start()

    def test_no_worker_means_no_wait(self):
        started = time.monotonic()
        self.assertEqual(not_up(''), [])
        self.assertLess(time.monotonic() - started, 1)

    def test_only_the_workers_that_are_down_are_named(self):
        late_port, closed_port = free_port(), free_port()
        self.listen_later(late_port, 4)

        workers = '\n'.join([
            f"alive|{self.run_process('317.5')}",
            'dead|sleep 318.5',
            f"listening-late|{self.run_process('319.5')}|{late_port}",
            f"never-listening|{self.run_process('320.5')}|{closed_port}",
            f'dead-with-port|sleep 321.5|{late_port}',
        ])

        self.assertEqual(not_up(workers), ['dead', 'never-listening', 'dead-with-port'])


if __name__ == '__main__':
    unittest.main()
