import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

import lab_support


class StartupReadinessTests(unittest.TestCase):
    def test_connection_closed_during_startup_is_retried(self):
        class StartingServer(BaseHTTPRequestHandler):
            attempts = 0

            def do_GET(self):
                type(self).attempts += 1
                if self.attempts < 3:
                    self.close_connection = True
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'version': 'ready'}).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), StartingServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        previous_url = lab_support.BASE_URL
        try:
            lab_support.BASE_URL = f'http://127.0.0.1:{server.server_port}'
            self.assertEqual({'version': 'ready'}, lab_support.wait_for_api(timeout=5))
            self.assertEqual(3, StartingServer.attempts)
        finally:
            lab_support.BASE_URL = previous_url
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
