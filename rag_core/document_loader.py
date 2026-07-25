"""
文档加载器 — 支持多种格式自动识别和加载
"""
import os
import json
from pathlib import Path
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from rag_config import (
    CHUNK_SIZE, CHUNK_OVERLAP, SUPPORTED_EXTENSIONS,
    DOCUMENTS_DIR, logger
)

# ==================== 文档加载器映射 ====================
def _get_splitter() -> RecursiveCharacterTextSplitter:
    """创建中文优化的递归分割器"""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[
            "\n\n",    # 空行（段落分隔）
            "\n",      # 换行
            "。",      # 中文句号
            "！",      # 中文感叹号
            "？",      # 中文问号
            "；",      # 中文分号
            "…",       # 省略号
            ", ",     # 英文逗号+空格
            ",",      # 英文逗号
            ". ",     # 英文句点+空格
            ".",      # 英文句点
            " ",      # 空格
            ""         # 空字符串（最后兜底）
        ],
        length_function=len,
    )


def _detect_encoding(filepath: Path) -> str:
    """自动检测文件编码"""
    # 尝试常用编码
    for enc in ["utf-8", "gbk", "gb2312", "gb18030", "big5", "utf-16"]:
        try:
            with open(filepath, "r", encoding=enc) as f:
                f.read(1000)
            logger.debug(f"文件 {filepath.name} 编码: {enc}")
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"  # 默认 utf-8


def load_txt(filepath: Path) -> List[Document]:
    """加载 TXT/MD/RST 文本文件（自动检测编码）"""
    from langchain_community.document_loaders import TextLoader
    
    # 自动检测编码
    encoding = _detect_encoding(filepath)
    loader = TextLoader(str(filepath), encoding=encoding)
    documents = loader.load()
    logger.info(f"加载 TXT: {filepath.name} (encoding={encoding}), {len(documents)} 页")
    return documents


def load_pdf(filepath: Path) -> List[Document]:
    """加载 PDF 文件"""
    try:
        from langchain_community.document_loaders import PyPDFLoader
    except ImportError:
        logger.warning(f"缺少 pypdf，无法加载 PDF: {filepath.name}。请运行: pip install pypdf")
        return []
    
    try:
        loader = PyPDFLoader(str(filepath))
        documents = loader.load()
        logger.info(f"加载 PDF: {filepath.name}, {len(documents)} 页")
        return documents
    except Exception as e:
        logger.warning(f"加载 PDF 失败 {filepath.name}: {e}")
        return []


def load_docx(filepath: Path) -> List[Document]:
    """加载 Word DOCX 文件"""
    try:
        from langchain_community.document_loaders import Docx2txtLoader
        loader = Docx2txtLoader(str(filepath))
        documents = loader.load()
        logger.info(f"加载 DOCX: {filepath.name}, {len(documents)} 页")
        return documents
    except ImportError:
        logger.warning(f"缺少 docx2txt，跳过 DOCX: {filepath.name}")
        return []


def load_csv_natural_language(filepath: Path) -> List[Document]:
    """
    加载 CSV 文件并转换为自然语言
    
    将 CSV 的每一行转为："列名1=值1，列名2=值2，..."
    这样 LLM 能正确理解数据结构
    """
    try:
        import pandas as pd
    except ImportError:
        logger.warning(f"缺少 pandas，跳过 CSV: {filepath.name}")
        return []
    
    try:
        df = pd.read_csv(filepath, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding="gbk")
    
    # 每行转为自然语言
    texts = []
    for _, row in df.iterrows():
        parts = []
        for col in df.columns:
            val = row[col]
            if pd.notna(val):
                parts.append(f"{col}={val}")
        text = "，".join(parts)
        if text:
            texts.append(text)
    
    documents = [
        Document(
            page_content=text,
            metadata={"source": filepath.name, "row": i}
        )
        for i, text in enumerate(texts)
    ]
    logger.info(f"加载 CSV: {filepath.name}, {len(documents)} 行")
    return documents


def load_excel(filepath: Path) -> List[Document]:
    """加载 Excel 文件，每张表转为自然语言"""
    try:
        import pandas as pd
    except ImportError:
        logger.warning(f"缺少 pandas，跳过 Excel: {filepath.name}")
        return []
    
    try:
        xlrd = __import__("xlrd")
    except ImportError:
        xlrd = None
    
    documents = []
    try:
        excel_file = pd.ExcelFile(filepath)
        for sheet_name in excel_file.sheet_names:
            df = excel_file.parse(sheet_name)
            for _, row in df.iterrows():
                parts = []
                for col in df.columns:
                    val = row[col]
                    if pd.notna(val):
                        parts.append(f"{col}={val}")
                text = "，".join(parts)
                if text:
                    documents.append(Document(
                        page_content=text,
                        metadata={"source": filepath.name, "sheet": sheet_name}
                    ))
        logger.info(f"加载 Excel: {filepath.name}, {len(documents)} 行")
    except Exception as e:
        logger.warning(f"加载 Excel 失败 {filepath.name}: {e}")
    
    return documents


def load_json(filepath: Path) -> List[Document]:
    """加载 JSON 文件，转为自然语言"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"加载 JSON 失败 {filepath.name}: {e}")
        return []
    
    def _dict_to_text(obj, prefix=""):
        """递归将字典转为自然语言"""
        parts = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    parts.extend(_dict_to_text(value, new_prefix))
                else:
                    parts.append(f"{new_prefix}={value}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    parts.extend(_dict_to_text(item, f"{prefix}[{i}]"))
                else:
                    parts.append(f"{prefix}[{i}]={item}")
        return parts
    
    texts = _dict_to_text(data)
    documents = [
        Document(page_content="\n".join(texts), metadata={"source": filepath.name})
    ]
    logger.info(f"加载 JSON: {filepath.name}, {len(documents)} 条")
    return documents


def load_html(filepath: Path) -> List[Document]:
    """加载 HTML 文件"""
    try:
        from langchain_community.document_loaders import HTMLLoader
        loader = HTMLLoader(str(filepath))
        documents = loader.load()
        logger.info(f"加载 HTML: {filepath.name}, {len(documents)} 页")
        return documents
    except ImportError:
        logger.warning(f"缺少可读的 HTML 加载器，跳过: {filepath.name}")
        return []


def load_document(filepath: Path) -> List[Document]:
    """
    根据文件扩展名自动选择加载器
    
    Args:
        filepath: 文件路径
        
    Returns:
        Document 列表
    """
    ext = filepath.suffix.lower()
    
    loaders = {
        ".txt": load_txt,
        ".md": load_txt,
        ".rst": load_txt,
        ".pdf": load_pdf,
        ".docx": load_docx,
        ".csv": load_csv_natural_language,
        ".xlsx": load_excel,
        ".xls": load_excel,
        ".json": load_json,
        ".html": load_html,
        ".htm": load_html,
    }
    
    loader = loaders.get(ext)
    if loader is None:
        logger.warning(f"不支持的文件类型: {ext}，尝试作为文本加载")
        loader = load_txt
    
    return loader(filepath)


def chunk_documents(documents: List[Document]) -> List[Document]:
    """
    将文档分割为小块
    
    Args:
        documents: 原始文档列表
        
    Returns:
        分割后的文档块列表
    """
    splitter = _get_splitter()
    chunks = splitter.split_documents(documents)
    logger.info(f"分割完成: {len(documents)} 页 → {len(chunks)} 块")
    return chunks


def load_directory(directory: Path) -> List[Document]:
    """
    加载整个目录下的所有文档
    
    Args:
        directory: 文档目录路径
        
    Returns:
        所有文档的分割块列表
    """
    all_chunks = []
    
    for filepath in sorted(directory.rglob("*")):
        if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                docs = load_document(filepath)
                chunks = chunk_documents(docs)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"加载失败 {filepath}: {e}")
    
    logger.info(f"目录加载完成: {len(all_chunks)} 个文档块")
    return all_chunks
