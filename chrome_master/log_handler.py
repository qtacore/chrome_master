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

"""Log命名空间的处理器
"""

from .handler import DebuggerHandler
from .util import MethodNotFoundError


class LogHandler(DebuggerHandler):
    """
    Log命名空间的处理器
    """

    namespace = "Log"

    def on_attached(self):
        """
        附加到调试器成功回调
        """
        try:
            self.enable()
        except MethodNotFoundError:
            self.logger.info("[%s] Log handler not enabled" % self.__class__.namespace)
        else:
            self.startViolationsReport(
                config=[
                    {"name": "longTask", "threshold": 200},
                    {"name": "longLayout", "threshold": 30},
                    {"name": "blockedEvent", "threshold": 100},
                    {"name": "blockedParser", "threshold": -1},
                    {"name": "handler", "threshold": 150},
                    {"name": "recurringHandler", "threshold": 50},
                    {"name": "discouragedAPIUse", "threshold": -1},
                ]
            )

    def on_recv_notify_msg(self, method, params):
        """
        接收到通知消息
        :param  method: 消息方法名
        :type   method: string
        :param  params: 参数字典
        :type   params: dict
        """
        if method == "entryAdded":
            params = params["entry"]
            level = params["level"]
            self.logger.info(
                "[%s][%s][%s] %s"
                % (self.__class__.namespace, level, params.get("url", ""), params["text"])
            )

