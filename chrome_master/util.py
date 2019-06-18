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

'''公共库
'''

import logging as logger

class ChromeDebuggerProtocolError(RuntimeError):
    '''Chrome调试错误
    '''

    def __new__(self, code, message):
        if self is ChromeDebuggerProtocolError:
            for it in globals():
                obj = globals()[it]
                if isinstance(obj, type) and obj != self and issubclass(obj, self):
                    if obj.code == code:
                        return obj(code, message)
        return RuntimeError.__new__(self, code, message)

    def __init__(self, code, message):
        self._code = code
        self._message = message

    def __str__(self):
        return '[%s] %s' % (self._code, self._message)

    def __repr__(self):
        return '<%s object[code=%d message=%r] at 0x%.8x>' % (self.__class__.__name__, self._code, self._message, id(self))

    @property
    def code(self):
        return self._code

    @property
    def message(self):
        return self._message


class MethodNotFoundError(ChromeDebuggerProtocolError):
    '''Chrome调试接口不存在错误
    '''
    code = -32601

class JavaScriptError(RuntimeError):
    '''执行JavaScript报错
    '''
    def __init__(self, frame, err_msg):
        super(JavaScriptError, self).__init__(err_msg)
        self._frame = frame
        self._err_msg = err_msg

    @property
    def frame(self):
        '''发生JS异常的frame
        '''
        return self._frame

    @property
    def message(self):
        return self._err_msg

    def __str__(self):
        return '[%s] %s' % (self.frame, self._err_msg)


class ConnectionClosedError(RuntimeError):
    '''连接已关闭
    '''
    pass


class TimeoutError(RuntimeError):
    '''超时错误
    '''
    pass

def hook_WebSocket_connect(sock):
    '''由于WebSocketApp的run_forever不支持传入`socket`参数，使用hook来实现
    '''
    import websocket
    if not sock: return
    orgin_connect = websocket.WebSocket.connect
    def new_connect(self, url, **options):
        options['socket'] = sock
        result = orgin_connect(self, url, **options)
        websocket.WebSocket.connect = orgin_connect  # unhook
        return result
    websocket.WebSocket.connect = new_connect



