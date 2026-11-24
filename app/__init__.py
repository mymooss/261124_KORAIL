"""KTX 디지털 트윈 관제 시스템 — Flask 앱 팩토리 (요청 기반 엔진, 서버리스 배포 가능)."""
from urllib.parse import urlparse

from flask import Flask, g, jsonify, request

from .config import load_config


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    load_config(app, test_config)
    app.json.ensure_ascii = False

    from . import db
    db.init_app(app)

    from .sim.engine import EngineError

    from .auth.routes import bp as auth_bp
    from .api.routes import bp as api_bp
    from .views.routes import bp as views_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    @app.errorhandler(EngineError)
    def _engine_error(e):
        return jsonify(error={"code": e.code, "message": e.message}), e.status

    @app.errorhandler(RuntimeError)
    def _runtime_error(e):
        app.logger.error("%s", e)
        return jsonify(error={"code": "SERVER_NOT_READY", "message": str(e)}), 503

    @app.before_request
    def _check_origin():
        # POST/PUT/DELETE 는 같은 출처(Origin)에서 온 요청만 허용한다.
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                return jsonify(error={"code": "BAD_ORIGIN", "message": "허용되지 않은 출처의 요청입니다."}), 403
        return None

    return app


def get_engine(write=True):
    """요청 단위 엔진. write=True 면 상태를 잠그고 흐른 시간만큼 진행한다. 커밋은 after_request 에서."""
    from .db import get_db
    from .sim.engine import SimulationEngine
    eng = g.get("engine")
    if eng is None or (write and not g.get("engine_write")):
        eng = SimulationEngine.open(get_db(), write=write)
        g.engine = eng
        g.engine_write = write
    return eng
