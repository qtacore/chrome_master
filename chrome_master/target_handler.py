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
"""Target命名空间的处理器
"""

from __future__ import unicode_literals
import json
import time

from .handler import DebuggerHandler
from .util import MethodNotFoundError


class TargetHandler(DebuggerHandler):
    """
    Target命名空间的处理器
    """

    namespace = "Target"

    def on_attached(self):
        """
        附加到调试器成功回调
        """
        self._session_map = {}
        self._attached_target_info = {}
        self._target_info = {}
        self._enabled = None
        try:
            self.setDiscoverTargets(discover=True)
        except MethodNotFoundError:
            self._enabled = False
            self.logger.info(
                "[%s] Target handler not enabled" % self.__class__.namespace
            )
        else:
            self._enabled = True

    def on_recv_notify_msg(self, method, params):
        if method == "attachedToTarget":
            self.logger.info(
                "[%s] Target %s attached"
                % (self.__class__.namespace, json.dumps(params))
            )
            if "sessionId" in params:
                session_id = params["sessionId"]
                self._session_map[params["targetInfo"]["targetId"]] = session_id
                self.setAutoAttach(
                    autoAttach=True,
                    waitForDebuggerOnStart=False,
                    flatten=True,
                    sessionId=session_id,
                )
                self.global_dispatch_event("on_new_session", session_id)

        elif method == "targetCreated":
            if "targetInfo" in params:
                self.logger.info(
                    "[%s] Target %s created"
                    % (self.__class__.namespace, json.dumps(params["targetInfo"]))
                )
                if params["targetInfo"]["type"] == "page":
                    target_id = params["targetInfo"]["targetId"]
                    self._target_info[target_id] = params["targetInfo"]
                    self.attach_to_target(target_id=target_id, flatten=True)
        elif method == "targetInfoChanged":
            self.logger.info(
                "[%s] Target info changed %s"
                % (self.__class__.namespace, json.dumps(params))
            )
            if "targetInfo" in params and params["targetInfo"]["type"] == "page":
                target_id = params["targetInfo"]["targetId"]
                self._target_info[target_id] = params["targetInfo"]

    def get_sessionid_list(self):
        return list(self._session_map.values())

    def create_target(self, url="about:blank"):
        target_info = self.createTarget(url=url)
        return target_info

    def get_target_info(self):
        return self._target_info

    def attach_to_target(self, target_id, flatten=True):
        """
        传入targetId获取对应的sessionId
        """
        return self.attachToTarget(targetId=target_id, flatten=flatten)

    def wait_for_session_id(self, target_id, timeout=10):
        time0 = time.time()
        while time.time() - time0 < timeout:
            if self._enabled == False:
                return None
            if self._session_map.get(target_id):
                return self._session_map[target_id]
            else:
                time.sleep(0.5)
        else:
            return False
