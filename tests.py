from funnl import Server, Handler
import unittest
import threading
import time
import httplib
import tempfile
import logging
import os

class Page(Handler):
    route = r"/page/(\d+)?"
    def get(self, number='0'):
        number = int(number)
        self.headers['content-type'] = 'text/html'
        return "<b>PAGE %d</b>" % number
        
    def post(self, number='0'):
        return uninitialized
        
STATIC_CONTENT = """THIS IS A STATIC FILE.\r\n"""
TEMP_FILE = None

class Test(unittest.TestCase):
    
    def setUp(self):
        self.conn = httplib.HTTPConnection('localhost:8081')
    
    def test_200(self):
        self.conn.request('GET', '/page/5')
        response = self.conn.getresponse()
        self.assertTrue(response.status == 200)
        self.assertTrue(response.read() == "<b>PAGE %d</b>" % 5)
        
    def test_404(self):
        self.conn.request('GET', '/pages/arent/here')
        response = self.conn.getresponse()
        self.assertTrue(response.status == 404)
    
    def test_500(self):
        self.conn.request('POST', '/page/10')
        response = self.conn.getresponse()
        self.assertTrue(response.status == 500)
        
    def test_static_200(self):
        uri = '/static/%s' % TEMP_FILE
        self.conn.request('GET', uri)
        response = self.conn.getresponse()
        self.assertTrue(response.status == 200)
        data = response.read()
        self.assertTrue(data == STATIC_CONTENT)
        
def start_server():
    global TEMP_FILE
    temporary_file = tempfile.NamedTemporaryFile(prefix="funnl_test")
    temporary_file.write(STATIC_CONTENT)
    temporary_file.flush()
    static_dir = os.path.dirname(temporary_file.name)
    TEMP_FILE = os.path.basename(temporary_file.name)
    server = Server(static_path=static_dir)
    server.add_handler(Page)
    server.enable_static()
    thread = threading.Thread(
        target=server.serve, kwargs={'port':8081, 'quiet':True}
    )
    thread.daemon = True
    thread.start()
    # Give it time to spin up
    time.sleep(1)
    return temporary_file

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.CRITICAL)
    temp_file = start_server()
    unittest.main()
    temp_file.close()
