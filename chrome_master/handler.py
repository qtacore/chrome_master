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

'''调试器处理器
'''

class DebuggerHandler(object):
    '''调试器处理器
    '''
    namespace = ''  # 命名空间
    dependencies = []  # 依赖的Handler
    
    def __init__(self, debugger):
        self._debugger = debugger
        
    def on_attached(self):
        '''附加到调试器成功回调
        '''
        pass
    
    def on_detached(self):
        '''调试器分离回调
        '''
        pass
    
    def on_recv_notify_msg(self, method, params):
        '''接收到通知消息
        
        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        '''
        pass
        
    def __getattr__(self, attr):
        '''允许通过直接调用的方式发送请求 
        '''
        def _wrap_func(*args, **kwargs):
            '''
            '''
            return self._debugger.send_request(self.__class__.namespace + '.' + attr, *args, **kwargs)
        return _wrap_func
    
    def __str__(self):
        return '<%s Handler object at 0x%x.8X>' % (self.__class__.namespace, id(self))
    
    
