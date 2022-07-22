# -*- coding: UTF-8 -*-
#
# Tencent is pleased to support the open source community by making QTA available.
# Copyright (C) 2016THL A29 Limited, a Tencent company. All rights reserved.
# Licensed under the BSD 3-Clause License (the "License"); you may not use this
# file except in compliance with the License. You may obtain a copy of the License at
#
# https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" basis, WITHOUT WARRANTIES OR CONDITIONS
# OF ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.
#

"""chrome_master模块单元测试
"""

try:
    import BaseHTTPServer as httpserver
except ImportError:
    import http.server as httpserver
try:
    from unittest import mock
except:
    import mock
import json
import random
import threading
import time
import unittest

from SimpleWebSocketServer import SimpleWebSocketServer, WebSocket

import chrome_master


class ChromeDevToolHTTPRequestHandler(httpserver.BaseHTTPRequestHandler):
    """mock http server
    """

    def do_GET(self):
        server_port = self.server.server_port + 1
        if self.path == "/json":
            content = r"""[ {
   "description": "{\"attached\":false,\"empty\":true,\"screenX\":0,\"screenY\":0,\"visible\":true}",
   "devtoolsFrontendUrl": "http://chrome-devtools-frontend.appspot.com/serve_rev/@49c9ff7f3b4c6ae5b17d764ee0ac83a37cb118d2/inspector.html?ws=localhost/devtools/page/633EE4EE9AF1D054667A1CB246DB4290",
   "id": "1",
   "title": "测试",
   "type": "page",
   "url": "http://www.qq.com/",
   "webSocketDebuggerUrl": "ws://localhost:%(server_port)d/devtools/page/1"
}, {
   "description": "{\"attached\":true,\"empty\":false,\"height\":1715,\"screenX\":0,\"screenY\":205,\"visible\":true,\"width\":1080}",
   "devtoolsFrontendUrl": "http://chrome-devtools-frontend.appspot.com/serve_rev/@49c9ff7f3b4c6ae5b17d764ee0ac83a37cb118d2/inspector.html?ws=localhost/devtools/page/79AB29BD9D8FBCB436A675CA06496213",
   "id": "2",
   "title": "测试",
   "type": "page",
   "url": "http://www.qq.com/",
   "webSocketDebuggerUrl": "ws://localhost:%(server_port)d/devtools/page/2"
}, {
   "description": "{\"attached\":true,\"empty\":false,\"height\":1715,\"screenX\":0,\"screenY\":205,\"visible\":true,\"width\":1080}",
   "devtoolsFrontendUrl": "http://chrome-devtools-frontend.appspot.com/serve_rev/@49c9ff7f3b4c6ae5b17d764ee0ac83a37cb118d2/inspector.html?ws=localhost/devtools/page/79AB29BD9D8FBCB436A675CA06496213",
   "id": "3",
   "title": "测试",
   "type": "page",
   "url": "http://www.baidu.com/",
   "webSocketDebuggerUrl": "ws://localhost:%(server_port)d/devtools/page/3"
}]""" % {
                "server_port": server_port
            }
            if not isinstance(content, bytes):
                content = content.encode("utf8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)


class ChromeDevToolWebSocket(WebSocket):
    """mock websocket server
    """

    def handleMessage(self):
        request = json.loads(self.data)
        request_id = request["id"]
        method = request["method"]
        params = request.get("params")
        response = {"id": request_id}
        if method in (
            "Page.enable",
            "Runtime.enable",
            "Target.setAutoAttach",
            "Network.enable",
            "Target.setDiscoverTargets",
            "Log.enable",
            "Log.startViolationsReport",
        ):
            response["result"] = {}
        elif method == "Page.getResourceTree":
            response["result"] = {"frameTree": {"frame": {"id": 12345}}}
        elif method == "Runtime.evaluate":
            script = params["expression"]
            value = ""
            if "document.title || location.href" in script:
                value = "mock server"
            elif "document.body.innerText" in script:
                value = "mock server body"
            response["result"] = {"result": {"value": "S" + value}}
        elif method == "Target.attachedToTarget":
            response["result"] = {
                "sessionId": "16263CBABCC247FC55DC973CCB8F79AE",
                "targetInfo": {
                    "attached": True,
                    "browserContextId": "C978F982D6147B698EBB59FCEBDBB103",
                    "canAccessOpener": False,
                    "targetId": "65227AD1F58E257264FEC7C62AFECCE2",
                },
            }
        else:
            raise NotImplementedError(method)
        self.sendMessage(json.dumps(response))
        if method == "Runtime.enable":
            message = {
                "method": "Runtime.executionContextCreated",
                "params": {"context": {"id": 12345, "frameId": 12345}},
            }
            self.sendMessage(json.dumps(message))


class TestChromeMaster(unittest.TestCase):
    """ChromeMaster类测试用例
    """

    def _create_mock_http_server(self, port):
        server = httpserver.HTTPServer(
            ("127.0.0.1", port), ChromeDevToolHTTPRequestHandler
        )
        server.serve_forever()

    def _create_mock_websocket_server(self, port):
        server = SimpleWebSocketServer("127.0.0.1", port, ChromeDevToolWebSocket)
        server.serveforever()

    def _create_mock_server_in_thread(self, port):
        t1 = threading.Thread(target=self._create_mock_http_server, args=(port,))
        t1.setDaemon(True)
        t1.start()
        t2 = threading.Thread(
            target=self._create_mock_websocket_server, args=(port + 1,)
        )
        t2.setDaemon(True)
        t2.start()
        time.sleep(1)

    def test_get_page_list(self):
        port = random.randint(10000, 60000)
        self._create_mock_server_in_thread(port)
        client = chrome_master.ChromeMaster(("127.0.0.1", port))
        result = client.get_page_list()
        self.assertTrue(len(result) > 0)

    def test_find_page(self):
        port = random.randint(10000, 60000)
        self._create_mock_server_in_thread(port)
        client = chrome_master.ChromeMaster(("127.0.0.1", port))
        debugger = client.find_page("测试", "http://www.qq.com/")
        self.assertEqual(
            debugger._ws_addr,
            "ws://localhost:%(server_port)d/devtools/page/2"
            % {"server_port": port + 1},
        )

    def test_multi_pages(self):
        port = random.randint(10000, 60000)
        self._create_mock_server_in_thread(port)
        client = chrome_master.ChromeMaster(("127.0.0.1", port))
        debugger = client.find_page("测试")
        self.assertEqual(
            debugger._ws_addr,
            "ws://localhost:%(server_port)d/devtools/page/3"
            % {"server_port": port + 1},
        )
        self.assertRaises(RuntimeError, client.find_page, "测试", last=False)
