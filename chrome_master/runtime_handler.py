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

'''Runtime命名空间的处理器
'''

import json
import time
from .handler import DebuggerHandler
from .page_handler import PageHandler
from .util import JavaScriptError, ChromeDebuggerProtocolError, logger

class RuntimeHandler(DebuggerHandler):
    '''Runtime命名空间的处理器
    '''
    namespace = 'Runtime'
    dependencies = [PageHandler]
    max_console_log_count = 100 # 最大存储的Console日志条数

    def on_attached(self):
        '''附加到调试器成功回调
        '''
        self._context_dict = {}
        self._frame_dict = {}
        self._console_logs = []
        self._console_callback = None
        self._tag = ''
        self.enable()
        self._tag = self.eval_script(None, 'document.title || location.href')

    def on_recv_notify_msg(self, method, params):
        '''接收到通知消息
        
        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        '''
        if method == 'executionContextCreated':
            # 有新的frame创建
            context = params['context']
            if 'type' in context and context['type'] == 'Extension': return
            if 'frameId' in context: frame_id = context['frameId']
            else: frame_id = context['auxData']['frameId']
            self._context_dict[frame_id] = context['id']
            logger.debug('[%s] add context: %s(%s %s)' % (self.__class__.namespace, context['id'], frame_id, context.get('origin')))
        elif method == 'executionContextDestroyed':
            context_id = params['executionContextId']
            for frame in self._context_dict:
                if self._context_dict[frame] == context_id:
                    del self._context_dict[frame]
                    break
        elif method == 'consoleAPICalled':
            for it in params['args']:
                value = None
                if it['type'] == 'object' and 'objectId' in it:
                    value = {
                        'object_id': it['objectId']
                    }
                elif it['value']:
                    value = it['value']
                else:
                    return
                log = {
                    'timestamp': params['timestamp'],
                    'function': params['type'],
                    'frame': self._get_frame_id(params['executionContextId']),
                    'type': it['type'],
                    'value': value
                }
                if len(self._console_logs) >= self.max_console_log_count:
                    self._console_logs.pop(0) # abandon old log
                self._console_logs.append(log)
                if self._console_callback:
                    self.handle_console_log(log)
                    self._console_callback(log)

    def handle_console_log(self, log):
        '''Lazy retrieve log data
        '''
        if log['type'] == 'object' and isinstance(log['value'], dict) and log['value'].get('object_id'):
            object_id = log['value']['object_id']
            log['value'] = self.get_object_properties(object_id)

    def set_console_callback(self, callback):
        '''Callback for console log
        '''
        self._console_callback = callback
        for log in self._console_logs:
            # Handle logs before set console callback
            self.handle_console_log(log)
            callback(log)

    def _get_context_id(self, frame_id, timeout=5):
        '''frame id to context id
        '''
        time0 = time.time()
        while time.time() - time0 < timeout:
            if frame_id in self._context_dict:
                time_cost = time.time() - time0
                if time_cost >= 0.1: logger.debug('[%s] wait context id for %s cost %sS' % (self.__class__.namespace, frame_id, time_cost))
                return self._context_dict[frame_id]
            time.sleep(0.01)
        else:
            raise RuntimeError('Can\'t find Context Id of %s' % frame_id)

    def _get_frame_id(self, context_id):
        '''context id to frame id
        '''
        for frame_id in self._context_dict:
            if self._context_dict[frame_id] == context_id:
                return frame_id
        else:
            raise RuntimeError('Context id %s not exist' % context_id)

    def _handle_object_value(self, value):
        if value['type'] in ('number', 'string', 'boolean'):
            return value['value']
        elif value['type'] == 'function':
            return value['description']
        elif value['type'] == 'object':
            if not 'description' in value:
                return None
            return value['description']
        elif value['type'] == 'undefined':
            return 'undefined'
        else:
            raise NotImplementedError(value['type'])

    def get_object_properties(self, object_id):
        '''获取对象属性
        '''
        properties = {}
        result = self.getProperties(objectId=object_id)
        for it in result['result']:
            if 'value' in it:
                properties[it['name']] = self._handle_object_value(it['value'])
        return properties

    def eval_script(self, frame_id, script):
        '''执行JavaScript
        '''
        if frame_id == None:
            frame_id = self._debugger.page.get_main_frame_id()
        context_id = self._get_context_id(frame_id)
        logger.info('[%s][%s][%s][eval][%d] %s' % (self.__class__.namespace, self._tag, context_id, len(script), script[:200].strip()))
        script = script.replace('\\', r'\\')
        script = script.replace('"', r'\"')
        script = script.replace('\r', r'\r')
        script = script.replace('\n', r'\n')
        script = r'''(function(){
            try{
                var result = eval("%s");
                if(result != undefined){
                    return 'S' + result.toString();
                }else{
                    return 'Sundefined';
                }
            }catch(e){
                var retVal = 'E[' + e.name + ']' + e.message;//toString()
                retVal += '\n' + e.stack;
                return retVal;
            }
        })();''' % script
        params = {'objectGroup': 'console', 'includeCommandLineAPI': True, 'doNotPauseOnExceptionsAndMuteConsole': False, 'returnByValue': False, 'generatePreview': True}
        result = self.evaluate(contextId=context_id, expression=script, **params)
        result = result['result']['value']
        logger.info('[%s][%s][retn] %s' % (self.__class__.namespace, self._tag, result))
        if result[0] == 'E':
            raise JavaScriptError(frame_id, result[1:])
        elif result[0] == 'S':
            result = result[1:]
        else:
            raise ChromeDebuggerProtocolError(result)
        return result

    def read_console_log(self):
        '''read one console log
        '''
        if not self._console_logs: return None
        return self._console_logs.pop(0)
    
    
