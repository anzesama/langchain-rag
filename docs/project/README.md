# 电信客户流失预测系统

## 快速启动

### 方式一：离线 HTML 版本（推荐）
1. 双击 `webapp/START_APP.bat` 或手动打开 `webapp/index.html`
2. 等待模型加载（首次约 10-30 秒）
3. 填写客户信息，点击"开始预测"
4. **完全离线运行，数据不会离开浏览器**

### 方式二：Streamlit Web 应用
```bash
cd webapp
conda activate ml_env
streamlit run app_churn.py
```
> ⚠️ 注意：本机网络协议栈损坏，此方式需要先修复环回适配器

## 项目结构
```
电信预测/
├── models/
│   ├── best_churn_model.pkl      # 训练的 Random Forest 模型
│   ├── scaler.pkl                # 标准化器
│   ├── column_info.pkl           # 列信息
│   ├── churn_model.onnx          # ONNX 格式模型（离线版使用）
│   ├── column_info.json          # 列信息（JSON 格式）
│   └── evaluation_report.txt     # 模型评估报告
├── webapp/
│   ├── index.html                # 离线 HTML 预测应用（自动生成）
│   ├── index_template.html       # HTML 模板
│   ├── app_churn.py              # Streamlit Web 应用
│   ├── START_APP.bat             # 一键启动脚本
│   └── data.csv                  # 原始数据（用于图表）
├── train_and_save_model.py       # 模型训练脚本
├── export_onnx.py                # ONNX 导出脚本
├── generate_html.py              # HTML 生成脚本
├── requirements.txt              # 依赖清单
├── PLAN.md                       # 诊断报告与解决方案
└── PHASE_SUMMARY.md              # 阶段复盘
```

## 技术细节
- **模型**: Random Forest Classifier (AUC: 0.9346, Accuracy: 89%)
- **特征**: 19 个（3 个数值 + 16 个类别）
- **离线推理**: ONNX Runtime Web (CPU)
- **可视化**: Chart.js (饼图、柱状图、直方图)

## 依赖安装
```bash
conda activate ml_env
pip install -r requirements.txt
pip install onnx onnxruntime skl2onnx
```

## 模型导出
```bash
python export_onnx.py          # 导出 ONNX 模型
python generate_html.py         # 生成离线 HTML 应用
```
