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

"""Runtime命名空间的处理器
"""

from __future__ import unicode_literals
import json
import time
from .handler import DebuggerHandler
from .page_handler import PageHandler
from .util import (
    JavaScriptError,
    ChromeDebuggerProtocolError,
    IDNotFoundError,
    TimeoutError,
    unicode_decode,
)


class NodeRuntimeHandler(DebuggerHandler):
    """Node.js中的Runtime命名空间处理器
    https://chromedevtools.github.io/devtools-protocol/v8/
    """

    namespace = "Runtime"
    dependencies = []

    def on_attached(self):
        """附加到调试器成功回调"""
        self._tags = {}
        self._tag_updated = False
        self.enable()
        self.register_event_listener("on_new_session", self.on_new_session)

    def on_new_session(self, session_id):
        self.enable(session_id=session_id)

    def _get_tag(self, context_id):
        if context_id in self._tags:
            return self._tags[context_id]
        return ""

    def _eval_script(self, context_id, script):
        script = unicode_decode(script)
        tag = unicode_decode(self._get_tag(context_id))
        self.logger.info(
            "[%s][%s][%s][eval][%d] %s"
            % (
                self.__class__.namespace,
                tag,
                context_id,
                len(script),
                script[:200].strip(),
            )
        )
        script = script.replace("\\", r"\\")
        script = script.replace('"', r"\"")
        script = script.replace("\r", r"\r")
        script = script.replace("\n", r"\n")
        script = (
            r"""(function(){
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
        })();"""
            % script
        )
        params = {
            "objectGroup": "console",
            "includeCommandLineAPI": True,
            "doNotPauseOnExceptionsAndMuteConsole": False,
            "returnByValue": False,
            "generatePreview": True,
        }
        try:
            result = self.evaluate(contextId=context_id, expression=script, **params)
        # if not result:
        #     result = self.evaluate(expression=script, **params)
        except ChromeDebuggerProtocolError as e:
            result = self.evaluate(expression=script, **params)
        if "result" not in result:
            raise RuntimeError("Invalid Response: %s" % result)
        result = unicode_decode(result["result"]["value"])
        self.logger.info(
            "[%s][%s][retn] %s" % (self.__class__.namespace, tag, result[:512])
        )
        if result[0] == "E":
            return False, result[1:]
        elif result[0] == "S":
            return True, result[1:]
        else:
            raise ChromeDebuggerProtocolError(result)

    def eval_script(self, script):
        """执行JavaScript"""
        success, result = self._eval_script(1, script)
        if not success:
            raise JavaScriptError("", result)
        return result


class RuntimeHandler(NodeRuntimeHandler):
    """Runtime命名空间的处理器"""

    dependencies = [PageHandler]
    max_console_log_count = 100  # 最大存储的Console日志条数

    def __init__(self, *args):
        super(RuntimeHandler, self).__init__(*args)
        self._context_dict = {}
        self._console_logs = []
        self._console_callback = None

    def on_recv_notify_msg(self, method, params):
        """接收到通知消息

        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        """
        if method == "executionContextCreated":
            # 有新的frame创建
            context = params["context"]
            if "type" in context and context["type"] == "Extension":
                return
            if "frameId" in context:
                frame_id = context["frameId"]
            else:
                frame_id = context["auxData"]["frameId"]
            self._context_dict[frame_id] = context["id"]
            self.logger.info(
                "[%s] Add context: %s(%s %s)"
                % (
                    self.__class__.namespace,
                    context["id"],
                    frame_id,
                    context.get("origin"),
                )
            )
            self._tags[context["id"]] = self.__get_tag(context["id"])
        elif method == "executionContextDestroyed":
            context_id = params["executionContextId"]
            for frame in self._context_dict:
                if self._context_dict[frame] == context_id:
                    self.logger.info(
                        "[%s] Remove context: %s(%s)"
                        % (self.__class__.namespace, context_id, frame)
                    )
                    self._context_dict.pop(frame)
                    break
            else:
                self.logger.warn(
                    "[%s] Context %s not found" % (self.__class__.namespace, context_id)
                )
            if context_id in self._tags:
                self._tags.pop(context_id)
        elif method == "consoleAPICalled":
            for it in params["args"]:
                value = None
                if it["type"] == "object" and "objectId" in it:
                    value = {"object_id": it["objectId"]}
                elif it.get("value"):
                    value = it["value"]
                else:
                    return
                log = {
                    "timestamp": params["timestamp"],
                    "function": params["type"],
                    "frame": self._get_frame_id(params["executionContextId"]),
                    "type": it["type"],
                    "value": value,
                }
                if len(self._console_logs) >= self.max_console_log_count:
                    self._console_logs.pop(0)  # abandon old log
                self._console_logs.append(log)
                if self._console_callback:
                    self.handle_console_log(log)
                    self._console_callback(log)

    def handle_console_log(self, log):
        """Lazy retrieve log data"""
        if (
            log["type"] == "object"
            and isinstance(log["value"], dict)
            and log["value"].get("object_id")
        ):
            object_id = log["value"]["object_id"]
            log["value"] = self.get_object_properties(object_id)

    def set_console_callback(self, callback):
        """Callback for console log"""
        self._console_callback = callback
        for log in self._console_logs:
            # Handle logs before set console callback
            self.handle_console_log(log)
            callback(log)

    def _get_context_id(self, frame_id):
        """frame id to context id"""
        return self._context_dict.get(frame_id)

    def _get_frame_id(self, context_id):
        """context id to frame id"""
        for frame_id in self._context_dict:
            if self._context_dict[frame_id] == context_id:
                return frame_id
        else:
            raise RuntimeError("Context id %s not exist" % context_id)

    def _handle_object_value(self, value):
        if value["type"] in ("number", "string", "boolean"):
            return value["value"]
        elif value["type"] == "function":
            return value["description"]
        elif value["type"] == "object":
            if not "description" in value:
                return None
            return value["description"]
        elif value["type"] == "undefined":
            return "undefined"
        else:
            raise NotImplementedError(value["type"])

    def get_object_properties(self, object_id):
        """获取对象属性"""
        properties = {}
        result = self.getProperties(objectId=object_id)
        for it in result["result"]:
            if "value" in it:
                properties[it["name"]] = self._handle_object_value(it["value"])
        return properties

    def _get_main_frame_id(self):
        return self._debugger.page.get_main_frame_id()

    def get_main_context_id(self):
        frame_id = self._get_main_frame_id()
        if not frame_id:
            return None
        return self._get_context_id(frame_id)

    def __get_tag(self, context_id):
        return str(context_id)
        timeout = 5
        time0 = time.time()
        while time.time() - time0 < timeout:
            try:
                result, tag = self._eval_script(
                    context_id, "document.title || location.href"
                )
            except IDNotFoundError:
                time.sleep(0.5)
                continue
            else:
                if time.time() - time0 >= 0.1:
                    self.logger.warning(
                        "[%s] Wait for context %s ready cost %.2fs"
                        % (self.__class__.namespace, context_id, time.time() - time0)
                    )
                if not result:
                    return str(context_id)
                if "?" in tag:
                    # 截断url中的`？`
                    tag = tag[: tag.find("?")]
                return tag
        else:
            self.logger.warning(
                "[%s] Find context %s timeout" % (self.__class__.namespace, context_id)
            )
            return str(context_id)

    def eval_script(self, frame_id, script):
        """执行JavaScript"""
        timeout = 10
        time0 = time.time()
        while time.time() - time0 < timeout:
            exp = None
            frame_id = frame_id or self._get_main_frame_id()
            if not frame_id:
                time.sleep(0.5)
                continue
            context_id = self._get_context_id(frame_id)
            if not context_id:
                time.sleep(0.5)
                continue

            try:
                success, result = self._eval_script(context_id, script)
                break
            except IDNotFoundError as e:
                # 重新获取context id
                time.sleep(0.5)
                exp = e
        else:
            if exp:
                raise exp
            elif not frame_id:
                raise TimeoutError("Wait for root frame timeout")
            else:
                raise TimeoutError("Can't find context id of frame %s" % frame_id)

        if not success:
            raise JavaScriptError(frame_id, result)
        return result

    def read_console_log(self):
        """read one console log"""
        if not self._console_logs:
            return None
        return self._console_logs.pop(0)
