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

"""Input命名空间的处理器
"""

from __future__ import unicode_literals
import sys
import time

from .handler import DebuggerHandler


class EnumModifierKey(object):
    """修饰键定义"""

    Default = 0
    Alt = (18, 1)
    Ctrl = (17, 2)
    Command = (91, 4)
    Shift = (16, 8)
    All = [Alt, Ctrl, Command, Shift]


class InputHandler(DebuggerHandler):
    """Input命名空间的处理器"""

    namespace = "Input"

    def hover(self, x_offset, y_offset):
        """mouse over"""
        self.dispatchMouseEvent(type="mouseMoved", x=x_offset, y=y_offset)

    def click(self, x_offset, y_offset, duration=0):
        """点击操作

        :param x_offset: 相对于页面左上角的x轴CSS像素偏移
        :type  x_offset: int/float
        :param y_offset: 相对于页面左上角的y轴CSS像素偏移
        :type  y_offset: int/float
        :param duration: 按住鼠标的时长，单位：秒
        :type  duration: int/float
        """
        self.logger.info(
            "[%s] Click %s, %s" % (self.__class__.namespace, x_offset, y_offset)
        )
        x_offset = int(x_offset)
        y_offset = int(y_offset)
        self.dispatchMouseEvent(
            type="mousePressed", x=x_offset, y=y_offset, button="left", clickCount=1
        )
        if duration:
            time.sleep(duration)

        self.dispatchMouseEvent(
            type="mouseReleased", x=x_offset, y=y_offset, button="left", clickCount=1
        )

    def send_keys(self, keys):
        """发送按键

        :param keys: 要发送的按键码列表
        :type  keys: list
        """
        modifiers = EnumModifierKey.Default
        for key in keys:
            is_modifier_key = False
            for it in EnumModifierKey.All:
                if key == it[0]:
                    modifiers += it[1]
                    is_modifier_key = True
                    break

            if is_modifier_key:
                continue

            self.dispatchKeyEvent(
                type="keyDown",
                modifiers=modifiers,
                text=chr(key),
                key=chr(key),
                windowsVirtualKeyCode=key,
                nativeVirtualKeyCode=key,
            )
            self.dispatchKeyEvent(
                type="keyUp",
                modifiers=modifiers,
                text=chr(key),
                key=chr(key),
                windowsVirtualKeyCode=key,
                nativeVirtualKeyCode=key,
            )
            modifiers = EnumModifierKey.Default

    def send_text(self, text):
        """发送文本

        :param text: 发送的文本
        :type  text: string
        """
        if sys.version_info[0] == 2 and not isinstance(text, unicode):
            text = text.decode("utf8")
        for c in text:
            self.dispatchKeyEvent(type="char", text=c)

    def drag(
            self, x1, y1, x2, y2, step=0, fire_press_event=True, fire_release_event=True
    ):
        """从(x1, y1)点拖动到(x2, y2)点

        :param x1:   起点横坐标
        :type  x1:   int/float
        :param y1:   起点纵坐标
        :type  y1:   int/float
        :param x2:   终点横坐标
        :type  x2:   int/float
        :param y2:   终点纵坐标
        :type  y2:   int/float
        :param step: 步长
        :type  step: int
        :param fire_press_event:   是否发送Press事件
        :type  fire_press_event:   bool
        :param fire_release_event: 是否发送Release事件
        :type  fire_release_event: bool
        """
        self.logger.info(
            "[%s] Drag (%s, %s) => (%s, %s) step=%s, fire_press_event=%s, fire_release_event=%s"
            % (
                self.__class__.namespace,
                x1,
                y1,
                x2,
                y2,
                step,
                fire_press_event,
                fire_release_event,
            )
        )
        if fire_press_event:
            self.dispatchMouseEvent(
                type="mousePressed", x=x1, y=y1, button="left", clickCount=1
            )

        if step > 0:
            dx = int(x2 - x1)
            dy = int(y2 - y1)
            length = int((dx ** 2 + dy ** 2) ** 0.5)
            step_count = length // step + 1
            x_step = dx // step_count
            y_step = dy // step_count

            for i in range(step_count):
                self.dispatchMouseEvent(
                    type="mouseMoved",
                    x=x1 + x_step * i,
                    y=y1 + y_step * i,
                    button="left",
                )

        self.dispatchMouseEvent(type="mouseMoved", x=x2, y=y2, button="left")

        if fire_release_event:
            self.dispatchMouseEvent(
                type="mouseReleased", x=x2, y=y2, button="left", clickCount=1
            )
