# Weeknote

用途很简单：平时想到什么就先记下来，周末再把这些零碎内容收拾成一份能继续修改、也能直接导出 Word 的周报。

Weeknote 是一个自托管的网页应用。它没有账号系统，数据默认保存在本机 SQLite，适合个人或小团队使用。

![Weeknote 界面](docs/images/overview.jpg)

## 能做什么

- 把零散记录整理成工作汇报和技术总结
- 上传 Word、PPT、PDF、Excel、Markdown、图片和 ZIP 等附件
- 自己搭建模板，或让模型从几份样例中归纳格式
- 在对话里继续补充和修改内容
- 保存每周的多个版本，并导出为 DOCX
- 可选接入火山引擎 SAUC，用语音录入内容

## 本地运行

需要 Python 3.12。

~~~bash
git clone https://github.com/liiiyiiixiii/weeknote.git
cd weeknote/backend

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env
~~~

打开 `backend/.env`，填入 DeepSeek API key：

~~~dotenv
DEEPSEEK_API_KEY=your_key_here
~~~

启动服务：

~~~bash
uvicorn app.main:app --reload --port 8000
~~~

然后访问 <http://127.0.0.1:8000>。

图片 OCR 依赖 Tesseract；如果要识别中文图片，需要额外安装 `chi_sim` 语言包。不使用 OCR 时可以忽略。

其他设置，包括数据库位置、调用限额、数据保留时间和语音识别，都写在 [backend/.env.example](backend/.env.example) 里。生产部署时记得设置固定的 `APP_SECRET`、`APP_PUBLIC_ORIGIN` 和 `ALLOWED_HOSTS`。

## 数据和隐私

周报、设置和模板保存在 SQLite。附件原文件不会写入数据库，但提取出的文字和未完成的会话会短暂保存，以便刷新页面或多 worker 运行时继续处理。

整理内容会发送给你配置的 DeepSeek 服务；启用语音后，音频会发送给火山引擎。不要用它处理不允许交给第三方服务的数据。

本地 `.env`、数据库和生产配置都已经列入 `.gitignore`，不会进入版本库。

## 开发

~~~bash
make format
make check
~~~

提交代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请通过 GitHub 的私密漏洞报告入口提交，具体见 [SECURITY.md](SECURITY.md)。

## 部署

[deploy](deploy/) 中有通用的 Nginx 和 systemd 示例，使用的是 `example.com` 和 `/opt/weeknote` 等占位值。复制后再替换自己的域名和路径，不要把填写后的生产配置提交回来。

## License

[MIT](LICENSE) © 2026 liiiyiiixiii
