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

"""Chrome远程调试协议实现
https://chromedevtools.github.io/devtools-protocol/
"""

from __future__ import unicode_literals

try:
    import httplib
except ImportError:
    import http.client as httplib
import copy
import json
import re
import socket
import sys
import time

from . import util

from .dom_handler import DOMHandler, IDOMEventListener
from .input_handler import InputHandler
from .log_handler import LogHandler
from .remote_debugger import RemoteDebugger
from .network_handler import NetworkHandler
from .runtime_handler import RuntimeHandler
from .page_handler import PageHandler, IFrameEventListener
from .target_handler import TargetHandler


def set_logger(logger):
    util.logger = logger


class ChromeMaster(object):
    """Chrome控制端
    """

    instances = {}

    def __new__(cls, addr, open_socket_func=None):
        key = "%s:%d" % addr
        if key not in cls.instances:
            if sys.version_info[0] == 2:
                cls.instances[key] = super(ChromeMaster, cls).__new__(
                    cls, addr, open_socket_func
                )
            else:
                cls.instances[key] = super(ChromeMaster, cls).__new__(cls)
        return cls.instances[key]

    def __init__(self, addr, open_socket_func=None):
        """
        :param addr: (ip, port)
        :param open_socket_func: 创建socket函数
        """
        if not hasattr(self, "_addr"):  # not initiatized
            self._addr = addr
            self._open_socket = open_socket_func
            self._pages = {}

    # def get_page_info(self, debugger_url, url, title):
    #     result = {
    #         'title': title,
    #         'url': url,
    #         'body': None
    #     }
    #     debugger = RemoteDebugger(debugger_url, self._open_socket)
    #     debugger.register_handler(RuntimeHandler)
    #     result['body'] = debugger.runtime.eval_script(
    #         None, 'document.body.innerText')
    #     if not result['body']:
    #         debugger.close()
    #         return result
    #     if result['title'] == 'about:blank':
    #         result['title'] = debugger.runtime.eval_script(
    #             None, 'document.title')
    #     if result['url'] == 'about:blank':
    #         result['url'] = debugger.runtime.eval_script(None, 'location.href')
    #     debugger.close()
    #     return result

    def get_page_list(self, ignore_blank_page=True):
        """获取打开的页面列表
        """
        conn = httplib.HTTPConnection(self._addr[0], self._addr[1], timeout=60)
        if self._open_socket:
            if hasattr(conn, "_create_connection"):
                conn._create_connection = (
                    lambda address, timeout, source_address: self._open_socket()
                )
            else:
                # older 2.7 version
                conn.sock = self._open_socket()
        conn.request("GET", "/json")
        result = conn.getresponse().read()
        conn.close()

        try:
            page_list = json.loads(util.general_encode(result))
        except ValueError:
            raise RuntimeError(
                "Get page list failed. Pls close the page debugger\nhttp response:\n%r"
                % result
            )

        result = []
        for page in page_list:
            if page["type"] != "page":
                continue

            desc = page["description"]
            if desc:
                page["description"] = json.loads(desc)
                if not page["description"].get("width") or not page["description"].get(
                    "height"
                ):
                    continue
                if not page["description"]["visible"]:
                    continue

            if not page["url"]:
                util.logger.warn(
                    "[%s] Page %s url is null" % (self.__class__.__name__, page["id"])
                )
                continue

            if "webSocketDebuggerUrl" not in page:
                if (
                    page["id"] not in self._pages
                    or not self._pages[page["id"]]["debugger"]
                ):
                    util.logger.warn(
                        "[%s] Page %s debugger is opened"
                        % (self.__class__.__name__, page)
                    )
                    continue

            # if ignore_blank_page and 'webSocketDebuggerUrl' in page:
            #     page_info = self.get_page_info(
            #         page['webSocketDebuggerUrl'], page['url'], page['title'])
            #     if not page_info['body']:
            #         util.logger.warn('[%s] Page %s body is null' %
            #                          (self.__class__.__name__, page))
            #         continue

            #     if page['url'] == 'about:blank' and page['title'] == 'about:blank':
            #         is_blank_url = True
            #         if page_info['url']:
            #             page['url'] = page_info['url']
            #             is_blank_url = False
            #         if page_info['title']:
            #             page['title'] = page_info['title']
            #             is_blank_url = False
            #         if is_blank_url:
            #             continue
            if page["id"] not in self._pages:
                self._pages[page["id"]] = {
                    "debugger": None,
                    "timestamp": time.time(),  # add timestamp
                }

            page["timestamp"] = self._pages[page["id"]]["timestamp"]
            page.pop("faviconUrl", None)
            page.pop("devtoolsFrontendUrl", None)
            result.append(page)
        result.sort(key=lambda page: page["timestamp"])
        return result

    def _is_page_debugged(self, page):
        if self._pages[page["id"]]["debugger"]:
            return True
        else:
            return False
        # return self._pages[page['id']]['debugger'] != None

    def wait_for_debugger(self, debugger):
        debugger.register_handler(TargetHandler)
        debugger.register_handler(RuntimeHandler)
        timeout = 2
        time0 = time.time()
        while time.time() - time0 < timeout:
            if debugger.runtime.get_main_context_id():
                return True
            time.sleep(0.2)
        return False

    def _get_debugger(self, page, timeout=10):
        debugger = self._pages[page["id"]]["debugger"]
        if debugger:
            return debugger
        url = page.get("webSocketDebuggerUrl")
        if not url:
            raise RuntimeError("Pls close the page debugger")
        time0 = time.time()
        while time.time() - time0 < timeout:
            debugger = RemoteDebugger(url, self._open_socket)
            debugger.logger = util.logger
            if not self.wait_for_debugger(debugger):
                util.logger.warn(
                    "[%s] Test debugger of page [%s] %s failed"
                    % (
                        self.__class__.__name__,
                        page["id"],
                        page["title"] or page["url"],
                    )
                )
                debugger.close()
            else:
                self._pages[page["id"]]["debugger"] = debugger
                debugger.register_handler(LogHandler)
                debugger.register_handler(NetworkHandler)
                return debugger
        else:
            raise util.TimeoutError(
                "Get debugger for page [%s] %s failed"
                % (page["id"], page["title"] or page["url"])
            )

    def _filter_pages(self, page_list, title, url):
        """filter pages with title is `title` and url is `url`
        """
        target_page_list = []
        title = util.general_encode(title or "")
        url = util.general_encode(url or "")
        for page in page_list:
            page["title"] = util.general_encode(page["title"])
            if (
                title
                and title != page["title"]
                and not re.match(title + "$", page["title"])
            ):
                continue
            page["url"] = util.general_encode(page["url"])
            if url and url != page["url"] and not re.match(url + "$", page["url"]):
                continue
            ws_addr = page.get("webSocketDebuggerUrl")
            if not ws_addr and not (
                page["id"] in self._pages and self._pages[page["id"]].get("debugger")
            ):
                # 连接被其它调试器占用
                raise RuntimeError(
                    "Pls close the debugger of page: [%s] %s"
                    % (page["id"], title or url)
                )

            target_page_list.append(page)
        return target_page_list

    def _select_new_page(self, page_list, prev_pages, last=True):
        """select new page
        """
        new_page_list = []
        for page in page_list:
            if page["id"] not in prev_pages:
                new_page_list.append(page)

        if len(new_page_list) == 1:
            return new_page_list[0]
        elif len(new_page_list) > 1 and last:
            return new_page_list[-1]
        elif len(new_page_list) > 1:
            raise RuntimeError("Multi new pages found")

    def find_page(self, title=None, url=None, last=True, timeout=5):
        """查找目标页面

        :param title: 目标页面标题
        :type  title: string
        :param url:   目标页面url
        :type  url:   string
        :param last:  是否取最后一个页面
        :type  last:  boolean
        :param fitler_blank: 是否过滤空白页面
        :type  fitler_blank: boolean
        """
        ignore_blank_page = True  # bool(title or url)
        page_list = None
        target_page_list = []
        prev_pages = copy.copy(self._pages)
        time0 = time.time()
        prev_page_info = ""
        while time.time() - time0 < timeout:
            page_list = self.get_page_list(ignore_blank_page)
            if not page_list:
                util.logger.warn(
                    "[%s] No page found in address %s:%s"
                    % (self.__class__.__name__, self._addr[0], self._addr[1])
                )
                time.sleep(0.5)
                continue

            curr_page_info = json.dumps(page_list)
            if len(page_list) != len(prev_pages) or curr_page_info != prev_page_info:
                util.logger.debug(
                    "[%s] Page list: [%d][%d] %s"
                    % (
                        self.__class__.__name__,
                        len(prev_pages),
                        len(page_list),
                        json.dumps(page_list),
                    )
                )
                prev_page_info = curr_page_info

            target_page_list = self._filter_pages(page_list, title, url)

            if target_page_list:
                page = self._select_new_page(target_page_list, prev_pages, last)
                if page:
                    util.logger.info(
                        "[%s] Select new page [%s] %s"
                        % (
                            self.__class__.__name__,
                            util.unicode_decode(page["id"]),
                            util.unicode_decode(page["title"] or page["url"]),
                        )
                    )
                    return self._get_debugger(page)
            time.sleep(0.5)
        else:
            if not page_list:
                raise RuntimeError("No page found in address %s:%s" % (self._addr))
            elif not target_page_list:
                raise RuntimeError(
                    "Can't find page match title=%s url=%s in address %s:%s\nCurrent page list: %s"
                    % (title, url, self._addr[0], self._addr[1], curr_page_info)
                )

        # 未有新页面出现，在现有页面中选择
        if len(target_page_list) > 1 and not last:
            print(repr(self._addr[1]))
            raise RuntimeError(
                "Multi pages found match title=%s url=%s in address %s:%s"
                % (
                    util.unicode_decode(title),
                    util.unicode_decode(url),
                    util.unicode_decode(self._addr[0]),
                    self._addr[1],
                )
            )
        elif len(target_page_list) == 1:
            util.logger.info(
                "[%s] Select page %s"
                % (self.__class__.__name__, target_page_list[0]["url"])
            )
            return self._get_debugger(target_page_list[0])
        else:
            util.logger.info(
                "[%s] Select last page %s"
                % (self.__class__.__name__, target_page_list[-1]["url"])
            )
            return self._get_debugger(target_page_list[-1])

    def new_page(self):
        """
        打开新页面
        """
        pass
