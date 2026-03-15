import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",  # 告诉 uvicorn 去 backend/app.py 里找 app 这个变量
        host="127.0.0.1",   # 只监听本机，不对外暴露
        port=8000,
        reload=True         # 代码改了自动重启，开发时用
    )