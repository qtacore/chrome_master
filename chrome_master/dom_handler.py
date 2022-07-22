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


"""DOM命名空间的处理器
"""

from __future__ import unicode_literals
import io
import xml.dom.minidom as minidom

from .handler import DebuggerHandler
from .util import NodeNotFoundError


class EnumNodeType(object):
    """Node type
    """

    ELEMENT_NODE = 1
    ATTRIBUTE_NODE = 2
    TEXT_NODE = 3
    CDATA_SECTION_NODE = 4
    ENTITY_REFERENCE_NODE = 5
    ENTITY_NODE = 6
    PROCESSING_INSTRUCTION_NODE = 7
    COMMENT_NODE = 8
    DOCUMENT_NODE = 9
    DOCUMENT_TYPE_NODE = 10
    DOCUMENT_FRAGMENT_NODE = 11
    NOTATION_NODE = 12


class Node(object):
    """Wrapper for minidom.Node
    """

    def __init__(self, doc, id, node):
        self._doc = doc
        self._id = id
        self._node = node
        self._xpath = None

    @property
    def id(self):
        return self._id

    @property
    def xpath(self):
        if self._xpath is None:
            self._xpath = self._get_xpath()
        return self._xpath

    def on_attribute_modified(self, attr, value):
        if self._node.nodeName in ("body", "script", "style", "link"):
            return
        self._xpath = None

    def _get_xpath(self):
        import xpath

        if self._doc == self._node or self._node.nodeName in ("html", "body"):
            return ""
        xpaths = []
        node = self
        while node.nodeName != "body":
            path = "/" + node.nodeName
            cond_list = []
            for attr, value in node.attributes.items():
                if attr in ("style",):
                    continue
                if value:
                    cond_list.append('@%s="%s"' % (attr, value))
            if cond_list:
                path += "[%s]" % " and ".join(cond_list)
            xpaths.insert(0, path)
            s_xpath = "/" + "".join(xpaths)
            result = xpath.find(s_xpath, self._doc)
            if len(result) == 1:
                return s_xpath
            elif len(result) == 0:
                raise RuntimeError(s_xpath)
            node = node.parentNode
        return ""

    def __hash__(self):
        return hash(self._id)

    def __str__(self):
        attrs = []
        if self.attributes:
            for attr in self.attributes.keys():
                attrs.append('%s="%s"' % (attr, self.getAttribute(attr)))
        return "<Node object %d %s[%s]>" % (self._id, self.nodeName, " ".join(attrs))

    def __eq__(self, other):
        if self.nodeName != other.nodeName:
            return False
        if self.nodeName not in ("#text", "#comment"):
            for attr in ("id", "name", "class"):
                if self.getAttribute(attr) != other.getAttribute(attr):
                    return False
        return True

    def __getattr__(self, attr):
        return getattr(self._node, attr)


class IDOMEventListener(object):
    """DOM事件监听器接口
    """

    def on_document_updated(self):
        pass

    def on_node_attr_modified(self, node, attr, value):
        pass

    def on_node_text_modified(self, node, text):
        pass

    def on_node_inserted(self, parent, node):
        pass

    def on_node_removed(self, parent, node):
        pass


class DOMHandler(DebuggerHandler):
    """DOM命名空间的处理器
    """

    namespace = "DOM"

    def on_attached(self):
        """附加到调试器成功回调
        """
        self.enable()
        self._dom = minidom.getDOMImplementation()
        self._doc = None
        self.get_dom_tree()

    def on_recv_notify_msg(self, method, params):
        """接收到通知消息

        :param method: 消息方法名
        :type  method: string
        :param params: 参数字典
        :type  params: dict
        """
        if method == "attributeModified":
            self._on_node_attribute_modified(
                params["nodeId"], params["name"], params["value"]
            )
        elif method == "attributeRemoved":
            pass
        elif method == "characterDataModified":
            pass
        elif method == "childNodeCountUpdated":
            pass
        elif method == "childNodeInserted":
            self._on_node_inserted(params["parentNodeId"], params["node"])
        elif method == "childNodeRemoved":
            self._on_node_removed(params["parentNodeId"], params["nodeId"])
        elif method == "distributedNodesUpdated":
            pass
        elif method == "documentUpdated":
            self.logger.info("[%s] Document updated" % (self.__class__.__name__))
            self._doc = None
            self.get_dom_tree()
            self._on_document_updated()
        elif method == "inlineStyleInvalidated":
            pass
        elif method == "pseudoElementAdded":
            pass
        elif method == "pseudoElementRemoved":
            pass
        elif method == "setChildNodes":
            root = self._get_node_by_id(self._doc, params["parentId"])
            if not root:
                self.logger.warn(
                    "[%s] Node %d not found"
                    % (self.__class__.namespace, params["parentId"])
                )
                return
            tree = {"children": params["nodes"]}
            self._build_dom_tree(root, tree)
        elif method == "shadowRootPopped":
            pass
        elif method == "shadowRootPushed":
            pass

        elif method == "setNodeValue":
            node_id = params["nodeId"]
            if not node_id:
                self.logger.warn("[%s] Get node failed." % self.__class__.namespace)
                return
            self.set_node_value(node_id, params["value"])

        else:
            self.logger.warn(
                "[%s] Unknown event %s" % (self.__class__.namespace, method)
            )

    def _on_document_updated(self):
        for listener in self._event_listeners:
            listener.on_document_updated()

    def _on_node_attribute_modified(self, node_id, attr, value):
        node = self._get_node_by_id(self._doc, node_id)
        if not node:
            self.logger.warn(
                "[%s] Node %d not found" % (self.__class__.namespace, node_id)
            )
            return
        node.on_attribute_modified(attr, value)
        node.setAttribute(attr, value)
        for listener in self._event_listeners:
            listener.on_node_attr_modified(node, attr, value)

    def __on_node_inserted(self, parent, node):
        if node.nodeType == EnumNodeType.TEXT_NODE:
            for listener in self._event_listeners:
                listener.on_node_text_modified(parent, node.nodeValue)
        elif node.nodeType == EnumNodeType.COMMENT_NODE:
            return
        else:
            for listener in self._event_listeners:
                listener.on_node_inserted(parent, node)

    def _on_node_inserted(self, parent_id, node):
        parent = self._get_node_by_id(self._doc, parent_id)
        if not parent:
            self.logger.warn(
                "[%s] Node %d not found" % (self.__class__.namespace, parent_id)
            )
            return
        node = self._create_node(node)
        if node:
            parent.appendChild(node)
            self.__on_node_inserted(parent, node)

    def _on_node_removed(self, parent_id, node_id):
        parent = self._get_node_by_id(self._doc, parent_id)
        if not parent:
            self.logger.warn(
                "[%s] Node %d not found" % (self.__class__.namespace, parent_id)
            )
            return
        node = self._get_node_by_id(self._doc, node_id)
        if not node:
            self.logger.warn(
                "[%s] Node %d not found" % (self.__class__.namespace, node_id)
            )
            return
        parent.removeChild(node)
        for listener in self._event_listeners:
            listener.on_node_removed(parent, node)

    def _get_node_by_id(self, root, node_id):
        if root.id == node_id:
            return root
        for child in root.childNodes:
            node = self._get_node_by_id(child, node_id)
            if node:
                return node
        return None

    def _create_node(self, node_data):
        if node_data["nodeType"] == EnumNodeType.ELEMENT_NODE:
            node = self._doc.createElement(node_data["nodeName"].lower())
            if "attributes" in node_data:
                for i in range(0, len(node_data["attributes"]), 2):
                    attr = node_data["attributes"][i]
                    value = node_data["attributes"][i + 1]
                    node.setAttribute(attr, value)
                    if attr == "id":
                        node.setIdAttribute("id")

        elif node_data["nodeType"] == EnumNodeType.TEXT_NODE:
            node = self._doc.createTextNode(node_data["nodeValue"])
        elif node_data["nodeType"] == EnumNodeType.COMMENT_NODE:
            node = self._doc.createComment(node_data["nodeValue"])
        else:
            self.logger.warn(
                "[%s] Unhandled node [%d] %s"
                % (
                    self.__class__.__name__,
                    node_data["nodeType"],
                    node_data["nodeName"],
                )
            )
            return None

        return Node(self._doc, node_data["nodeId"], node)

    def _build_dom_tree(self, root, tree):
        if "children" not in tree:
            return
        for child in tree["children"]:
            node = self._create_node(child)
            if node:
                root.appendChild(node)
                self.__on_node_inserted(root, node)
                self._build_dom_tree(node, child)

    def _request_child_nodes(self, root, depth=-1):
        """请求子节点
        """
        self.requestChildNodes(nodeId=root.id, depth=depth)

    def set_node_attribute(self, node, attr, value):
        """设置节点属性
        """
        try:
            self.setAttributeValue(nodeId=node.id, name=attr, value=str(value))
            return True
        except NodeNotFoundError:
            self.logger.warn(
                "[%s] Node %d not found when set attribute %s"
                % (self.__class__.namespace, node.id, attr)
            )
            return False

    def set_node_value(self, node, value):
        """
        修改节点值
        """
        try:
            self.setNodeValue(nodeId=node.id, value=str(value))
            return True
        except NodeNotFoundError:
            self.logger.warn("[%s] Node not found." % self.__class__.namespace)
            return False

    def get_dom_tree(self):
        """获取DOM树
        """
        result = self.getDocument()
        root = result["root"]
        assert root["nodeName"] == "#document"
        assert root["nodeType"] == EnumNodeType.DOCUMENT_NODE
        doc = self._dom.createDocument(None, None, None)
        self._doc = Node(doc, root["nodeId"], doc)
        self._build_dom_tree(self._doc, root)
        self._request_child_nodes(self._doc.getElementsByTagName("body")[0])

    def toxml(self):
        """生成xml
        """
        fp = io.StringIO()
        self._doc.writexml(fp, addindent="  ", newl="\n", encoding="utf-8")
        fp.seek(0)
        xml = fp.read()
        fp.close()
        return xml

    def upload_files(self, file_list, node_selector=None):
        """上传文件

        :param file_list:     文件路径列表
        :type  file_list:     list
        :param node_selector: 节点selector
        :type  node_selector: string
        """
        if not node_selector:
            node_selector = 'input[type="file"]'
        root = self.getDocument()["root"]
        node = self.querySelector(nodeId=root["nodeId"], selector=node_selector)
        self.setFileInputFiles(files=file_list, nodeId=node["nodeId"])
