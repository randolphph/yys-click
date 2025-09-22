# 阴阳师挂机战斗脚本

使用 Python + PyAutoGUI 实现的阴阳师挂机战斗脚本，通过识别截图自动点击按钮，并在点击时加入随机延迟与偏移，降低被脚本检测的风险。

## 环境准备

1. 安装依赖（建议使用虚拟环境）：
   ```bash
   pip install -r requirements.txt
   ```
2. 在 `images/` 目录中存放截图素材（可以根据实际情况调整路径）。
3. 根据自己的需求复制并修改配置文件：
   ```bash
   cp targets.example.json targets.json
   ```
   - `image`：按钮截图的相对路径
   - `confidence`：匹配阈值（0-1，opencv 支持）
   - `click_margin`：点击随机偏移范围（像素）
   - `move_duration_range`：移动鼠标到目标位置的随机耗时范围
   - `pre_click_delay_range`：移动到位后点击前的随机延迟范围
   - `post_click_delay_range`：点击完成后的随机等待范围
   - `region`：可选，限定识别区域 `[left, top, width, height]`

## 运行

```bash
python yys_clicker.py --targets targets.json
```

- 将鼠标移到左上角或按 `Ctrl+C` 可快速停止。
- `--scan-interval MIN MAX` 控制空闲时循环检测的随机间隔。
- `--confidence` 可以临时覆盖全部目标的识别阈值。

## 常见提示

- 如果提示找不到图像文件，请确认配置中的路径与文件名。
- 依赖 Pillow + OpenCV 进行截图和模板匹配；所有必需库已列在 `requirements.txt`。
- 建议在低分辨率窗口或固定位置运行游戏，以提高识别成功率。
## 识别原理

- 每次循环会用 Pillow 的 `ImageGrab.grab` 截取全屏或配置的 `region` 区域。
- OpenCV (`cv2.matchTemplate`) 在截屏中搜索配置模板，取匹配度最高的位置并与 `confidence` 比较。
- 匹配成功后随机选取该区域内的坐标，加入移动、点击前后延迟，触发按键动作。
- 如果匹配失败，脚本会按 `--scan-interval` 设置的随机时间重新截图继续检测。

