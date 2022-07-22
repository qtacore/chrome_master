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
"""Page命名空间的处理器
"""

from __future__ import unicode_literals
import base64
import io
import json
import os
import time

from PIL import Image

from .handler import DebuggerHandler
from .target_handler import TargetHandler
from .util import MessageNotHandledError, MethodNotFoundError


class IFrameEventListener(object):
    """Frame事件监听器
    """

    def on_frame_created(self, parent, frame):
        """Frame被创建
        """
        pass

    def on_frame_destroyed(self, parent, frame):
        """Frame被销毁
        """
        pass


class PageHandler(DebuggerHandler):
    """Page命名空间的处理器
    """

    namespace = "Page"
    dependencies = [TargetHandler]

    def on_attached(self, *args, **kwargs):
        """附加到调试器成功回调
        """
        self.enable()
        self.register_event_listener("on_new_session", self.on_new_session)
        self._screen_data = []
        self._frame_tree = {}
        self._resource_tree = {}
        self._force_update_resource_tree = False
        self._last_recv_frame_time = 0
        frame_tree = self._get_frame_tree()
        self._build_frame_tree(self._frame_tree, frame_tree)

    def on_new_session(self, session_id):
        self.enable(session_id=session_id)

    def notify_update_resource_tree(self):
        self._force_update_resource_tree = True

    def _remove_old_child_frame(self, root, child):
        for it in root["childFrames"]:
            if it["frame"]["id"] == child["frame"]["id"]:
                # remove prev child
                self.logger.info(
                    "[%s] Frame %s is replaced by %s"
                    % (self.__class__.namespace, json.dumps(it), json.dumps(child))
                )
                root["childFrames"].remove(it)
                break

    def _build_frame_tree(self, root, frame):
        root["frame"] = {}
        root["frame"]["id"] = frame["frame"]["id"]
        root["frame"]["name"] = frame["frame"].get("name", "")
        root["frame"]["url"] = frame["frame"].get("url", "")
        root["childFrames"] = []
        if "childFrames" in frame:
            for child in frame["childFrames"]:
                item = {}
                self.dispatch_event("on_frame_created", root, item)
                self._build_frame_tree(item, child)
                self._remove_old_child_frame(root, item)
                root["childFrames"].append(item)

    def _lookup_frame(self, frame_id, root=None):
        if not root:
            root = self._frame_tree
        if not root:
            return None
        if root["frame"]["id"] == frame_id:
            return root
        for child in root["childFrames"]:
            result = self._lookup_frame(frame_id, child)
            if result:
                return result
        return None

    def _remove_child_frame(self, root, frame_id):
        if not root:
            return False
        for child in root["childFrames"]:
            if child["frame"]["id"] == frame_id:
                self.dispatch_event("on_frame_destroyed", root, child)
                root["childFrames"].remove(child)
                return True
            else:
                result = self._remove_child_frame(child, frame_id)
                if result:
                    return result
        return False

    def on_recv_notify_msg(self, method, params):
        """接收到通知消息

        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        """
        if method == "frameNavigated":
            is_root_frame = "parentId" not in params["frame"]
            if is_root_frame:
                self._resource_tree = {}
                self._frame_tree = {
                    "frame": {
                        "id": params["frame"]["id"],
                        "url": params["frame"]["url"],
                    },
                    "childFrames": [],
                }
                self.logger.info(
                    "[%s] Root frame [%s] %s loaded"
                    % (
                        self.__class__.namespace,
                        params["frame"]["id"],
                        params["frame"]["url"],
                    )
                )
            else:
                parent_frame_id = params["frame"]["parentId"]
                parent_frame = self._lookup_frame(parent_frame_id)
                if not parent_frame:
                    self.logger.warn(
                        "[%s] Frame %s not found in frame tree %s"
                        % (
                            self.__class__.namespace,
                            parent_frame_id,
                            json.dumps(self._frame_tree),
                        )
                    )
                    raise MessageNotHandledError()
                frame = {
                    "frame": {
                        "id": params["frame"]["id"],
                        "name": params["frame"].get("name", ""),
                        "url": params["frame"].get("url", ""),
                    },
                    "childFrames": [],
                }
                self._remove_old_child_frame(parent_frame, frame)
                parent_frame["childFrames"].append(frame)
                self.logger.info(
                    "[%s] Frame [%s] %s loaded in [%s]"
                    % (
                        self.__class__.namespace,
                        params["frame"]["id"],
                        params["frame"]["url"],
                        parent_frame_id,
                    )
                )
                self.dispatch_event("on_frame_created", parent_frame, frame)
        elif method == "frameAttached":
            self.logger.info(
                "[%s] Frame %s attached, parent frame is %s"
                % (
                    self.__class__.namespace,
                    params["frameId"],
                    params.get("parentFrameId"),
                )
            )
            frame = self._lookup_frame(params["frameId"])
            if not frame:
                parent_frame = self._lookup_frame(params["parentFrameId"])
                if not parent_frame:
                    self.logger.warn(
                        "[%s] Frame %s not found in frame tree %s"
                        % (
                            self.__class__.namespace,
                            params["parentFrameId"],
                            json.dumps(self._frame_tree),
                        )
                    )
                    raise MessageNotHandledError()
                frame = {}
                self._build_frame_tree(
                    frame,
                    {
                        "frame": {"id": params["frameId"], "name": "", "url": ""},
                        "childFrames": [],
                    },
                )

                parent_frame["childFrames"].append(frame)
        elif method == "frameDetached":
            self.logger.info(
                "[%s] Frame %s detached" % (self.__class__.namespace, params["frameId"])
            )
            if not self._remove_child_frame(self._frame_tree, params["frameId"]):
                self.logger.warn(
                    "[%s] Frame %s not in frame tree %s"
                    % (self.__class__.namespace, params["frameId"], json.dumps(self._frame_tree))
                )
                raise MessageNotHandledError()
        elif method == "screencastFrame":
            data = base64.b64decode(params["data"])
            self._screen_data.append((params["metadata"]["timestamp"], data))
            self._last_recv_frame_time = time.time()
        elif method == "javascriptDialogOpening":
            self.handleJavaScriptDialog(accept=True)

    def get_screen_record_data(self):
        """get screen record data
        """
        return self._screen_data

    def save_screen_record(self, save_path):
        """save screencast frames to video file

        :param save_path: video file path
        :type  save_path: string
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.logger.warn(
                "[%s] opencv-python not installed" % self.__class__.__name__
            )
            return False

        while (
            self._last_recv_frame_time and time.time() - self._last_recv_frame_time <= 5
        ):
            # 等待接收frame
            time.sleep(0.5)

        frame_rate = 10
        format = "MJPG"
        if save_path.lower().endswith(".flv"):
            format = "FLV1"
        elif save_path.lower().endswith(".mp4"):
            format = "mp4v"
        width = height = 0
        video_writer = None
        time0 = 0
        last_frame = None
        for timestamp, data in self._screen_data:
            image = Image.open(io.BytesIO(data))
            image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
            if not width or not height:
                _, width, height = image.shape[::-1]
            if not video_writer:
                video_writer = cv2.VideoWriter(
                    save_path,
                    cv2.VideoWriter_fourcc(*format),
                    frame_rate,
                    (width, height),
                )

            if time0 and timestamp - time0 > 1 / frame_rate:
                # 填充帧
                for _ in range(int((timestamp - time0) * frame_rate) - 1):
                    video_writer.write(last_frame)
            video_writer.write(image)
            last_frame = image
            time0 = timestamp

    def update_resource_tree(self):
        """update resource tree
        """
        self.logger.info("[%s] Update resource tree" % self.__class__.namespace)
        # self._resource_tree = self.getResourceTree()
        resource_tree = self.getResourceTree()
        resource_tree["childFrames"] = []
        frame_id = resource_tree["frameTree"]["frame"].get("id", "")
        session_id_list = self._debugger.target.get_sessionid_list()
        if session_id_list:
            for session_id in session_id_list:
                try:
                    session_resource_tree = self.getResourceTree(session_id=session_id)
                except MethodNotFoundError:
                    self.logger.info("[%s] Get resource tree with session id not supported" % self.__class__.namespace)
                    break
                if session_resource_tree:
                    parent_id = session_resource_tree["frameTree"]["frame"].get(
                        "parentId", ""
                    )
                    if parent_id == frame_id:
                        resource_tree["childFrames"].append(
                            session_resource_tree["frameTree"]
                        )
        self._resource_tree = resource_tree

    def _get_frame_tree(self):
        if not self._force_update_resource_tree:
            self.update_resource_tree()
            self.notify_update_resource_tree()
        return self._resource_tree["frameTree"]

    def get_frame_tree(self):
        """get frame tree
        """
        return self._frame_tree

    def get_main_frame_id(self):
        """获取顶层frame id
        """
        frame_id = None
        if "frame" in self._frame_tree:
            frame_id = self._frame_tree["frame"].get("id")
        if not frame_id:
            self.update_resource_tree()
            self.notify_update_resource_tree()
            frame = self._resource_tree["frameTree"]["frame"]
            self._frame_tree = {
                "frame": {"id": frame["id"], "url": frame["url"]},
                "childFrames": [],
            }
            self.logger.info(
                "[%s] Update frame tree %s"
                % (self.__class__.namespace, self._frame_tree)
            )
        return frame_id

    def bring_to_front(self):
        """bring current page to front
        """
        try:
            self.bringToFront()
            return True
        except MethodNotFoundError:
            return False

    def screenshot(self):
        """capture current page screen

        :return: screen png data
        """
        if not self.bring_to_front():
            self.logger.warn("Call bring_to_front failed")
        data = self.captureScreenshot()
        data = base64.b64decode(data["data"])
        return data

    def start_screencast(self):
        """start screencast
        """
        self.startScreencast()

    def stop_screencast(self):
        """stop screencast
        """
        self.stopScreencast()

    def get_cookies(self):
        """get all cookies
        """
        result = self.getCookies()
        return result["cookies"]

    def get_window_size(self):
        """get browser window size
        """
        result = self.getLayoutMetrics()
        scale = result["visualViewport"]["scale"]
        width = result["visualViewport"]["clientWidth"]
        height = result["visualViewport"]["clientHeight"]
        return scale * width, scale * height

    def nagivate(self, url, frame_id=None):
        return self.navigate(url=url, frameId=frame_id)
