# 抖音图文爬虫 - Ziky_XY

爬取抖音网页版指定用户的图文作品图片，按发布日期排序保存到本地。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 获取 Cookie

1. 打开 Chrome, 访问 https://www.douyin.com/ 并登录
2. 按 F12 打开开发者工具 -> Application -> Cookies -> www.douyin.com
3. 将 Cookie 键值对拼成字符串: key1=value1; key2=value2; ...

> 至少需要包含 sessionid 或登录相关的 Cookie。

### 3. 配置

```bash
cp .env.example .env
# 编辑 .env, 填入你的 DOUYIN_COOKIE
```

### 4. 运行

```bash
python run.py
```

## 输出结构

```
output/
├── 2026-01-15_作品标题A/
│   ├── info.txt        # 发布时间、作品ID、文案
│   ├── img_01.jpg
│   └── img_02.jpg
├── 2026-01-10_作品标题B/
│   └── ...
└── ...
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DOUYIN_COOKIE | 登录 Cookie 字符串 | (必填) |
| DOUYIN_USER_ID | 抖音用户 ID | Ziky_XY |
| MAX_POSTS | 最大爬取作品数 | 50 |
| OUTPUT_DIR | 输出目录 | ./output |
| HEADLESS | 是否无头模式 (true/false) | true |

## 依赖

- Python 3.9+
- Playwright (Chromium)
- httpx
