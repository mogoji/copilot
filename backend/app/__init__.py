"""后端应用包。

运行约定：
    # 启动服务
    uvicorn app.main:app

    # 评测脚本（用 python -m，让 app 成为正式包）
    python -m app.eval_retrieval
    python -m app.eval_e2e 0.60
"""
