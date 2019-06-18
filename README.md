# chrome_master

> A python client implementation of [Chrome Devtools Procotol](https://chromedevtools.github.io/devtools-protocol/)

## USAGE

打开Chrome的调试开关，如：

PC端Chrome使用以下方式启动会打开调试端口`9222`

```bash
chrome --remote-debugging-port=9222
```
然后使用`chrome_master`操作Chrome

```python
chrome_master = chrome_master.ChromeMaster(('localhost', 9222))
page_debugger = chrome_master.find_page(url=url, title=title)
page_debugger.register_handler(chrome_master.RuntimeHandler)

url = page_debugger.eval_script(None, 'location.href')
```
