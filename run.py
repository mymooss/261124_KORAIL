"""로컬 실행 진입점. (Vercel 에서는 api/index.py 가 같은 앱을 띄운다)"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # 요청 기반 엔진이라 백그라운드 스레드가 없다. 화면이 열려 있는 동안 polling 요청이 시간을 진행시킨다.
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
