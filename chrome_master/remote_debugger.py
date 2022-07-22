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

"""远程调试器基类
"""

from __future__ import unicode_literals
import json
import threading
import time
import websocket

try:
    import Queue as queue
except ImportError:
    import queue

from .util import (
    ChromeDebuggerProtocolError,
    ConnectionClosedError,
    MessageNotHandledError,
    TimeoutError,
    hook_WebSocket_connect,
    logger,
)


class RemoteDebugger(object):
    """远程调试器"""

    def __init__(self, ws_addr, open_socket_func=None):
        self._ws_addr = ws_addr
        self._open_socket = open_socket_func
        self._ws = websocket.WebSocketApp(
            self._ws_addr,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self._seq = 0
        self._connected = False
        self._handlers = {}
        self._data_dict = {}
        self._message_queue = queue.Queue()
        self._retry_message_queue = queue.Queue()
        self._running = True
        self._logger = logger
        t = threading.Thread(target=self.work_thread)
        t.setDaemon(True)
        t.start()
        t = threading.Thread(target=self.websocket_thread)
        t.setDaemon(True)
        t.start()
        self._wait_for_ready()

    @property
    def logger(self):
        return self._logger

    @logger.setter
    def logger(self, _logger):
        self._logger = _logger

    # ================= WebSocket callback start ===========================
    def on_open(self, ws=None):
        """WebSocket打开回调"""
        self._connected = True

    def on_message(self, ws, message=None):
        """收到消息"""
        if message is None:
            message = ws  # 兼容新版本websocket_client
        message = json.loads(message)

        if "id" in message:
            self.logger.debug(
                "[%s][%x][recv][%d] %s"
                % (
                    self.__class__.__name__,
                    id(self),
                    message["id"],
                    json.dumps(message.get("result", ""))[:200],
                )
            )
            self._data_dict[message["id"]] = message
        else:
            message["timestamp"] = time.time()
            self._message_queue.put(message)

    def on_error(self, ws, error=None):
        if error is None:
            error = ws
        self._connected = False
        self.logger.error("[%s] Recv error: %s" % (self.__class__.__name__, error))

    def on_close(self, ws=None):
        self._connected = False
        self.logger.info("[%s] Recv close" % (self.__class__.__name__))

    # =================== WebSocket callback end =============================

    def __str__(self):
        return "<%s object [%s] at 0x%.8X>" % (
            self.__class__.__name__,
            self._ws_addr,
            id(self),
        )

    def _wait_for_ready(self, timeout=10, interval=0.1):
        """等待WebSocket连接"""
        time0 = time.time()
        while time.time() - time0 < timeout:
            if self._connected:
                break
            time.sleep(interval)
        else:
            raise RuntimeError("Connect %s failed" % self._ws_addr)

    def websocket_thread(self):
        """websocket working thread"""
        if self._open_socket:
            sock = self._open_socket()
            hook_WebSocket_connect(sock)
        self._ws.run_forever()

    def enqueue_delay_message(self, message, delay=0.5):
        """放入重试队列"""
        timeout = 10
        if time.time() - message["timestamp"] > timeout:
            self.logger.warn(
                "[%s] Abandon message %s" % (self.__class__.__name__, message)
            )
        message["runat"] = time.time() + delay
        self._retry_message_queue.put(message)

    def work_thread(self):
        """工作线程"""
        while self._running:
            message = None
            if self._message_queue.empty():
                if not self._retry_message_queue.empty():
                    if self._retry_message_queue.queue[0]["runat"] <= time.time():
                        message = self._retry_message_queue.get()
                        message.pop("runat")

                if not message:
                    time.sleep(0.01)
                    continue
            else:
                message = self._message_queue.get()
            try:
                self.on_recv_notify_msg(message["method"], message.get("params", {}))
            except MessageNotHandledError:
                self.enqueue_delay_message(message, 2)
            except ConnectionClosedError:
                self.logger.warn(
                    "[%s] Websocket connection closed" % self.__class__.__name__
                )
            except:
                self.logger.exception(
                    "[%s] Handle %s message error"
                    % (self.__class__.__name__, message["method"])
                )

    def _wait_for_response(self, request, timeout=120, interval=0.005):
        """等待返回数据"""
        time0 = time.time()
        while time.time() - time0 < timeout:
            if not self._connected:
                raise ConnectionClosedError(
                    "Connection closed when reading response of request %s" % request
                )

            if request["id"] in self._data_dict:
                result = self._data_dict.pop(request["id"])
                if "result" in result:
                    return result["result"]
                elif "error" in result:
                    self.logger.warn(
                        "[%s] Response error: %s" % (self.__class__.__name__, json.dumps(result))
                    )
                    raise ChromeDebuggerProtocolError(
                        result["error"]["code"],
                        result["error"]["message"],
                        result["error"].get("data"),
                    )

            time.sleep(interval)
        else:
            raise TimeoutError("Wait for response of request %s timeout" % request)

    def send_request(self, method, session_id='', **kwds):
        """发送请求

        :param method: 命令字
        :type method:  string
        """
        if not self._ws:
            raise ConnectionClosedError("Websocket connection %x is closed" % id(self))
        self._seq += 1
        request = {"id": self._seq, "method": method}
        if kwds:
            request["params"] = kwds
        if session_id:
            request['sessionId'] = session_id
        data = json.dumps(request)
        try:
            self._ws.send(data)
        except websocket.WebSocketConnectionClosedException as e:
            raise ConnectionClosedError(e.message)

        if "params" in request:
            params = json.dumps(request["params"])
        else:
            params = ""
        while params.find(" " * 2) >= 0:
            # remove multi spaces
            params = params.replace(" " * 2, " ")
        self.logger.debug(
            "[%s][%x][send][%d][%s] %s"
            % (self.__class__.__name__, id(self), self._seq, method, params[:400])
        )
        return self._wait_for_response(request)

    def on_recv_notify_msg(self, method, params):
        """接收到通知消息

        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        """
        namespace, method = method.split(".")
        for ns in list(self._handlers.keys()):
            if ns == namespace:
                self._handlers[ns].on_recv_notify_msg(method, params)

    def register_handler(self, handler_cls, *args, **kwargs):
        """注册处理器"""
        namespace = handler_cls.namespace
        if namespace in self._handlers:
            self.logger.info(
                "[%s] Namespace %s handler is realdy registered"
                % (self.__class__.__name__, namespace)
            )
            return self._handlers[namespace]
        self.logger.debug(
            "[%s] Register handler %s" % (self.__class__.__name__, namespace)
        )
        handler = handler_cls(self, *args, **kwargs)
        handler.logger = self.logger
        self._handlers[namespace] = handler
        for dep in handler.__class__.dependencies:
            if not dep.namespace in self._handlers:
                self.register_handler(dep)
        handler.on_attached()

    def unregister_handler(self, handler_cls):
        """移除处理器"""
        namespace = handler_cls.namespace
        if not namespace in self._handlers:
            raise RuntimeError("Handler %s not registered" % (handler_cls))
        self._handlers.pop(namespace)

    def dispatch_event(self, event, *args, **kwargs):
        for ns in self._handlers:
            self._handlers[ns].dispatch_event(event, *args, **kwargs)

    def __getattr__(self, attr):
        """根据命名空间获取已注册的处理器"""
        for namespace in self._handlers:
            if namespace == attr or namespace.lower() == attr:
                return self._handlers[namespace]
        raise AttributeError(
            "'%s' object has no attribute '%s'" % (self.__class__.__name__, attr)
        )

    def close(self):
        """关闭调试器"""
        self._running = False
        if self._ws:
            self.logger.info(
                "[%s] WebSocket connection closed" % self.__class__.__name__
            )
            self._ws.close()
            self._ws = None
