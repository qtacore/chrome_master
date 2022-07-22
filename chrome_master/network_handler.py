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

"""Network命名空间的处理器
"""

from __future__ import unicode_literals

from collections import OrderedDict
import json
import time

import six

from .handler import DebuggerHandler


class NetworkHandler(DebuggerHandler):
    """
    Network命名空间的处理器
    """

    namespace = "Network"

    def on_attached(self):
        """
        附加到调试器成功回调
        """
        self._packets = []
        self.enable()
        self.register_event_listener("on_new_session", self.on_new_session)

    def on_new_session(self, session_id):
        self.enable(session_id=session_id)

    def on_recv_notify_msg(self, method, params):
        """
        接受到通知消息
        :param  method: 消息方法名
        :type   method: string
        :param  params: 参数字典
        :type   params: dict
        """
        if method == "requestWillBeSent":
            if params["request"]["url"].startswith("data:image"):
                return
            self._packets.append(
                {
                    "start_time": time.time(),
                    "request_id": params["requestId"],
                    "request": params["request"],
                }
            )
            self.logger.debug(
                "[%s] Request [%s][%s][%s] will be sent"
                % (
                    self.__class__.namespace,
                    params["requestId"],
                    params["request"]["method"],
                    params["request"]["url"],
                )
            )
        elif method == "responseReceived":
            if params["response"]["url"].startswith("data:image"):
                return
            for packet in self._packets:
                if packet["request_id"] == params["requestId"]:
                    packet["response"] = params["response"]
                    packet["end_time"] = time.time()
                    self.logger.info(
                        "[%s] Request [%s][%s][%s] cost %.2fs, return code is %d"
                        % (
                            self.__class__.namespace,
                            params["requestId"],
                            packet["request"]["method"],
                            packet["request"]["url"],
                            packet["end_time"] - packet["start_time"],
                            packet["response"]["status"],
                        )
                    )
                    break

    def set_http_headers(self, session_id, **kwargs):
        """
        设置HTTP请求头
        :param  **kwargs: 请求头信息
        :type   **kwargs: dict
        """
        headers = OrderedDict()
        for key, value in six.iteritems(kwargs):
            headers[key] = value
        self.setExtraHTTPHeaders(headers=headers, session_id=session_id)
        self.logger.info(
            "[%s] Set extra http headers: %s"
            % (self.__class__.namespace, json.dumps(headers))
        )
