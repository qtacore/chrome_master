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

'''远程调试器基类
'''

import json
import threading
import time
import websocket

try:
    import Queue as queue
except ImportError:
    import queue

from .util import ChromeDebuggerProtocolError, ConnectionClosedError, TimeoutError, hook_WebSocket_connect, logger

class RemoteDebugger(object):
    '''远程调试器
    '''
    
    def __init__(self, ws_addr, open_socket_func=None):
        self._ws_addr = ws_addr
        self._open_socket = open_socket_func
        self._ws = websocket.WebSocketApp(self._ws_addr,
                              on_open=self.on_open,
                              on_message=self.on_message,
                              on_error=self.on_error,
                              on_close=self.on_close)
        self._seq = 0
        self._connected = False
        self._context_dict = {}
        self._data_dict = {}
        self._message_queue = queue.Queue()
        self._running = True
        t = threading.Thread(target=self.work_thread)
        t.setDaemon(True)
        t.start()
        t = threading.Thread(target=self.websocket_thread)
        t.setDaemon(True)
        t.start()
        self._wait_for_ready()
        self._handlers = {}
    
    # ================= WebSocket callback start ===========================
    def on_open(self, ws=None):
        '''WebSocket打开回调
        '''
        self._connected = True
        
    def on_message(self, ws, message=None):
        '''收到消息
        '''
        if message is None: message = ws # 兼容新版本websocket_client
        message = json.loads(message)
        if 'id' in message:
            logger.debug('[%s][recv][%d] %s' % (self.__class__.__name__, message['id'], json.dumps(message['result'])[:200]))
            self._data_dict[message['id']] = message
        else:
            self._message_queue.put(message)
                
    def on_error(self, ws, error=None):
        if error is None: error = ws
        logger.error('[%s] error: %s' % (self.__class__.__name__, error))
     
    def on_close(self, ws=None):
        logger.debug('[%s] close' % (self.__class__.__name__))
    
    # =================== WebSocket callback end =============================
    
    def __str__(self):
        return '<%s object [%s] at 0x%.8X>' % (self.__class__.__name__, self._ws_addr, id(self))
    
    
    def _wait_for_ready(self, timeout=10, interval=0.1):
        '''等待WebSocket连接
        '''
        time0 = time.time()
        while time.time() - time0 < timeout:
            if self._connected: break
            time.sleep(interval)
        else:
            raise RuntimeError('Connect %s failed' % self._ws_addr)

    def websocket_thread(self):
        '''websocket working thread
        '''
        if self._open_socket:
            sock = self._open_socket()
            hook_WebSocket_connect(sock)
        self._ws.run_forever()

    def work_thread(self):
        '''工作线程
        '''
        while self._running:
            if self._message_queue.empty():
                time.sleep(0.01)
                continue
            message = self._message_queue.get()
            try:
                self.on_recv_notify_msg(message['method'], message['params'])
            except ConnectionClosedError:
                logger.warn('[%s] Websocket connection closed' % self.__class__.__name__)
            except:
                logger.exception('[%s] Handle %s message error' % (self.__class__.__name__, message['method']))
    
    def _wait_for_response(self, seq, timeout=10, interval=0.1):
        '''等待返回数据
        '''
        time0 = time.time()
        while time.time() - time0 < timeout:
            if seq in self._data_dict: 
                result = self._data_dict.pop(seq)
                if 'result' in result:
                    return result['result']
                elif 'error' in result:
                    logger.warn('[%s] response error %s' % (self.__class__.__name__, result))
                    raise ChromeDebuggerProtocolError(result['error']['code'], result['error']['message'])
                
            time.sleep(interval)
        else:
            raise TimeoutError('Wait for [%s] response timeout' % seq)
        
    def send_request(self, method, **kwds):
        '''发送请求
        
        :param method: 命令字
        :type method:  string
        '''
        if not self._ws:
            raise ConnectionClosedError('Websocket connection is closed')
        self._seq += 1
        request = {'id': self._seq, 'method': method}
        if kwds: request['params'] = kwds
        data = json.dumps(request)
        self._ws.send(data)
        if 'params' in request:
            params = json.dumps(request['params'])
        else:
            params = ''
        logger.debug('[%s][send][%d][%s] %s' % (self.__class__.__name__, self._seq, method, params[:400]))
        return self._wait_for_response(self._seq)
    
    def on_recv_notify_msg(self, method, params):
        '''接收到通知消息
        
        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        '''
        namespace, method = method.split('.')
        for ns in self._handlers:
            if ns == namespace:
                self._handlers[ns].on_recv_notify_msg(method, params)
        
    def register_handler(self, handler_cls):
        '''注册处理器
        '''
        namespace = handler_cls.namespace
        if namespace in self._handlers:
            logger.warn('[%s] Namespace %s handler is registered' % (self.__class__.__name__, namespace))
        logger.debug('[%s] register handler %s' % (self.__class__.__name__, namespace))
        handler = handler_cls(self)
        self._handlers[namespace] = handler
        for dep in handler.__class__.dependencies:
            if not dep.namespace in self._handlers:
                self.register_handler(dep)
        handler.on_attached()
    
    def unregister_handler(self, handler_cls):
        '''移除处理器
        '''
        namespace = handler_cls.namespace
        if not namespace in self._handlers:
            raise RuntimeError('Handler %s not registered' % (handler_cls))
        self._handlers.pop(namespace)
        
    def __getattr__(self, attr):
        '''根据命名空间获取已注册的处理器
        '''
        for namespace in self._handlers:
            if namespace == attr or namespace.lower() == attr:
                return self._handlers[namespace]
        raise AttributeError("'%s' object has no attribute '%s'" % (self.__class__.__name__, attr))
        
    def close(self):
        '''关闭调试器
        '''
        self._running = False
        if self._ws:
            self._ws.close()
            self._ws = None
        
        