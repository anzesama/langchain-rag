# Streamlit测试应用目录

此目录用于存放Streamlit测试和演示应用。

## 文件清单

### test_minimal.py
- Streamlit入门示例
- 显示"Hello World"标题
- 用于测试Streamlit安装

### test_minimal2.py
- Streamlit入门示例
- 显示"Test"标题
- 验证Streamlit功能

### test_streamlit_wrapper.py
- Streamlit启动包装器
- 解决Python 3.13兼容性问题
- 在Windows上强制使用SelectorEventLoopPolicy

## 使用方法

### 启动应用
```bash
python test_streamlit_wrapper.py
```

### 启动特定应用
修改 `test_streamlit_wrapper.py` 中的参数：
```python
streamlit.cli.main(["test_minimal.py"])
```

## 技术说明

### Python 3.13兼容性
Streamlit在Python 3.13下会在Windows上出现socket阻塞bug，需要使用SelectorEventLoopPolicy。

## 注意事项

- 这些文件是测试示例，不是生产级应用
- 如需开发新的Streamlit应用，请在此目录创建新文件
- 原测试文件位于 `D:/class/` 已归档到此目录