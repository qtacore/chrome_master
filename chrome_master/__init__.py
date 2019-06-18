# -*- coding: utf-8 -*-
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

'''Chrome远程调试协议实现
https://chromedevtools.github.io/devtools-protocol/
'''

try:
    import httplib
except ImportError:
    import http.client as httplib
import json
import re
import socket
import sys
import time

from . import util
from .remote_debugger import RemoteDebugger
from .input_handler import InputHandler
from .runtime_handler import RuntimeHandler
from .page_handler import PageHandler


def set_logger(logger):
    '''
    '''
    from . import remote_debugger
    from . import runtime_handler
    from . import page_handler
    util.logger = logger
    remote_debugger.logger = logger
    runtime_handler.logger = logger
    page_handler.logger = logger


class ChromeMaster(object):
    '''Chrome控制端
    '''
    instances = {}

    def __new__(cls, addr, open_socket_func=None):
        key = '%s:%d' % addr
        if key not in cls.instances:
            if sys.version_info[0] == 2:
                cls.instances[key] = super(ChromeMaster, cls).__new__(cls, addr, open_socket_func)
            else:
                cls.instances[key] = super(ChromeMaster, cls).__new__(cls)
        return cls.instances[key]

    def __init__(self, addr, open_socket_func=None):
        '''
        :param addr: (ip, port)
        :param open_socket_func: 创建socket函数
        '''
        if not hasattr(self, '_addr'):  # not initiatized
            self._addr = addr
            self._open_socket = open_socket_func
            self._pages = {}

    def get_page_info(self, debugger_url, url, title):
        result = {
            'title': title,
            'url': url,
            'body': None
        }
        debugger = RemoteDebugger(debugger_url, self._open_socket)
        debugger.register_handler(RuntimeHandler)
        result['body'] = debugger.runtime.eval_script(None, 'document.body.innerText')
        if not result['body']:
            debugger.close()
            return result
        if result['title'] == 'about:blank':
            result['title'] = debugger.runtime.eval_script(None, 'document.title')
        if result['url'] == 'about:blank':
            result['url'] = debugger.runtime.eval_script(None, 'location.href')
        debugger.close()
        return result

    def get_page_list(self):
        '''获取打开的页面列表
        '''
        conn = httplib.HTTPConnection(self._addr[0], self._addr[1], timeout=60)
        if self._open_socket:
            if hasattr(conn, '_create_connection'):
                conn._create_connection = lambda address, timeout, source_address: self._open_socket(
                )
            else:
                # older 2.7 version
                conn.sock = self._open_socket()
        conn.request('GET', '/json')
        result = conn.getresponse().read()
        conn.close()
        util.logger.debug(result)

        try:
            page_list = json.loads(result)
        except ValueError:
            raise RuntimeError(
                'Get page list failed. Pls close the page debugger')

        result = []
        for page in page_list:
            if page['type'] != 'page':
                continue

            desc = page['description']
            if desc:
                page['description'] = json.loads(desc)
                if not page['description'].get(
                        'width') or not page['description'].get('height'):
                    continue
                if not page['description']['visible']: continue
            
            if 'webSocketDebuggerUrl' not in page:
                util.logger.warn('[%s] Page %s debugger is opened' % (self.__class__.__name__, page))
                continue

            page_info = self.get_page_info(page['webSocketDebuggerUrl'], page['url'], page['title'])
            if not page_info['body']:
                util.logger.warn('[%s] Page %s body is null' % (self.__class__.__name__, page))
                continue

            if page['url'] == 'about:blank' and page['title'] == 'about:blank':
                is_blank_url = True
                if page_info['url']:
                    page['url'] = page_info['url']
                    is_blank_url = False
                if page_info['title']:
                    page['title'] = page_info['title']
                    is_blank_url = False
                if is_blank_url:
                    continue
            
            if page['id'] not in self._pages:
                self._pages[page['id']] = time.time()  # add timestamp
            page['timestamp'] = self._pages[page['id']]
            result.append(page)
        result.sort(key=lambda page: page['timestamp'])
        return result

    def find_page(self, title=None, url=None, last=True):
        '''查找目标页面
        
        :param title: 目标页面标题
        :type  title: string
        :param url:   目标页面url
        :type  url:   string
        :param last:  是否取最后一个页面
        :type  last:  boolean
        '''
        page_list = self.get_page_list()
        if not page_list:
            raise RuntimeError('No page found in address %s:%s' % self._addr)
        util.logger.debug('[%s] Page list: %s' % (self.__class__.__name__, page_list))

        if not title and not url:
            if len(page_list) == 1 or last:
                url = page_list[-1].get('webSocketDebuggerUrl')
                if not url:
                    raise RuntimeError('Pls close the page debugger')
                    
                return RemoteDebugger(url, self._open_socket)

            raise RuntimeError(
                'Multi pages found, but title or url is not specified')

        target_page_list = []
        for page in page_list:
            if (title and (title == page['title'] or re.match(title + '$', page['title']))) or \
                (url and (url == page['url'] or re.match(url + '$', page['url']))):
                ws_addr = page.get('webSocketDebuggerUrl')
                if not ws_addr:
                    raise RuntimeError('Pls close the debugger of page: %s' %
                                       (title or url))
                target_page_list.append(ws_addr)

        if not target_page_list:
            raise RuntimeError('Can\'t find page match %s in address %s:%s' %
                               (title or url, self._addr[0], self._addr[1]))
        elif len(target_page_list) > 1 and not last:
            raise RuntimeError('Multi page found match %s in address %s:%s' %
                               (title or url, self._addr[0], self._addr[1]))
        elif len(target_page_list) == 1:
            return RemoteDebugger(target_page_list[0], self._open_socket)
        else:
            return RemoteDebugger(target_page_list[-1], self._open_socket)
