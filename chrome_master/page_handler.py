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

'''Page命名空间的处理器
'''

import base64

from .handler import DebuggerHandler
from .util import MethodNotFoundError, logger

class PageHandler(DebuggerHandler):
    '''Page命名空间的处理器
    '''
    namespace = 'Page'
    
    def on_attached(self):
        '''附加到调试器成功回调
        '''
        self.enable()
        self._screen_data = []
        
    def on_recv_notify_msg(self, method, params):
        '''接收到通知消息
        
        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        '''
        if method == 'screencastFrame':
            data = base64.b64decode(params['data'])
            self._screen_data.append((params['metadata']['timestamp'], data))
    
    def get_screen_record_data(self):
        '''get screen record data
        '''
        return self._screen_data
        
    def get_frame_tree(self):
        '''获取frame树
        '''
        result = self.getResourceTree()
        return result['frameTree']
    
    def get_main_frame_id(self):
        '''获取顶层frame id
        '''
        return self.get_frame_tree()['frame']['id']
        
    def bring_to_front(self):
        '''bring current page to front
        '''
        try:
            self.bringToFront()
            return True
        except MethodNotFoundError:
            return False
            
    def screenshot(self):
        '''capture current page screen
        
        :return: screen png data
        '''
        if not self.bring_to_front():
            logger.warn('Call bring_to_front failed')
        data = self.captureScreenshot()
        data = base64.b64decode(data['data'])
        return data
    
    def start_screencast(self):
        '''start screencast
        '''
        self.startScreencast()
    
    def stop_screencast(self):
        '''stop screencast
        '''
        self.stopScreencast()
        
    def get_cookies(self):
        '''get all cookies
        '''
        result = self.getCookies()
        return result['cookies']
    
    def get_window_size(self):
        '''get browser window size
        '''
        result = self.getLayoutMetrics()
        scale = result['visualViewport']['scale']
        width = result['visualViewport']['clientWidth']
        height = result['visualViewport']['clientHeight']
        return scale * width, scale * height
